"""Cross-market correlation — exploit lagging reprices across related markets.

When one market moves, related markets often take time to catch up.
This strategy groups markets by keyword/topic and detects when one
outcome in a group has moved while a correlated outcome hasn't repriced yet.

Examples:
  - "Bitcoin above 70k March" moves to 0.80 → "Bitcoin above 65k March"
    should be higher than its current 0.75 → buy it
  - "Trump says X this week" resolves YES → "Trump says Y this week"
    on a related topic may be underpriced
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass

from src.config import TradingConfig, trading_cfg
from src.scanner import MarketSnapshot

logger = logging.getLogger(__name__)

CORRELATION_GROUPS = [
    (r"bitcoin|btc", "crypto_btc"),
    (r"ethereum|eth\b", "crypto_eth"),
    (r"solana|sol\b", "crypto_sol"),
    (r"xrp\b", "crypto_xrp"),
    (r"trump.*truth\s*social|trump.*post", "trump_truth"),
    (r"trump.*say|trump.*said", "trump_speech"),
    (r"temperature.*nyc|temperature.*new\s*york", "weather_nyc"),
    (r"temperature.*chicago", "weather_chicago"),
    (r"temperature.*miami", "weather_miami"),
    (r"temperature.*paris", "weather_paris"),
    (r"temperature.*london", "weather_london"),
    (r"temperature.*munich", "weather_munich"),
    (r"russia.*enter|russia.*capture", "russia_ukraine"),
    (r"s&p\s*500|spx\b|spy\b", "index_sp500"),
    (r"nasdaq|ndx\b|qqq\b", "index_nasdaq"),
    (r"oscars?\b", "oscars"),
    (r"ncaa\b|march\s*madness", "ncaa"),
    (r"nba\b", "nba"),
    (r"masters\s*tournament", "golf_masters"),
]


@dataclass
class CorrelationOpportunity:
    market_question: str
    market_slug: str
    condition_id: str
    neg_risk: bool
    token_id: str
    outcome: str
    price: float
    group: str
    group_avg_price: float
    leader_price: float
    lag_pct: float
    volume: float
    score: float

    @property
    def profit_per_share(self) -> float:
        return max(self.group_avg_price - self.price, 0.01)

    def __str__(self) -> str:
        return (
            f"CORR  score={self.score:.1f}  lag={self.lag_pct:+.1f}%  "
            f"price=${self.price:.2f}  group_avg=${self.group_avg_price:.2f}  "
            f"group={self.group}  {self.market_question[:35]}"
        )


class CorrelationStrategy:
    """Detects correlated markets where one is lagging behind the group."""

    def __init__(self, cfg: TradingConfig = trading_cfg) -> None:
        self._cfg = cfg
        self._compiled = [(re.compile(pat, re.IGNORECASE), name) for pat, name in CORRELATION_GROUPS]

    def scan(self, snapshots: list[MarketSnapshot]) -> list[CorrelationOpportunity]:
        groups = self._build_groups(snapshots)
        opportunities: list[CorrelationOpportunity] = []

        for group_name, members in groups.items():
            if len(members) < 2:
                continue
            opps = self._find_laggards(group_name, members)
            opportunities.extend(opps)

        opportunities.sort(key=lambda o: o.score, reverse=True)
        return opportunities

    def _classify(self, question: str) -> str | None:
        for pattern, name in self._compiled:
            if pattern.search(question):
                return name
        return None

    def _build_groups(
        self, snapshots: list[MarketSnapshot]
    ) -> dict[str, list[tuple[MarketSnapshot, str, float]]]:
        """Group snapshots by correlation topic. Each entry is (snap, token_id, yes_price)."""
        groups: dict[str, list[tuple[MarketSnapshot, str, float]]] = defaultdict(list)

        for snap in snapshots:
            group = self._classify(snap.market.question)
            if group is None:
                continue

            if snap.market.volume < self._cfg.min_market_volume:
                continue

            for token in snap.market.tokens:
                book = snap.books.get(token.token_id)
                if book is None or book.best_ask is None:
                    continue

                price = book.best_ask
                if price < 0.10 or price > 0.95:
                    continue

                groups[group].append((snap, token.token_id, price))

        return groups

    def _find_laggards(
        self,
        group_name: str,
        members: list[tuple[MarketSnapshot, str, float]],
    ) -> list[CorrelationOpportunity]:
        prices = [p for _, _, p in members]
        avg_price = sum(prices) / len(prices)
        leader_price = max(prices)

        results: list[CorrelationOpportunity] = []

        for snap, token_id, price in members:
            lag_pct = ((avg_price - price) / price) * 100

            if lag_pct < 5.0:
                continue

            score = self._score(lag_pct, snap.market.volume, len(members))

            token = next((t for t in snap.market.tokens if t.token_id == token_id), None)
            if token is None:
                continue

            results.append(
                CorrelationOpportunity(
                    market_question=snap.market.question,
                    market_slug=snap.market.slug,
                    condition_id=snap.market.condition_id,
                    neg_risk=snap.market.neg_risk,
                    token_id=token_id,
                    outcome=token.outcome,
                    price=price,
                    group=group_name,
                    group_avg_price=avg_price,
                    leader_price=leader_price,
                    lag_pct=lag_pct,
                    volume=snap.market.volume,
                    score=score,
                )
            )

        return results

    @staticmethod
    def _score(lag_pct: float, volume: float, group_size: int) -> float:
        import math

        lag_score = min(lag_pct * 5, 100)
        volume_score = min(math.log10(max(volume, 1)) * 20, 100)
        group_score = min(group_size * 10, 50)

        return (lag_score * 0.50) + (volume_score * 0.30) + (group_score * 0.20)
