from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class PolymarketConfig:
    host: str = "https://clob.polymarket.com"
    gamma_host: str = "https://gamma-api.polymarket.com"
    chain_id: int = 137
    private_key: str = field(default_factory=lambda: os.environ["POLYMARKET_PRIVATE_KEY"])
    signature_type: int = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
    funder: str = os.getenv("POLYMARKET_FUNDER", "")


@dataclass(frozen=True)
class TradingConfig:
    bankroll_usdc: float = float(os.getenv("BANKROLL_USDC", "10.0"))

    # Endgame thresholds
    min_endgame_probability: float = float(os.getenv("MIN_ENDGAME_PROB", "0.92"))
    max_endgame_price: float = float(os.getenv("MAX_ENDGAME_PRICE", "0.98"))
    max_days_to_resolution: int = int(os.getenv("MAX_DAYS_TO_RESOLUTION", "14"))
    min_market_volume: float = float(os.getenv("MIN_MARKET_VOLUME", "1000.0"))
    max_trades_per_cycle: int = int(os.getenv("MAX_TRADES_PER_CYCLE", "3"))

    # Risk limits — aggressive for small bankroll
    max_position_pct: float = float(os.getenv("MAX_POSITION_PCT", "20.0"))
    max_total_exposure_pct: float = float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "80.0"))
    max_drawdown_pct: float = float(os.getenv("MAX_DRAWDOWN_PCT", "30.0"))

    # Scanning
    scan_interval_seconds: float = float(os.getenv("SCAN_INTERVAL_SECONDS", "5.0"))
    markets_refresh_seconds: float = float(os.getenv("MARKETS_REFRESH_SECONDS", "120.0"))
    max_markets: int = int(os.getenv("MAX_MARKETS", "500"))

    tick_size: str = os.getenv("TICK_SIZE", "0.01")

    # Execution
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() == "true"

    @property
    def max_position_usdc(self) -> float:
        return self.bankroll_usdc * (self.max_position_pct / 100)

    @property
    def max_total_exposure_usdc(self) -> float:
        return self.bankroll_usdc * (self.max_total_exposure_pct / 100)

    @property
    def max_drawdown_usdc(self) -> float:
        return self.bankroll_usdc * (self.max_drawdown_pct / 100)


polymarket_cfg = PolymarketConfig()
trading_cfg = TradingConfig()
