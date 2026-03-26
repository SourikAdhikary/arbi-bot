# Arbi-Bot — Polymarket Arbitrage Trading Bot

Automated trading bot that scans Polymarket prediction markets for arbitrage and endgame sniping opportunities.

## Strategies

**Intra-Market Arbitrage** — When the sum of best-ask prices across all outcomes is less than $1.00, buy every outcome for a guaranteed profit. The bot scans all active markets every few seconds for these mispricings.

**Endgame Sniping** — Buy near-certain outcomes (95-98% probability) close to market resolution for outsized annualized returns.

## Prerequisites

- **Python 3.10+** — for the strategy bot
- **Rust 1.75+** — for the arb engine (`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)

## Setup

```bash
# Clone and enter the project
cd arbi-bot

# Create virtual environment and install Python deps
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Build the Rust arb engine
cd arb-engine && cargo build --release && cd ..

# Configure
cp .env.example .env
# Edit .env with your private key and parameters
```

## Configuration

All settings are in `.env` (see `.env.example` for the full template). Key parameters:

**Credentials**

| Variable | Default | Description |
|---|---|---|
| `POLYMARKET_PRIVATE_KEY` | — | Your Polygon wallet private key |
| `POLYMARKET_SIGNATURE_TYPE` | 0 | Signature type for order signing |
| `POLYMARKET_FUNDER` | — | Funder address (optional) |
| `BANKROLL_USDC` | 10.0 | Your USDC bankroll |

**Endgame Strategy**

| Variable | Default | Description |
|---|---|---|
| `MIN_ENDGAME_PROB` | 0.92 | Minimum outcome probability to consider |
| `MAX_ENDGAME_PRICE` | 0.98 | Maximum price to pay per share |
| `MAX_DAYS_TO_RESOLUTION` | 14 | Only target markets resolving within N days |
| `MIN_MARKET_VOLUME` | 1000 | Skip markets with less than $N total volume |
| `MAX_TRADES_PER_CYCLE` | 3 | Max trades executed per scan cycle |

**Risk Limits**

| Variable | Default | Description |
|---|---|---|
| `MAX_POSITION_PCT` | 20.0 | Max single position as % of bankroll |
| `MAX_TOTAL_EXPOSURE_PCT` | 80.0 | Max total open exposure as % of bankroll |
| `MAX_DRAWDOWN_PCT` | 30.0 | Kill switch drawdown threshold (%) |

**Scanning**

| Variable | Default | Description |
|---|---|---|
| `SCAN_INTERVAL_SECONDS` | 5.0 | Seconds between scan cycles |
| `MARKETS_REFRESH_SECONDS` | 120.0 | Seconds between full market list refreshes |
| `MAX_MARKETS` | 500 | Max markets to scan (sorted by volume) |
| `TICK_SIZE` | 0.01 | Order book tick size |

**Safety**

| Variable | Default | Description |
|---|---|---|
| `DRY_RUN` | true | Simulate trades without placing orders |

## Running

The easiest way to run the full system is with the launcher script, which starts both bots and handles graceful shutdown on Ctrl+C:

```bash
./run.sh
```

This will build the Rust engine (if not already built), then launch the Python strategy bot and the Rust arb engine side by side.

To run the components individually:

```bash
# Python strategy bot only
python -m src.main

# Rust arb engine only
cd arb-engine && cargo run --release
```

> Always start with `DRY_RUN=true` (the default). Set to `false` in `.env` only when you're ready to trade real money.

The Python bot launches a live terminal dashboard showing:
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

### Python Bot (`src/`)

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

### Rust Arb Engine (`arb-engine/`)

A high-performance arbitrage engine written in Rust. It connects to Polymarket via WebSocket, maintains real-time order books for all active binary markets, and detects arbitrage opportunities when the combined ask price of YES + NO tokens falls below $1.00.

```
arb-engine/
├── src/
│   ├── main.rs        # Entry point — orchestrates the arb loop
│   ├── config.rs      # Environment-driven configuration
│   ├── types.rs       # Core data structures (OrderBook, MarketPair, ArbOpportunity)
│   ├── scanner.rs     # ArbScanner — detects mispricings across order books
│   ├── executor.rs    # ArbExecutor — position sizing, risk limits, trade execution
│   ├── ws.rs          # WebSocket client with auto-reconnect and keepalive
│   └── markets.rs     # Gamma API client — fetches binary market metadata
└── Cargo.toml
```

**How it works:**

1. Fetches all active binary markets from the Gamma API (up to 500 markets, sorted by volume)
2. Subscribes to real-time order book updates via WebSocket for YES/NO tokens
3. Scans for arb opportunities every 100 order book updates
4. Executes trades when spread exceeds the minimum threshold, subject to risk limits

**Key design choices:**

- Prices stored as `u64` keys (scaled by 1,000,000) in `BTreeMap` for efficient sorted order book lookups
- Tokio async runtime for concurrent WebSocket streaming and market scanning
- Auto-reconnecting WebSocket with 2-second retry and 10-second keepalive pings

**Configuration** (environment variables):

| Variable | Default | Description |
|---|---|---|
| `ARB_WS_URL` | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | WebSocket endpoint |
| `ARB_CLOB_URL` | `https://clob.polymarket.com` | Trading API endpoint |
| `ARB_GAMMA_URL` | `https://gamma-api.polymarket.com` | Market metadata API |
| `ARB_MIN_SPREAD_PCT` | 0.5 | Minimum spread to trade (%) |
| `ARB_MAX_POSITION_USDC` | 2.0 | Max USDC per single arb |
| `ARB_MAX_EXPOSURE_USDC` | 8.0 | Max total concurrent exposure |

**Running the engine:**

```bash
cd arb-engine
cargo run --release
```

> **Note:** Trade execution is currently dry-run only. Live trading requires implementing EIP-712 order signing against the CLOB API.

## License

[Apache License 2.0](LICENSE)

## Disclaimer

This is a trading tool, not a guaranteed money maker. Prediction markets are competitive. Always start with small amounts, use dry-run mode extensively, and never risk more than you can afford to lose.
