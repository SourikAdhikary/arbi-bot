"""Market scanner — continuously fetches markets and feeds them to strategies."""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from src.client import Market, OrderBookSnapshot, PolymarketClient
from src.config import TradingConfig, trading_cfg

logger = logging.getLogger(__name__)

CONCURRENCY = 20


@dataclass
class MarketSnapshot:
    """A market together with live order-book snapshots for every token."""
    market: Market
    books: dict[str, OrderBookSnapshot] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def yes_price(self) -> float | None:
        """Best ask for the first (YES) token."""
        if not self.market.tokens:
            return None
        book = self.books.get(self.market.tokens[0].token_id)
        return book.best_ask if book else None

    def no_price(self) -> float | None:
        """Best ask for the second (NO) token — if binary market."""
        if len(self.market.tokens) < 2:
            return None
        book = self.books.get(self.market.tokens[1].token_id)
        return book.best_ask if book else None


class MarketScanner:
    """Periodically refreshes market list and snapshots order books."""

    def __init__(
        self,
        client: PolymarketClient,
        cfg: TradingConfig = trading_cfg,
    ) -> None:
        self._client = client
        self._cfg = cfg
        self._markets: list[Market] = []
        self._last_market_refresh: float = 0
        self._pool = ThreadPoolExecutor(max_workers=CONCURRENCY)

    @property
    def markets(self) -> list[Market]:
        return list(self._markets)

    async def refresh_markets(self) -> None:
        """Reload the full market list from Gamma API."""
        loop = asyncio.get_running_loop()
        self._markets = await loop.run_in_executor(
            self._pool,
            lambda: self._client.fetch_active_markets(max_markets=self._cfg.max_markets),
        )
        self._last_market_refresh = time.time()
        logger.info("Market list refreshed: %d markets", len(self._markets))

    def _snapshot_market_sync(self, market: Market) -> MarketSnapshot | None:
        """Synchronous single-market snapshot for use in thread pool."""
        books: dict[str, OrderBookSnapshot] = {}
        for token in market.tokens:
            try:
                book = self._client.get_order_book(token.token_id)
                books[token.token_id] = book
            except Exception:
                pass
        if not books:
            return None
        return MarketSnapshot(market=market, books=books)

    async def scan_all(self) -> list[MarketSnapshot]:
        """Snapshot every active market in parallel. Refreshes market list if stale."""
        now = time.time()
        if now - self._last_market_refresh > self._cfg.markets_refresh_seconds:
            await self.refresh_markets()

        total = len(self._markets)
        logger.info("Scanning order books for %d markets (%d concurrent)...", total, CONCURRENCY)

        loop = asyncio.get_running_loop()
        sem = asyncio.Semaphore(CONCURRENCY)

        async def _snap(idx: int, market: Market) -> MarketSnapshot | None:
            async with sem:
                result = await loop.run_in_executor(self._pool, self._snapshot_market_sync, market)
                if idx > 0 and idx % 200 == 0:
                    logger.info("  ...scanned %d / %d markets", idx, total)
                return result

        tasks = [_snap(i, m) for i, m in enumerate(self._markets)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        snapshots = [r for r in results if isinstance(r, MarketSnapshot)]
        failed = total - len(snapshots)

        logger.info(
            "Scan complete: %d OK, %d failed (%.1fs)",
            len(snapshots), failed, time.time() - now,
        )
        return snapshots
