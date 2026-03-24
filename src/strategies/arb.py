"""Intra-market and multi-outcome arbitrage strategies.

Intra-market arb: if best_ask(YES) + best_ask(NO) < 1.00, buy both for
guaranteed profit equal to (1.00 - total_cost) per share.

Multi-outcome arb: for markets with N outcomes, if sum of best asks < 1.00,
buy all outcomes for the same guaranteed spread.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import TradingConfig, trading_cfg
from src.scanner import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class ArbOpportunity:
    market_question: str
    market_slug: str
    condition_id: str
    neg_risk: bool
    token_ids: list[str]
    ask_prices: list[float]
    total_cost: float
    spread_pct: float

    @property
    def profit_per_share(self) -> float:
        return 1.0 - self.total_cost

    def __str__(self) -> str:
        return (
            f"ARB  {self.spread_pct:+.2f}%  cost={self.total_cost:.4f}  "
            f"profit/share={self.profit_per_share:.4f}  "
            f"{self.market_question[:60]}"
        )


class ArbitrageStrategy:
    """Detects arbitrage opportunities across market outcomes."""

    def __init__(self, cfg: TradingConfig = trading_cfg) -> None:
        self._cfg = cfg

    def scan(self, snapshots: list[MarketSnapshot]) -> list[ArbOpportunity]:
        opportunities: list[ArbOpportunity] = []

        for snap in snapshots:
            opp = self._check_market(snap)
            if opp is not None:
                opportunities.append(opp)

        opportunities.sort(key=lambda o: o.spread_pct, reverse=True)
        return opportunities

    def _check_market(self, snap: MarketSnapshot) -> ArbOpportunity | None:
        market = snap.market

        if len(market.tokens) < 2:
            return None

        ask_prices: list[float] = []
        token_ids: list[str] = []

        for token in market.tokens:
            book = snap.books.get(token.token_id)
            if book is None or book.best_ask is None:
                return None
            ask_prices.append(book.best_ask)
            token_ids.append(token.token_id)

        total_cost = sum(ask_prices)

        if total_cost >= 1.0:
            return None

        spread_pct = (1.0 - total_cost) * 100

        if spread_pct < self._cfg.min_arb_spread_pct:
            return None

        return ArbOpportunity(
            market_question=market.question,
            market_slug=market.slug,
            condition_id=market.condition_id,
            neg_risk=market.neg_risk,
            token_ids=token_ids,
            ask_prices=ask_prices,
            total_cost=total_cost,
            spread_pct=spread_pct,
        )
