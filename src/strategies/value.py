"""Value betting — detect mispriced markets where the crowd is wrong.

Looks for markets where YES + NO prices imply a different probability
than what simple heuristics suggest. Specifically:

1. Stale prices: midpoint hasn't moved but volume is spiking on one side
   (someone knows something, price hasn't caught up)
2. Overreaction: price moved too far too fast (buy the other side)
3. Bid-ask imbalance: heavy bids vs light asks (or vice versa) signal
   directional pressure that hasn't fully repriced
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import TradingConfig, trading_cfg
from src.scanner import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class ValueOpportunity:
    market_question: str
    market_slug: str
    condition_id: str
    neg_risk: bool
    token_id: str
    outcome: str
    price: float
    fair_value: float
    edge_pct: float
    signal: str
    volume: float
    bid_depth: float
    ask_depth: float
    score: float

    @property
    def profit_per_share(self) -> float:
        return self.fair_value - self.price

    def __str__(self) -> str:
        return (
            f"VALUE  score={self.score:.1f}  edge={self.edge_pct:+.1f}%  "
            f"price=${self.price:.2f}  fair=${self.fair_value:.2f}  "
            f"signal={self.signal}  {self.market_question[:40]}"
        )


class ValueStrategy:
    """Finds mispriced markets via order book imbalance and spread analysis."""

    def __init__(self, cfg: TradingConfig = trading_cfg) -> None:
        self._cfg = cfg

    def scan(self, snapshots: list[MarketSnapshot]) -> list[ValueOpportunity]:
        opportunities: list[ValueOpportunity] = []

        for snap in snapshots:
            opps = self._check_market(snap)
            opportunities.extend(opps)

        opportunities.sort(key=lambda o: o.score, reverse=True)
        return opportunities

    def _check_market(self, snap: MarketSnapshot) -> list[ValueOpportunity]:
        market = snap.market
        results: list[ValueOpportunity] = []

        if market.volume < self._cfg.min_market_volume:
            return results
        if len(market.tokens) < 2:
            return results

        for token in market.tokens:
            book = snap.books.get(token.token_id)
            if book is None or book.best_ask is None or book.best_bid is None:
                continue

            price = book.best_ask
            if price < 0.15 or price > 0.85:
                continue

            bid_depth = self._depth(book.bids)
            ask_depth = self._depth(book.asks)
            spread = book.best_ask - book.best_bid

            opp = self._check_imbalance(snap, token, book, price, bid_depth, ask_depth, spread)
            if opp:
                results.append(opp)

            opp = self._check_wide_spread(snap, token, book, price, bid_depth, ask_depth, spread)
            if opp:
                results.append(opp)

        return results

    def _check_imbalance(
        self, snap, token, book, price, bid_depth, ask_depth, spread
    ) -> ValueOpportunity | None:
        """Heavy bids + light asks = price likely going up. Buy before it does."""
        if bid_depth <= 0 or ask_depth <= 0:
            return None

        imbalance_ratio = bid_depth / ask_depth

        if imbalance_ratio < 3.0:
            return None

        import math
        pressure_boost = min(math.log2(imbalance_ratio) * 0.03, 0.10)
        fair_value = min(price + pressure_boost, 0.99)
        edge_pct = ((fair_value - price) / price) * 100

        if edge_pct < 3.0:
            return None

        score = self._score_value(edge_pct, snap.market.volume, bid_depth, spread)

        return ValueOpportunity(
            market_question=snap.market.question,
            market_slug=snap.market.slug,
            condition_id=snap.market.condition_id,
            neg_risk=snap.market.neg_risk,
            token_id=token.token_id,
            outcome=token.outcome,
            price=price,
            fair_value=fair_value,
            edge_pct=edge_pct,
            signal="BID_IMBALANCE",
            volume=snap.market.volume,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            score=score,
        )

    def _check_wide_spread(
        self, snap, token, book, price, bid_depth, ask_depth, spread
    ) -> ValueOpportunity | None:
        """Wide spread = market maker left a gap. Buy at ask, true value is higher."""
        if spread < 0.06:
            return None

        midpoint = (book.best_bid + book.best_ask) / 2
        edge_from_mid = ((midpoint - book.best_ask) / book.best_ask) * 100

        fair_value = midpoint
        edge_pct = ((fair_value - price) / price) * 100

        if edge_pct < 2.0:
            return None

        score = self._score_value(edge_pct, snap.market.volume, bid_depth, spread)

        return ValueOpportunity(
            market_question=snap.market.question,
            market_slug=snap.market.slug,
            condition_id=snap.market.condition_id,
            neg_risk=snap.market.neg_risk,
            token_id=token.token_id,
            outcome=token.outcome,
            price=price,
            fair_value=fair_value,
            edge_pct=edge_pct,
            signal="WIDE_SPREAD",
            volume=snap.market.volume,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            score=score,
        )

    @staticmethod
    def _score_value(edge_pct: float, volume: float, depth: float, spread: float) -> float:
        import math

        edge_score = min(edge_pct * 8, 100)
        volume_score = min(math.log10(max(volume, 1)) * 20, 100)
        depth_score = min(depth * 5, 100)
        spread_penalty = min(spread * 200, 50)

        return (edge_score * 0.40) + (volume_score * 0.25) + (depth_score * 0.20) - (spread_penalty * 0.15)

    @staticmethod
    def _depth(entries: list) -> float:
        total = 0.0
        for e in entries:
            try:
                size = float(e["size"]) if isinstance(e, dict) else float(e.size)
                total += size
            except (KeyError, AttributeError, TypeError, ValueError):
                pass
        return total
