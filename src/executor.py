"""Order executor — bridges strategy signals to actual order placement."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.client import PolymarketClient
from src.config import TradingConfig, trading_cfg
from src.risk import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    opportunity_type: str
    market_slug: str
    tokens_bought: list[str]
    total_cost: float
    expected_profit: float
    message: str


class Executor:
    """Sizes and places orders for detected opportunities."""

    def __init__(
        self,
        client: PolymarketClient,
        risk: RiskManager,
        cfg: TradingConfig = trading_cfg,
    ) -> None:
        self._client = client
        self._risk = risk
        self._cfg = cfg

    def execute(self, opp: Any, strategy_name: str) -> ExecutionResult:
        """Universal executor for any opportunity type."""
        if self._risk.has_position(opp.token_id):
            return self._skip(opp, strategy_name, "Already have position on this token")

        if self._risk.has_market_position(opp.market_slug):
            return self._skip(opp, strategy_name, "Already have position on this market")

        max_shares = self._risk.compute_position_size(opp.price)
        if max_shares <= 0:
            return self._skip(opp, strategy_name, "Position sizing returned 0")

        total_cost = opp.price * max_shares
        ok, reason = self._risk.can_trade(total_cost)
        if not ok:
            return self._skip(opp, strategy_name, reason)

        if self._cfg.dry_run:
            return self._dry_run_result(opp, strategy_name, max_shares, total_cost)

        try:
            self._client.place_limit_buy(
                token_id=opp.token_id,
                price=opp.price,
                size=max_shares,
                tick_size=self._cfg.tick_size,
                neg_risk=opp.neg_risk,
            )
            self._risk.record_entry(
                token_id=opp.token_id,
                market_slug=opp.market_slug,
                strategy=strategy_name,
                side="BUY",
                size=max_shares,
                price=opp.price,
            )
        except Exception as exc:
            logger.error("[%s] Failed buy on %s: %s", strategy_name, opp.market_slug, exc)
            return ExecutionResult(
                success=False,
                opportunity_type=strategy_name,
                market_slug=opp.market_slug,
                tokens_bought=[],
                total_cost=0.0,
                expected_profit=0.0,
                message=str(exc),
            )

        expected_profit = opp.profit_per_share * max_shares
        return ExecutionResult(
            success=True,
            opportunity_type=strategy_name,
            market_slug=opp.market_slug,
            tokens_bought=[opp.token_id],
            total_cost=total_cost,
            expected_profit=expected_profit,
            message=f"{opp.outcome} @ ${opp.price:.2f} x{max_shares:.1f}",
        )

    # -- Helpers ------------------------------------------------------------------

    @staticmethod
    def _skip(opp: Any, strategy_name: str, reason: str) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            opportunity_type=strategy_name,
            market_slug=opp.market_slug,
            tokens_bought=[],
            total_cost=0.0,
            expected_profit=0.0,
            message=f"Skip: {reason}",
        )

    @staticmethod
    def _dry_run_result(opp: Any, strategy_name: str, shares: float, cost: float) -> ExecutionResult:
        profit = opp.profit_per_share * shares
        logger.info(
            "[DRY RUN][%s] %.1f shares @ $%.2f ($%.2f) profit=$%.2f on %s",
            strategy_name, shares, opp.price, cost, profit, opp.market_slug,
        )
        return ExecutionResult(
            success=True,
            opportunity_type=strategy_name,
            market_slug=opp.market_slug,
            tokens_bought=[],
            total_cost=cost,
            expected_profit=profit,
            message=f"[DRY] {shares:.1f}sh @ ${opp.price:.2f} +${profit:.2f}",
        )
