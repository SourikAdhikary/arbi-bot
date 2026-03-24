# Arbi-Bot — Polymarket Arbitrage Trading Bot

Automated trading bot that scans Polymarket prediction markets for arbitrage and endgame sniping opportunities.

## Strategies

**Intra-Market Arbitrage** — When the sum of best-ask prices across all outcomes is less than $1.00, buy every outcome for a guaranteed profit. The bot scans all active markets every few seconds for these mispricings.

**Endgame Sniping** — Buy near-certain outcomes (95-98% probability) close to market resolution for outsized annualized returns.

## Setup

```bash
# Clone and enter the project
cd arbi-bot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your private key and parameters
```

## Configuration

All settings are in `.env`. Key parameters:

| Variable | Default | Description |
|---|---|---|
| `POLYMARKET_PRIVATE_KEY` | — | Your Polygon wallet private key |
| `BANKROLL_USDC` | 100 | Your USDC bankroll |
| `MIN_ARB_SPREAD_PCT` | 1.5 | Minimum spread to trade (%) |
| `MAX_POSITION_PCT` | 2.0 | Max single position as % of bankroll |
| `MAX_DRAWDOWN_PCT` | 10.0 | Kill switch drawdown threshold (%) |
| `DRY_RUN` | true | Simulate trades without placing orders |

## Running

```bash
# Always start in dry-run mode first
python -m src.main

# When confident, set DRY_RUN=false in .env
```

The bot launches a live terminal dashboard showing:
- Current equity, exposure, and P&L
- Detected arbitrage opportunities ranked by spread
- Endgame sniping candidates ranked by annualized return
- Recent execution history

## Risk Management

- **Position limits**: No single trade exceeds `MAX_POSITION_PCT` of bankroll
- **Exposure cap**: Total open exposure capped at `MAX_TOTAL_EXPOSURE_PCT`
- **Kill switch**: Trading halts automatically if drawdown exceeds threshold
- **Fees**: Polymarket charges ~2% on winnings — `MIN_ARB_SPREAD_PCT` defaults to 1.5% to ensure profitability after fees

## Architecture

```
src/
├── main.py            # Orchestrator — async event loop
├── config.py          # Environment-driven configuration
├── client.py          # Polymarket CLOB + Gamma API wrapper
├── scanner.py         # Market discovery and order book snapshots
├── executor.py        # Order sizing and placement
├── risk.py            # Position tracking, limits, kill switch
├── dashboard.py       # Rich terminal dashboard
└── strategies/
    ├── arb.py         # Intra-market / multi-outcome arbitrage
    └── endgame.py     # Near-resolution sniping
```

## Disclaimer

This is a trading tool, not a guaranteed money maker. Prediction markets are competitive. Always start with small amounts, use dry-run mode extensively, and never risk more than you can afford to lose.
