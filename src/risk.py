"""Risk manager — auto-compounding, position limits, exposure caps, kill switch."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import Lock

from src.config import TradingConfig, trading_cfg

logger = logging.getLogger(__name__)


@dataclass
class Position:
    token_id: str
    market_slug: str
    strategy: str
    side: str
    size: float
    entry_price: float
    timestamp: float = field(default_factory=time.time)

    @property
    def cost_basis(self) -> float:
        return self.size * self.entry_price


class RiskManager:
    """Tracks positions, compounds winnings, and enforces risk limits."""

    def __init__(self, cfg: TradingConfig = trading_cfg) -> None:
        self._cfg = cfg
        self._positions: dict[str, Position] = {}
        self._realized_pnl: float = 0.0
        self._peak_equity: float = cfg.bankroll_usdc
        self._lock = Lock()
        self._killed = False
        self._trade_log: list[dict] = []

    # -- Auto-compounding ---------------------------------------------------------

    @property
    def effective_bankroll(self) -> float:
        """Current bankroll = initial + all realized gains. Grows as you win."""
        return max(self._cfg.bankroll_usdc + self._realized_pnl, 0.01)

    @property
    def max_position_usdc(self) -> float:
        return self.effective_bankroll * (self._cfg.max_position_pct / 100)

    @property
    def max_total_exposure_usdc(self) -> float:
        return self.effective_bankroll * (self._cfg.max_total_exposure_pct / 100)

    @property
    def max_drawdown_usdc(self) -> float:
        return self.effective_bankroll * (self._cfg.max_drawdown_pct / 100)

    # -- Queries ------------------------------------------------------------------

    @property
    def is_killed(self) -> bool:
        return self._killed

    @property
    def total_exposure(self) -> float:
        with self._lock:
            return sum(p.cost_basis for p in self._positions.values())

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def current_equity(self) -> float:
        return self.effective_bankroll

    @property
    def drawdown(self) -> float:
        return max(0.0, self._peak_equity - self.current_equity)

    @property
    def position_count(self) -> int:
        with self._lock:
            return len(self._positions)

    @property
    def win_count(self) -> int:
        return sum(1 for t in self._trade_log if t["pnl"] > 0)

    @property
    def loss_count(self) -> int:
        return sum(1 for t in self._trade_log if t["pnl"] <= 0)

    @property
    def win_rate(self) -> float:
        total = len(self._trade_log)
        return (self.win_count / total * 100) if total > 0 else 0.0

    def get_positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    def has_position(self, token_id: str) -> bool:
        with self._lock:
            return token_id in self._positions

    def has_market_position(self, market_slug: str) -> bool:
        with self._lock:
            return any(p.market_slug == market_slug for p in self._positions.values())

    # -- Pre-trade checks ---------------------------------------------------------

    def can_trade(self, cost: float) -> tuple[bool, str]:
        if self._killed:
            return False, "KILL SWITCH ACTIVE"

        if cost > self.max_position_usdc:
            return False, f"Cost ${cost:.2f} > max position ${self.max_position_usdc:.2f}"

        if self.total_exposure + cost > self.max_total_exposure_usdc:
            return False, (
                f"Exposure ${self.total_exposure + cost:.2f} > "
                f"max ${self.max_total_exposure_usdc:.2f}"
            )

        if self.drawdown >= self.max_drawdown_usdc:
            self._killed = True
            return False, f"KILL SWITCH: drawdown ${self.drawdown:.2f}"

        return True, "OK"

    def compute_position_size(self, price: float) -> float:
        """Size based on current compounded bankroll."""
        remaining = self.max_total_exposure_usdc - self.total_exposure
        max_spend = min(self.max_position_usdc, remaining)

        if max_spend <= 0 or price <= 0:
            return 0.0

        return round(max_spend / price, 2)

    # -- Post-trade bookkeeping ---------------------------------------------------

    def record_entry(
        self, token_id: str, market_slug: str, strategy: str, side: str, size: float, price: float
    ) -> None:
        with self._lock:
            self._positions[token_id] = Position(
                token_id=token_id,
                market_slug=market_slug,
                strategy=strategy,
                side=side,
                size=size,
                entry_price=price,
            )
        logger.info(
            "ENTRY [%s] %s %.2f @ $%.4f ($%.2f) on %s",
            strategy, side, size, price, size * price, market_slug,
        )

    def record_exit(self, token_id: str, exit_price: float) -> float:
        with self._lock:
            pos = self._positions.pop(token_id, None)

        if pos is None:
            return 0.0

        pnl = (exit_price - pos.entry_price) * pos.size
        self._realized_pnl += pnl
        self._peak_equity = max(self._peak_equity, self.current_equity)
        self._trade_log.append({
            "token_id": token_id,
            "market_slug": pos.market_slug,
            "strategy": pos.strategy,
            "pnl": pnl,
            "entry": pos.entry_price,
            "exit": exit_price,
            "size": pos.size,
        })

        logger.info(
            "EXIT  [%s] pnl=$%+.4f (%.4f->%.4f x%.2f) bankroll=$%.2f on %s",
            pos.strategy, pnl, pos.entry_price, exit_price, pos.size,
            self.effective_bankroll, pos.market_slug,
        )
        return pnl

    def reset_kill_switch(self) -> None:
        self._killed = False
        logger.warning("Kill switch manually reset")
