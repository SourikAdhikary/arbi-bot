"""Main orchestrator — scan, strategize across 3 engines, execute top picks."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime

from src.client import PolymarketClient
from src.config import trading_cfg
from src.dashboard import Dashboard
from src.executor import Executor
from src.risk import RiskManager
from src.scanner import MarketScanner
from src.strategies.correlation import CorrelationStrategy
from src.strategies.endgame import EndgameStrategy
from src.strategies.value import ValueStrategy

_log_file = f"logs/arbi-bot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(_log_file), logging.StreamHandler()],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class ArbiBot:
    """Core event loop: scan -> 3 strategies -> execute top picks -> compound."""

    def __init__(self) -> None:
        self._client = PolymarketClient()
        self._risk = RiskManager()
        self._scanner = MarketScanner(self._client)
        self._endgame = EndgameStrategy()
        self._value = ValueStrategy()
        self._correlation = CorrelationStrategy()
        self._executor = Executor(self._client, self._risk)
        self._dashboard = Dashboard(self._risk)
        self._running = True
        self._scan_count = 0

    async def run(self) -> None:
        cfg = trading_cfg
        logger.info(
            "ArbiBot starting | bankroll=$%.2f | dry_run=%s | "
            "strategies=endgame+value+correlation | "
            "max_position=$%.2f (%.0f%%) | max_exposure=$%.2f (%.0f%%) | "
            "max_trades/cycle=%d | markets=%d | auto_compound=ON",
            cfg.bankroll_usdc, cfg.dry_run,
            cfg.max_position_usdc, cfg.max_position_pct,
            cfg.max_total_exposure_usdc, cfg.max_total_exposure_pct,
            cfg.max_trades_per_cycle, cfg.max_markets,
        )

        self._client.connect()
        logger.info("Polymarket client connected")

        live = self._dashboard.start()
        with live:
            while self._running:
                try:
                    await self._tick()
                except KeyboardInterrupt:
                    break
                except Exception:
                    logger.exception("Error in main loop")

                await asyncio.sleep(cfg.scan_interval_seconds)

        logger.info("ArbiBot stopped | final_bankroll=$%.2f | pnl=$%+.2f | trades=%d (W:%d L:%d %.0f%%)",
                     self._risk.effective_bankroll, self._risk.realized_pnl,
                     self._risk.win_count + self._risk.loss_count,
                     self._risk.win_count, self._risk.loss_count, self._risk.win_rate)

    async def _tick(self) -> None:
        if self._risk.is_killed:
            logger.warning("Kill switch active — skipping tick")
            return

        snapshots = await self._scanner.scan_all()
        self._scan_count += 1

        endgame_opps = self._endgame.scan(snapshots)
        value_opps = self._value.scan(snapshots)
        corr_opps = self._correlation.scan(snapshots)

        logger.info(
            "Tick #%d | markets=%d | bankroll=$%.2f | "
            "endgame=%d value=%d correlation=%d",
            self._scan_count, len(snapshots), self._risk.effective_bankroll,
            len(endgame_opps), len(value_opps), len(corr_opps),
        )

        for opp in endgame_opps[:3]:
            logger.info("  %s", opp)
        for opp in value_opps[:3]:
            logger.info("  %s", opp)
        for opp in corr_opps[:3]:
            logger.info("  %s", opp)

        budget = trading_cfg.max_trades_per_cycle
        executions = []

        endgame_budget = max(1, budget // 2)
        value_budget = max(1, (budget - endgame_budget) // 2 + (budget - endgame_budget) % 2)
        corr_budget = max(1, budget - endgame_budget - value_budget)

        for opp in endgame_opps[:endgame_budget]:
            if self._risk.is_killed:
                break
            result = self._executor.execute(opp, "endgame")
            executions.append(result)

        for opp in value_opps[:value_budget]:
            if self._risk.is_killed:
                break
            result = self._executor.execute(opp, "value")
            executions.append(result)

        for opp in corr_opps[:corr_budget]:
            if self._risk.is_killed:
                break
            result = self._executor.execute(opp, "correlation")
            executions.append(result)

        self._dashboard.update(
            endgame_opps=endgame_opps,
            value_opps=value_opps,
            corr_opps=corr_opps,
            executions=executions if executions else None,
            scan_count=self._scan_count,
            markets_count=len(self._scanner.markets),
        )

    def stop(self) -> None:
        self._running = False


def main() -> None:
    bot = ArbiBot()

    def handle_signal(sig: int, _frame: object) -> None:
        if not bot._running:
            return
        logger.info("Received signal %d, shutting down...", sig)
        bot.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
