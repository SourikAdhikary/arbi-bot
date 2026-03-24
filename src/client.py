"""Polymarket CLOB client wrapper with authentication and market data fetching."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from src.config import PolymarketConfig, polymarket_cfg

logger = logging.getLogger(__name__)


@dataclass
class Market:
    condition_id: str
    question: str
    slug: str
    active: bool
    closed: bool
    tokens: list[TokenPair]
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: str = ""
    neg_risk: bool = False

    @property
    def is_binary(self) -> bool:
        return len(self.tokens) == 1

    @property
    def outcomes_count(self) -> int:
        return len(self.tokens)


@dataclass
class TokenPair:
    """Represents a YES/NO outcome pair for a market."""
    outcome: str
    token_id: str
    winner: bool | None = None


@dataclass
class OrderBookSnapshot:
    token_id: str
    bids: list[dict[str, Any]] = field(default_factory=list)
    asks: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    @staticmethod
    def _get_price(entry: Any) -> float:
        if isinstance(entry, dict):
            return float(entry["price"])
        return float(entry.price)

    @property
    def best_bid(self) -> float | None:
        if not self.bids:
            return None
        return max(self._get_price(b) for b in self.bids)

    @property
    def best_ask(self) -> float | None:
        if not self.asks:
            return None
        return min(self._get_price(a) for a in self.asks)

    @property
    def midpoint(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2


class PolymarketClient:
    """Wraps the CLOB client and Gamma API for unified market access."""

    def __init__(self, cfg: PolymarketConfig = polymarket_cfg) -> None:
        self._cfg = cfg
        self._http = httpx.Client(base_url=cfg.gamma_host, timeout=30)
        self._clob: ClobClient | None = None
        self._authenticated = False

    def connect(self) -> None:
        """Initialize CLOB client and derive API credentials."""
        kwargs: dict[str, Any] = {
            "host": self._cfg.host,
            "key": self._cfg.private_key,
            "chain_id": self._cfg.chain_id,
            "signature_type": self._cfg.signature_type,
        }
        if self._cfg.funder:
            kwargs["funder"] = self._cfg.funder

        self._clob = ClobClient(**kwargs)
        creds = self._clob.create_or_derive_api_creds()
        self._clob.set_api_creds(creds)
        self._authenticated = True
        logger.info("Connected to Polymarket CLOB (chain_id=%d)", self._cfg.chain_id)

    @property
    def clob(self) -> ClobClient:
        if self._clob is None:
            raise RuntimeError("Call .connect() before accessing the CLOB client")
        return self._clob

    # -- Market data (Gamma API) --------------------------------------------------

    def fetch_active_markets(self, limit: int = 100, max_markets: int = 2000) -> list[Market]:
        """Fetch active markets from the Gamma API, sorted by volume descending."""
        markets: list[Market] = []
        offset = 0

        while len(markets) < max_markets:
            resp = self._http.get(
                "/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                    "offset": offset,
                    "order": "volume",
                    "ascending": "false",
                },
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break

            for raw in batch:
                tokens = self._parse_tokens(raw)
                if not tokens:
                    continue
                markets.append(
                    Market(
                        condition_id=raw.get("conditionId", ""),
                        question=raw.get("question", ""),
                        slug=raw.get("slug", ""),
                        active=raw.get("active", False),
                        closed=raw.get("closed", False),
                        tokens=tokens,
                        volume=float(raw.get("volume", 0)),
                        liquidity=float(raw.get("liquidity", 0)),
                        end_date=raw.get("endDate", ""),
                        neg_risk=raw.get("negRisk", False),
                    )
                )
            offset += limit

        logger.info("Fetched %d active markets", len(markets))
        return markets

    # -- Order book ---------------------------------------------------------------

    def get_order_book(self, token_id: str) -> OrderBookSnapshot:
        book = self.clob.get_order_book(token_id)
        return OrderBookSnapshot(
            token_id=token_id,
            bids=book.get("bids", []) if isinstance(book, dict) else getattr(book, "bids", []),
            asks=book.get("asks", []) if isinstance(book, dict) else getattr(book, "asks", []),
        )

    def get_midpoint(self, token_id: str) -> float | None:
        try:
            mid = self.clob.get_midpoint(token_id)
            return float(mid) if mid else None
        except Exception:
            logger.debug("Failed to get midpoint for %s", token_id)
            return None

    def get_price(self, token_id: str, side: str = "BUY") -> float | None:
        try:
            price = self.clob.get_price(token_id, side)
            return float(price) if price else None
        except Exception:
            logger.debug("Failed to get price for %s side=%s", token_id, side)
            return None

    # -- Order execution ----------------------------------------------------------

    def place_market_buy(
        self,
        token_id: str,
        price: float,
        size: float,
        tick_size: str = "0.01",
        neg_risk: bool = False,
    ) -> dict[str, Any]:
        resp = self.clob.create_and_post_order(
            OrderArgs(token_id=token_id, price=price, size=size, side=BUY),
            options={"tick_size": tick_size, "neg_risk": neg_risk},
            order_type=OrderType.FOK,
        )
        logger.info("BUY order placed: token=%s price=%.4f size=%.2f resp=%s", token_id, price, size, resp)
        return resp

    def place_limit_buy(
        self,
        token_id: str,
        price: float,
        size: float,
        tick_size: str = "0.01",
        neg_risk: bool = False,
    ) -> dict[str, Any]:
        resp = self.clob.create_and_post_order(
            OrderArgs(token_id=token_id, price=price, size=size, side=BUY),
            options={"tick_size": tick_size, "neg_risk": neg_risk},
            order_type=OrderType.GTC,
        )
        logger.info("LIMIT BUY: token=%s price=%.4f size=%.2f resp=%s", token_id, price, size, resp)
        return resp

    def cancel_all(self) -> Any:
        return self.clob.cancel_all()

    def get_positions(self) -> list[dict[str, Any]]:
        try:
            return self.clob.get_positions() or []
        except Exception:
            logger.warning("Failed to fetch positions")
            return []

    # -- Internal -----------------------------------------------------------------

    @staticmethod
    def _parse_tokens(raw: dict[str, Any]) -> list[TokenPair]:
        import json

        clob_ids = raw.get("clobTokenIds", "")
        outcomes = raw.get("outcomes", "")

        if isinstance(clob_ids, str):
            try:
                clob_ids = json.loads(clob_ids)
            except (json.JSONDecodeError, TypeError):
                clob_ids = [t.strip().strip('"') for t in clob_ids.strip("[]").split(",") if t.strip()]

        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except (json.JSONDecodeError, TypeError):
                outcomes = [o.strip().strip('"') for o in outcomes.strip("[]").split(",") if o.strip()]

        if not clob_ids:
            return []

        tokens: list[TokenPair] = []
        for i, tid in enumerate(clob_ids):
            tokens.append(
                TokenPair(
                    outcome=outcomes[i] if i < len(outcomes) else f"Outcome_{i}",
                    token_id=tid,
                )
            )
        return tokens
