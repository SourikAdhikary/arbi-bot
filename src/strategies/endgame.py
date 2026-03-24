"""Endgame sniping — buy near-certain outcomes close to resolution.

Ranks opportunities by a composite score that balances:
  - Profit per share (higher is better)
  - Days to resolution (sooner is better — money back faster)
  - Market volume (higher is better — more liquid, more trustworthy)
  - Bid depth (can we actually exit if needed?)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.config import TradingConfig, trading_cfg
from src.scanner import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class EndgameOpportunity:
    market_question: str
    market_slug: str
    condition_id: str
    neg_risk: bool
    token_id: str
    outcome: str
    price: float
    end_date: str
    days_to_end: float
    volume: float
    liquidity: float
    bid_depth: float
    score: float

    @property
    def profit_per_share(self) -> float:
        return 1.0 - self.price

    @property
    def return_pct(self) -> float:
        return (self.profit_per_share / self.price) * 100

    def __str__(self) -> str:
        return (
            f"ENDGAME  score={self.score:.1f}  "
            f"price=${self.price:.2f}  profit=${self.profit_per_share:.2f}/sh  "
            f"days={self.days_to_end:.1f}  vol=${self.volume:,.0f}  "
            f"{self.market_question[:45]}"
        )


class EndgameStrategy:
    """Finds high-probability outcomes trading below $1 near resolution."""

    def __init__(self, cfg: TradingConfig = trading_cfg) -> None:
        self._cfg = cfg

    def scan(self, snapshots: list[MarketSnapshot]) -> list[EndgameOpportunity]:
        opportunities: list[EndgameOpportunity] = []

        for snap in snapshots:
            opps = self._check_market(snap)
            opportunities.extend(opps)

        opportunities.sort(key=lambda o: o.score, reverse=True)
        return opportunities

    def _check_market(self, snap: MarketSnapshot) -> list[EndgameOpportunity]:
        market = snap.market
        results: list[EndgameOpportunity] = []

        if market.volume < self._cfg.min_market_volume:
            return results

        days_to_end = self._days_until_end(market.end_date)
        if days_to_end is None or days_to_end > self._cfg.max_days_to_resolution:
            return results

        for token in market.tokens:
            book = snap.books.get(token.token_id)
            if book is None or book.best_ask is None:
                continue

            price = book.best_ask

            if price < self._cfg.min_endgame_probability:
                continue
            if price > self._cfg.max_endgame_price:
                continue

            bid_depth = self._compute_bid_depth(book)
            score = self._score(price, days_to_end, market.volume, bid_depth)

            results.append(
                EndgameOpportunity(
                    market_question=market.question,
                    market_slug=market.slug,
                    condition_id=market.condition_id,
                    neg_risk=market.neg_risk,
                    token_id=token.token_id,
                    outcome=token.outcome,
                    price=price,
                    end_date=market.end_date,
                    days_to_end=days_to_end,
                    volume=market.volume,
                    liquidity=market.liquidity,
                    bid_depth=bid_depth,
                    score=score,
                )
            )

        return results

    @staticmethod
    def _score(price: float, days: float, volume: float, bid_depth: float) -> float:
        """Composite score: higher = better opportunity.

        Components (all normalized roughly 0-100):
          profit_score:  how much we make per dollar risked
          time_score:    prefer sooner resolution (money back faster)
          volume_score:  prefer liquid markets (log scale)
          depth_score:   prefer markets where we can exit via bids
        """
        import math

        profit_pct = ((1.0 - price) / price) * 100
        profit_score = min(profit_pct * 10, 100)

        time_score = max(0, 100 - (days * 7))

        volume_score = min(math.log10(max(volume, 1)) * 20, 100)

        depth_score = min(bid_depth * 10, 100)

        return (profit_score * 0.35) + (time_score * 0.30) + (volume_score * 0.20) + (depth_score * 0.15)

    @staticmethod
    def _compute_bid_depth(book: object) -> float:
        """Sum of bid sizes — rough measure of exit liquidity."""
        total = 0.0
        bids = getattr(book, "bids", [])
        for b in bids:
            try:
                size = float(b["size"]) if isinstance(b, dict) else float(b.size)
                total += size
            except (KeyError, AttributeError, TypeError, ValueError):
                pass
        return total

    @staticmethod
    def _days_until_end(end_date: str) -> float | None:
        if not end_date:
            return None
        try:
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            delta = end - datetime.now(timezone.utc)
            return max(delta.total_seconds() / 86400, 0)
        except (ValueError, TypeError):
            return None
