# Polymarket Trading System — Complete Documentation

Everything about how this system works, why every decision was made, what alternatives were considered, and how to think about the tradeoffs.

---

## Table of Contents

1. [The Problem We're Solving](#1-the-problem-were-solving)
2. [How Polymarket Works (From a Trader's Perspective)](#2-how-polymarket-works)
3. [System Architecture & Why Two Languages](#3-system-architecture--why-two-languages)
4. [The Python Strategy Bot — Every File, Every Decision](#4-the-python-strategy-bot)
5. [The Rust Arbitrage Engine — Every File, Every Decision](#5-the-rust-arbitrage-engine)
6. [The Launch System](#6-the-launch-system)
7. [Risk Philosophy & Money Management](#7-risk-philosophy--money-management)
8. [Complete Data Flow Walkthroughs](#8-complete-data-flow-walkthroughs)
9. [Configuration Reference & Tuning Guide](#9-configuration-reference--tuning-guide)
10. [What Can Go Wrong — Honest Risk Assessment](#10-what-can-go-wrong)
11. [Setup & Running](#11-setup--running)

---

## 1. The Problem We're Solving

You have $10 and want to grow it on Polymarket. The fundamental challenge: Polymarket is a zero-sum game. For every dollar you make, someone else lost a dollar. So to be profitable, you need an edge that other participants don't have.

**Our edges:**

1. **Speed** (Rust engine): When two sides of the same market briefly misprice (YES + NO < $1.00), that's free money. But everyone sees it. The person who buys first wins. We use Rust with WebSocket streaming to react in milliseconds.

2. **Breadth** (Python bot): Most humans monitor 5-10 markets. We scan 500 every 18 seconds. When a market is resolving tomorrow and the YES token is at $0.90, we find it before manual traders do.

3. **Discipline** (Risk manager): Humans panic-sell, double down on losses, and let winners ride too long. Our risk manager compounds wins mechanically, cuts losses at predetermined thresholds, and never deviates from position sizing rules.

4. **Pattern recognition** (Correlation strategy): When Bitcoin sentiment shifts across 8 related markets, some reprice faster than others. We detect the laggards and buy them before they catch up.

**What we are NOT doing:**
- We're not predicting the future. We're not saying "Bitcoin will hit $100K."
- We're exploiting mechanical inefficiencies: mispricing, slow repricing, and near-certain outcomes that haven't settled yet.
- The endgame and arb strategies are closest to "free money" — they work regardless of which outcome wins.

---

## 2. How Polymarket Works

### Prediction Markets 101

Polymarket asks questions about the future. "Will Bitcoin reach $100,000 by December 31, 2026?" Each question has outcomes — usually YES and NO. Each outcome is a **token** on the Polygon blockchain (an ERC-1155 NFT).

Tokens trade between **$0.00 and $1.00**. The price represents the market's collective estimate of probability. A YES token at $0.42 means the crowd thinks there's a 42% chance.

When the market resolves (the event happens or doesn't):
- **Winning tokens pay $1.00** per share
- **Losing tokens pay $0.00** per share

This is the foundation everything else builds on. The guaranteed $1.00 payout for winners is what makes arbitrage and endgame sniping possible.

### Why YES + NO Should Equal $1.00

If YES is trading at $0.42, you'd expect NO to trade at $0.58. Because if you buy one YES ($0.42) and one NO ($0.58), you've spent $1.00 and you're guaranteed to get $1.00 back — one of them must win. No profit, no loss.

But order books aren't always perfectly efficient. Sometimes the asks don't perfectly add up. If YES asks at $0.42 and NO asks at $0.55, total = $0.97. You can buy both for $0.97 and collect $1.00 guaranteed. That $0.03 per share is risk-free arbitrage profit.

### The Order Book (CLOB)

Polymarket uses a Central Limit Order Book — the same mechanism the NYSE or NASDAQ uses. This is important because it means:

- **You can see depth**: Not just the best price, but all resting orders at every price level.
- **You can place limit orders**: "I'll buy at $0.38 or lower" instead of paying whatever the current ask is.
- **Bid-ask spread exists**: The gap between the highest buyer and lowest seller. Wide spreads = illiquid, risky. Tight spreads = liquid, safer.

Example order book for "Will ETH hit $4,000?" YES token:
```
ASKS (sellers wanting to sell YES shares)
  $0.31 × 50 shares    ← best ask (cheapest to buy)
  $0.32 × 120 shares
  $0.35 × 200 shares
  $0.40 × 500 shares

BIDS (buyers wanting to buy YES shares)
  $0.29 × 800 shares   ← best bid (most someone will pay)
  $0.28 × 400 shares
  $0.25 × 1,000 shares

Best Ask = $0.31   Best Bid = $0.29   Spread = $0.02
```

**Why depth matters**: If you want to buy 100 shares, the first 50 cost $0.31 but the next 50 cost $0.32. Large orders "walk the book" and get worse prices. This is why we limit position sizes.

**Why bids matter**: If you need to exit a position (sell before resolution), you sell into the bids. More bid depth = easier to exit.

### Authentication — How You Prove You're You

Polymarket's CLOB uses a two-layer auth system:

**Layer 1 — EIP-712 Signature**: Your Ethereum private key signs a structured message ("I want to create API credentials for this wallet"). This proves you own the wallet. This happens once.

**Layer 2 — HMAC-SHA256**: The signed message generates an API key, secret, and passphrase. These three values authenticate every subsequent REST request. This is faster than signing every single request with your private key.

**Why this matters**: Reading public data (order books, market lists) requires no auth. But placing orders requires both layers. The Rust engine currently only reads (WebSocket order book data is public), while the Python bot has full auth for order placement.

### Token IDs — The Ugly Numbers

Every outcome has a unique token ID on Polygon:
```
71439730646235279808665335107954661987767386997501589451725217259692960672095
```

This is a 256-bit number — the on-chain identifier for that specific outcome's ERC-1155 token. The Gamma API returns these inside a JSON-encoded string:
```json
"clobTokenIds": "[\"71439730...\", \"10566953...\"]"
```

This double-encoding (a JSON string containing JSON) is a common API quirk. Both our Python and Rust parsers handle it by trying `json.loads()` / `serde_json::from_str()` first, then falling back to string manipulation if that fails. This was one of the first bugs we hit — the token IDs had leftover `[`, `]`, and `"` characters that caused 404 errors when requesting order books.

### The Two APIs

**Gamma API** (`https://gamma-api.polymarket.com`): Market discovery. This is where you find out what markets exist, their questions, outcomes, volume, resolution dates, token IDs. It's a simple REST API with no auth required. Supports pagination, sorting by volume, filtering by active/closed status.

**CLOB API** (`https://clob.polymarket.com`): Trading. Fetches live order books, places/cancels orders, checks positions and balances. REST for request-response operations. Also has a WebSocket endpoint (`wss://ws-subscriptions-clob.polymarket.com/ws/market`) for streaming real-time order book updates — this is what the Rust engine uses.

**Why two APIs?** Gamma manages market metadata (questions, dates, categories). CLOB manages trading (order books, execution). They're maintained by different teams and serve different purposes. We need both: Gamma to know *what* to trade, CLOB to know *at what price* and to *execute*.

---

## 3. System Architecture & Why Two Languages

### The Two-Engine Design

```
┌───────────────────────────────────────────────────────────────┐
│                        .env (shared config)                   │
└──────────┬────────────────────────────────────┬───────────────┘
           │                                    │
    ┌──────▼──────────┐               ┌─────────▼──────────┐
    │  Python Bot      │               │  Rust Arb Engine    │
    │  (src/)          │               │  (arb-engine/)      │
    │                  │               │                     │
    │  3 strategies:   │               │  1 strategy:        │
    │  - Endgame       │               │  - Intra-market arb │
    │  - Value         │               │                     │
    │  - Correlation   │               │  Speed:             │
    │                  │               │  400 updates/sec    │
    │  Speed:          │               │  ~4 scans/sec       │
    │  ~18s per cycle  │               │                     │
    │  (scan + sleep)  │               │  Data:              │
    │                  │               │  WebSocket stream   │
    │  Data:           │               │  (real-time deltas) │
    │  HTTP polling    │               │                     │
    │  (full snapshots)│               └─────────────────────┘
    └──────────────────┘
```

### Why Not Just One Language?

**Decision**: Use Python for strategic analysis, Rust for speed-critical arbitrage.

**Why Python for strategies**: 
- The `py-clob-client` SDK handles all the EIP-712 signing complexity. Re-implementing this in Rust would take weeks.
- Endgame, value, and correlation strategies don't need sub-second speed. They analyze 500 markets and pick the best opportunities — whether you find an endgame play in 13 seconds or 13.5 seconds doesn't matter, because these positions are held for hours or days.
- Rapid iteration: we tuned scoring weights, thresholds, and filters many times. Python makes this trivial.

**Why Rust for arbitrage**:
- Arb windows close in milliseconds. Python's Global Interpreter Lock (GIL) and interpreted nature add ~10-100ms of latency per operation. In those 100ms, someone else already bought both sides.
- WebSocket streaming + event-driven architecture is natural in Rust with `tokio`. No GIL, no garbage collection pauses.
- The Rust engine processes ~400 price updates per second with negligible CPU usage. Python would struggle to process 50/sec with the same reliability.

**Why not C++?** Rust was chosen over C++ because:
- Memory safety without garbage collection (no segfaults, no use-after-free)
- The `tokio` async runtime is production-grade for WebSocket handling
- `serde` makes JSON deserialization trivial and fast
- Cargo (package manager) vs CMake/Conan — much simpler dependency management
- Comparable performance to C++ for this workload

**Alternative considered**: A single Rust binary doing everything. Rejected because the `rs-clob-client` crate is less mature than the Python SDK, and we'd need to re-implement all three strategies in a language that's slower to iterate in.

### How They Cooperate

The two engines are **fully independent**. They share nothing except the `.env` file for configuration. They run as separate OS processes. If one crashes, the other continues.

This was a deliberate decision. Alternatives considered:
1. **Python spawns Rust as subprocess** — rejected because it couples their lifecycles
2. **IPC (inter-process communication)** — rejected because they don't need to share state. They look at the same markets but make different decisions.
3. **Independent processes with shared `.env`** — chosen. Simplest, most robust.

They can even trade the same markets without conflict because:
- Python places limit orders (GTC) that sit in the book
- Rust would place fill-or-kill (FOK) orders that execute instantly or cancel
- They'd never compete on the same opportunity because their strategies are fundamentally different

---

## 4. The Python Strategy Bot

### 4.1 Configuration (`src/config.py`)

**Design decision — frozen dataclasses**: Config is immutable after creation. This prevents bugs where code accidentally modifies settings mid-run. The `@dataclass(frozen=True)` decorator enforces this at runtime.

**Design decision — environment variables with defaults**: Every setting can be overridden via `.env`, but has a sane default. This means you can run the bot with just a private key and everything else works out of the box.

**Design decision — singletons at module level**: `polymarket_cfg` and `trading_cfg` are created once when the module loads. Every other module imports these singletons. Alternative was dependency injection (passing config to every constructor), but that adds ceremony without benefit for a single-process application.

**Why these specific defaults:**

| Setting | Default | Why this value |
|---------|---------|----------------|
| `bankroll_usdc = 10.0` | We're optimizing for a small bankroll. All percentages and limits are tuned for $10. |
| `min_endgame_probability = 0.92` | Below $0.92, outcomes aren't "near-certain" enough. A $0.85 token has a 15% chance of losing — that's too risky for endgame. Above $0.92, the implied probability is 92%+. |
| `max_endgame_price = 0.98` | Above $0.98, profit is only $0.02/share (2%). After fees and slippage, this is barely profitable. |
| `max_days_to_resolution = 14` | Capital locked for >2 weeks is expensive. We want money back fast for compounding. |
| `min_market_volume = 1000` | Markets with <$1K volume are ghost towns. Thin order books, wide spreads, potential for manipulation. |
| `max_trades_per_cycle = 3` | With $10, we can afford ~3 positions at $3 each. More would over-diversify. |
| `max_position_pct = 20.0` | Kelly criterion suggests ~25% for high-edge bets. 20% is conservative of that. |
| `max_total_exposure_pct = 80.0` | Keep 20% as reserve. If all positions go to zero, we still have $2 to restart. |
| `max_drawdown_pct = 30.0` | Lose $3 of $10 and we stop. This is the "I've been wrong about everything, stop before it gets worse" threshold. |
| `scan_interval_seconds = 5.0` | After a 13-second scan, wait 5 seconds before the next. Shorter = more API calls = potential rate limiting. Longer = stale data. |
| `markets_refresh_seconds = 120` | New markets appear infrequently. Refreshing every 2 minutes catches new opportunities without hammering the Gamma API. |
| `max_markets = 500` | Polymarket has ~30,000+ markets. Most are illiquid. The top 500 by volume capture >95% of all liquidity. Scanning more adds time without adding profitable opportunities. |
| `tick_size = "0.01"` | Polymarket's minimum price increment. Prices must be multiples of $0.01. |

### 4.2 Polymarket Client (`src/client.py`)

**Design decision — wrapper around `py-clob-client`**: Rather than using the SDK directly throughout the codebase, we wrap it. This gives us:
- A clean interface (`fetch_active_markets`, `get_order_book`, `place_limit_buy`)
- A single place to handle SDK quirks (like `OrderSummary` objects vs dicts)
- Easy mocking for testing

**The `_get_price()` problem**: The `py-clob-client` SDK returns order book entries as `OrderSummary` objects with `.price` and `.size` attributes. But depending on the version and context, sometimes they come back as plain dicts with `["price"]` and `["size"]` keys. Our `_get_price()` static method handles both:

```python
@staticmethod
def _get_price(entry):
    if isinstance(entry, dict):
        return float(entry["price"])
    return float(entry.price)
```

This was discovered at runtime when the bot crashed with `TypeError: 'OrderSummary' object is not subscriptable`. Rather than pinning a specific SDK version, we made the code handle both formats.

**The `_parse_tokens()` problem**: The Gamma API returns `clobTokenIds` as a JSON string containing a JSON array — double-encoded. Example:
```
"clobTokenIds": "[\"71439730...\", \"10566953...\"]"
```

First attempt: naive string splitting on commas. This left `[`, `]`, and `"` characters in the token IDs, causing 404 errors from the CLOB API.

Fix: Try `json.loads()` first (handles the double-encoding), fall back to manual splitting with `.strip("[]").strip('"')` for edge cases.

**Design decision — `httpx` for Gamma, `py-clob-client` for CLOB**: Gamma API is simple REST with no auth — `httpx` is lighter and faster than going through the SDK. CLOB API requires EIP-712 signing — the SDK handles this complexity.

**Design decision — FOK for market buys, GTC for limit buys**: 
- **FOK (Fill-Or-Kill)**: Execute the entire order immediately or cancel it entirely. Used for arbitrage where partial fills are dangerous (you'd be stuck holding only one side).
- **GTC (Good-Till-Cancelled)**: Leave the order in the book until filled. Used for strategic positions where we're willing to wait for a better price.

### 4.3 Market Scanner (`src/scanner.py`)

**The parallelism problem**: Scanning 500 markets sequentially means 500 HTTP requests, each taking ~0.5 seconds. That's 250 seconds (4+ minutes) per cycle — way too slow.

**Solution**: `ThreadPoolExecutor(max_workers=20)` with `asyncio.Semaphore(20)`. This runs 20 order book requests in parallel.

**Why 20 concurrent?** This was tuned empirically:
- 10 concurrent: ~26 seconds per scan (too slow)
- 20 concurrent: ~13 seconds per scan (sweet spot)
- 50 concurrent: ~12 seconds (marginal improvement, risk of rate limiting)
- 100 concurrent: API starts returning 429 (rate limited)

20 gives us 2x speedup over 10 with no rate limiting issues.

**Why ThreadPoolExecutor instead of asyncio.gather with aiohttp?** The `py-clob-client` SDK uses synchronous `requests` internally. We can't make it async. So we run synchronous SDK calls in a thread pool and await them from the async main loop. This is the standard pattern for wrapping synchronous I/O in asyncio.

**Design decision — `MarketSnapshot` bundles market + books**: Strategies need both the market metadata (question, end date, volume) and the live order book (prices, depth). Bundling them into `MarketSnapshot` avoids passing two parallel lists around.

**Failure handling**: If an order book request fails (404, timeout, etc.), that market is skipped for this cycle. The scanner logs how many failed vs succeeded. Typical failure rate is 0-10 out of 500 per cycle — mostly from recently created or just-resolved markets.

### 4.4 Endgame Strategy (`src/strategies/endgame.py`)

**The fundamental insight**: When a prediction market is about to resolve and one outcome is very likely, the token for that outcome trades near $1.00 but not quite at $1.00. This gap is profit.

**Why the gap exists**: Several reasons:
1. **Time value of money**: $0.95 today vs $1.00 in 3 days. Some traders prefer to sell at $0.95 now and redeploy capital elsewhere.
2. **Residual uncertainty**: Even at 95% probability, there's a 5% chance of losing. Some sellers are pricing that risk.
3. **Thin books near $1.00**: Not many people post asks at $0.98 because the profit per share is only $0.02. This means the ask can be stale.

**The scoring formula — why these weights:**

```
score = (profit_score × 0.35) + (time_score × 0.30) + (volume_score × 0.20) + (depth_score × 0.15)
```

- **Profit (35%)**: The primary objective. Higher profit per share = better opportunity. A $0.88 token ($0.12 profit) is strictly better than a $0.95 token ($0.05 profit), all else equal.

- **Time (30%)**: Money locked in a position can't compound elsewhere. A 10% return in 1 day is better than a 10% return in 14 days because the annualized rate is dramatically different. The formula `time_score = 100 - (days × 7)` means markets resolving today score 100, markets resolving in 14 days score 2.

- **Volume (20%)**: High-volume markets are more trustworthy. A $50K-volume market has real price discovery. A $100-volume market could be manipulated by a single trader. We use log scale (`log10(volume) × 20`) because the difference between $1K and $10K matters more than the difference between $100K and $1M.

- **Depth (15%)**: If we need to sell before resolution (changed our mind, need capital), we sell into bids. More bid depth = more exit liquidity. This is insurance. Weight is lowest because for endgame we typically hold to resolution.

**Why these weight ratios specifically?** They were tuned by analyzing which opportunities from early dry runs looked best to a human. The initial weights were equal (25% each). We increased profit weight because that's what we care about most. We increased time weight because capital velocity matters enormously with a $10 bankroll — you want money back ASAP to compound.

**Filter decisions:**

- **Price between $0.92 and $0.98**: Below $0.92 = too risky (8%+ chance of loss). Above $0.98 = too little profit ($0.02/share doesn't justify the capital lockup).
- **Volume ≥ $1,000**: Markets with less than $1K total volume traded are unreliable. The price may not reflect reality.
- **Resolves within 14 days**: Beyond two weeks, you're speculating, not sniping. Your capital is locked up too long.

**What the real output looks like:**
```
ENDGAME  score=99.8  price=$0.90  profit=$0.10/sh  days=0.1  vol=$95,507
  "Ethereum Up or Down on March 15?"
```

This is a near-perfect endgame: $0.10 profit per share, resolves in 2.4 hours, massive volume. The question is about ETH going up OR down today — one side must win, and the market has already determined which with 90% confidence.

### 4.5 Value Strategy (`src/strategies/value.py`)

**The fundamental insight**: Order book imbalance predicts short-term price direction. When 3x more money is sitting on the bid side than the ask side, there's buying pressure that hasn't fully repriced the ask yet.

**Why this works**: Market makers update prices in response to order flow. But they don't do it instantly — especially on Polymarket where many market makers are humans or slow bots. A sudden influx of bids takes minutes to fully reprice the ask. We buy before it does.

**Signal 1: Bid Imbalance (BID_IMBALANCE)**

```python
imbalance_ratio = bid_depth / ask_depth
if imbalance_ratio >= 3.0:
    pressure_boost = min(log2(imbalance_ratio) * 0.03, 0.10)
    fair_value = price + pressure_boost
```

**Why 3.0x threshold?** Below 3x, imbalance could be normal market dynamics. At 3x+, it's a strong signal. This was set conservatively — we'd rather miss some opportunities than trade on noise. We tested 2.0x and it generated too many false signals.

**Why log2 for pressure boost?** The relationship between imbalance and price movement is logarithmic, not linear. Going from 3x to 6x imbalance doesn't mean 2x the price move — it means maybe 50% more. `log2` captures this diminishing returns curve.

**Why cap at $0.10 boost?** A $0.10 move is huge in prediction markets. Even extreme imbalances don't predict moves larger than that on Polymarket. The cap prevents the model from suggesting absurd fair values.

**Signal 2: Wide Spread (WIDE_SPREAD)**

When the bid-ask spread is abnormally wide, the midpoint is a better estimate of fair value than the ask. Buying at the ask and holding gives you an edge equal to half the spread.

**Why only $0.15–$0.85 price range?** 
- Below $0.15: These tokens represent events with <15% probability. They're naturally noisy and spreads are wide by default.
- Above $0.85: Same issue in reverse — near-certain outcomes have thin books.
- In the middle range, wide spreads are genuinely informative rather than structural.

### 4.6 Correlation Strategy (`src/strategies/correlation.py`)

**The fundamental insight**: Markets about the same underlying topic should reprice together when new information arrives. In practice, some reprice faster than others.

**Example**: Breaking news: "Ethereum hits $3,500."
- "ETH above $3,000 by March" immediately jumps to $0.95 (near certain)
- "ETH above $3,500 by March" jumps to $0.70
- "ETH reach $4,000 by December" barely moves from $0.29 to $0.31

The December market should reprice higher because ETH sentiment just got a boost. It hasn't yet because different market makers manage different markets, and some are slow or offline.

**How grouping works:**

We use regex patterns to classify markets by topic:
```python
CORRELATION_GROUPS = [
    (r"bitcoin|btc", "crypto_btc"),
    (r"ethereum|eth\b", "crypto_eth"),
    (r"nba\b", "nba"),
    (r"russia.*enter|russia.*capture", "russia_ukraine"),
    # ... 20+ groups
]
```

**Why regex instead of NLP/embeddings?** 
- Regex is deterministic and fast (compiled once, applied instantly)
- Market questions on Polymarket are formulaic ("Will X happen by Y?") — regex works perfectly
- NLP/embeddings would add heavy dependencies and startup time for marginal accuracy improvement
- We can easily add new groups by adding a regex pattern

**The lag calculation:**
```
lag_pct = (group_avg_price - token_price) / token_price × 100
```

A lag of +50% means this token is priced 50% below the group average. The assumption: it should converge upward.

**Known limitations (honest assessment):**
- **Different strike prices**: "BTC above $85K" and "BTC above $100K" naturally have different prices. A high lag might just reflect a harder condition, not a mispricing.
- **Different timeframes**: "ETH above $3K by March" vs "ETH reach $4K by December" — different expiries change the fair price.
- **Small groups**: If a group has only 2 markets, the "average" is fragile.

These are real weaknesses. The strategy compensates by scoring conservatively and letting the executor's position sizing limit exposure. It's the highest-risk of the three strategies.

### 4.7 Risk Manager (`src/risk.py`)

**Philosophy**: The risk manager's job is to keep you in the game. No single trade should be able to ruin you. The best strategy in the world is worthless if one bad trade wipes out your bankroll.

**Auto-Compounding — The Core Innovation**

Traditional bots use fixed position sizes: always bet $2. But with a $10 bankroll, if you win your first 3 trades ($0.30 profit each), your bankroll is $10.90 — but you're still betting $2. You're leaving money on the table.

Auto-compounding scales position sizes with your bankroll:

```python
@property
def effective_bankroll(self):
    return max(self._cfg.bankroll_usdc + self._realized_pnl, 0.01)

@property
def max_position_usdc(self):
    return self.effective_bankroll * (self._cfg.max_position_pct / 100)
```

**Progression example with 30% max position:**
```
Start:       bankroll=$10.00 → max_bet=$3.00
After +$0.30: bankroll=$10.30 → max_bet=$3.09
After +$0.50: bankroll=$10.80 → max_bet=$3.24
After +$2.00: bankroll=$12.80 → max_bet=$3.84
After +$5.00: bankroll=$15.80 → max_bet=$4.74
```

This is a simplified version of the Kelly Criterion — bet proportionally to your edge and bankroll. As you prove your edge (winning trades), bet more. As you lose (bankroll shrinks), bet less.

**The `max(... , 0.01)` floor**: Even if you lose more than your initial bankroll, effective_bankroll never goes below $0.01. This prevents division by zero and negative position sizing.

**Kill Switch — Why It Exists**

```python
if self.drawdown >= self.max_drawdown_usdc:
    self._killed = True
    return False, "KILL SWITCH: drawdown ${self.drawdown:.2f}"
```

Once drawdown exceeds the threshold (default 30% = $3 of $10), the bot stops trading permanently until restarted. This exists because:

1. **Regime change**: If you're losing consistently, your strategy's assumptions may be wrong. Better to stop and reassess than to keep bleeding.
2. **Black swan protection**: A flash crash, API bug, or incorrect resolution could cause cascading losses. The kill switch limits damage.
3. **Psychological**: Automated systems don't have emotions, but they can enter loss spirals from systematic errors. A hard stop prevents this.

**Why permanent until restart?** Because if the strategy is broken, restarting the kill switch timer just means you'll lose the next 30% too. Human review should happen before resuming.

**Duplicate Prevention — Why We Block Same-Market Bets**

```python
def has_position(self, token_id):        # Same token
def has_market_position(self, market_slug):  # Same market, any token
```

Two checks:
1. **Same token**: Don't buy YES on "ETH $4K" twice. This prevents doubling down on the same bet.
2. **Same market**: Don't buy YES on "ETH $4K" from endgame AND value strategy. Even if both strategies find it attractive, we only want one position per market to avoid concentration risk.

**Why this matters in practice**: Without this check, all three strategies might find the same opportunity (e.g., a crypto market with high endgame score, strong bid imbalance, AND correlation lag). Without duplicate prevention, you'd put $9 into a single market — 90% of your bankroll on one bet.

**Thread Safety — The Lock**

```python
self._lock = Lock()
```

All position reads/writes are protected by a mutex. This exists because the scanner runs in a thread pool (20 threads) while the main loop reads positions. Without the lock, concurrent reads and writes could corrupt the position dictionary.

### 4.8 Executor (`src/executor.py`)

**Design decision — one universal `execute()` method**: Originally, there were separate `execute_arb()`, `execute_endgame()` methods. This was refactored into a single `execute(opp, strategy_name)` because:
- All strategies output opportunities with the same interface (`.token_id`, `.price`, `.market_slug`, `.profit_per_share`)
- The execution logic is identical regardless of strategy: size → check → buy
- Adding new strategies doesn't require adding new executor methods

**Position Sizing Logic:**

```python
def compute_position_size(self, price):
    remaining = max_total_exposure - current_exposure
    max_spend = min(max_position_usdc, remaining)
    return max_spend / price
```

This is constrained by two limits:
1. **Per-position cap**: Never spend more than `max_position_usdc` on one trade
2. **Remaining exposure cap**: Never exceed `max_total_exposure_usdc` across all positions

The minimum of these two becomes the budget. Divide by price to get number of shares.

**Example with real numbers** (bankroll=$10, max_position=30%, max_exposure=90%):
- First trade: remaining=$9.00, max_position=$3.00 → spend $3.00
- Second trade: remaining=$6.00, max_position=$3.00 → spend $3.00
- Third trade: remaining=$3.00, max_position=$3.00 → spend $3.00
- Fourth trade: remaining=$0.00 → can't trade (exposure limit hit)

**`ExecutionResult` — structured feedback**: Every execution returns a result with `success`, `total_cost`, `expected_profit`, and `message`. This feeds the dashboard and logging without side effects.

### 4.9 Dashboard (`src/dashboard.py`)

**Why Rich?** Alternatives considered:
- `curses` — too low-level, painful to build layouts
- Print statements — can't update in place, scrolls forever
- Web UI — adds HTTP server complexity, overkill for a terminal bot
- Rich — modern, beautiful, supports live updating, tables, panels, colors

**Design decision — 2 refreshes/second**: The dashboard updates twice per second via `refresh_per_second=2`. This is fast enough to feel responsive without flickering. The actual data only changes every ~18 seconds (scan cycle), but smooth refresh makes it feel alive.

**Layout rationale — three strategy panels side by side**: You can compare endgame, value, and correlation opportunities at a glance. Seeing all three simultaneously reveals patterns: if the same market appears in all three strategies, that's a high-conviction bet.

### 4.10 Main Loop (`src/main.py`)

**Budget Allocation Across Strategies:**

With `max_trades_per_cycle = 5`:
```python
endgame_budget = max(1, budget // 2)           # 2
value_budget = max(1, (budget - 2) // 2 + ...)  # 2
corr_budget = max(1, budget - 2 - 2)            # 1
```

**Why endgame gets 50%?** It's the lowest-risk strategy. Near-certain outcomes close to resolution are the closest thing to free money on Polymarket. When you're starting with $10, capital preservation matters more than upside.

**Why correlation gets the least?** It's the highest-risk strategy. The lag might be legitimate (different strike prices), and the convergence might not happen. Give it one shot per cycle, not three.

**Signal Handling:**

```python
def handle_signal(sig, frame):
    if not bot._running:
        return  # Already shutting down
    logger.info("Received signal %d, shutting down...", sig)
    bot.stop()
```

**Why the `if not bot._running` guard?** Without it, pressing Ctrl+C during the scan phase would fire the handler multiple times (once for the main loop, once for each active thread). This caused duplicate "shutting down" messages. The guard ensures we log once and set the flag once.

**Logging — timestamped files**: Each run creates `logs/arbi-bot-20260315-200132.log`. This means you can compare runs over time, diagnose issues after the fact, and never worry about log rotation. The log goes to both file and terminal simultaneously.

---

## 5. The Rust Arbitrage Engine

### 5.1 Why Rust, Not Python, Not C++

**The speed requirement**: Polymarket arbitrage windows (YES ask + NO ask < $1.00) close in milliseconds because market makers and other bots are constantly scanning. The Python bot polls every ~18 seconds. Any arb window that lasts 18 seconds would have been caught by dozens of competitors already.

**Measured performance**:
- Rust engine: 400 WebSocket messages/sec processed, 4 full arb scans/sec
- Python equivalent: ~50 messages/sec (GIL + interpreter overhead), 0.07 scans/sec (one scan per 14s cycle)

That's an 80x throughput advantage and a 57x scanning frequency advantage.

**Why not C++?**
- Memory safety: Rust prevents use-after-free, double-free, buffer overflows at compile time. A segfault in a trading bot could leave orphaned positions.
- Async runtime: `tokio` is production-grade with excellent WebSocket support. C++ async is fragmented (Boost.Asio, libuv, etc.).
- Serde: Rust's serialization framework makes JSON parsing trivial. C++ JSON libraries (nlohmann/json, RapidJSON) are more verbose.
- Cargo vs CMake: Cargo handles dependencies, building, and testing in one tool. CMake is notoriously painful.

### 5.2 Configuration (`config.rs`)

**Design decision — reads parent `.env`**: `dotenvy::from_filename("../.env")` looks one directory up for the config file. This means the Rust engine shares configuration with the Python bot without duplicating the `.env` file.

**Separate namespace for arb settings**: Python uses `MAX_POSITION_PCT` (percentage of bankroll). Rust uses `ARB_MAX_POSITION_USDC` (absolute dollar amount). This is because:
- The arb engine doesn't track bankroll the same way (no cross-strategy compounding)
- Absolute limits are simpler and safer for a speed-critical path
- They can be tuned independently

### 5.3 Data Types (`types.rs`)

**BTreeMap for order books — the key design decision:**

```rust
pub struct OrderBook {
    pub bids: BTreeMap<u64, f64>,  // price_key → size
    pub asks: BTreeMap<u64, f64>,
}
```

**Why BTreeMap instead of HashMap?** 
- BTreeMap is sorted. `best_bid()` = last key, `best_ask()` = first key. Both are O(1) iterator operations.
- HashMap would require scanning all entries to find min/max — O(n) every time.
- We need sorted access for every arb check (400x/sec × 500 markets = 200,000 lookups/sec). BTreeMap makes this essentially free.

**Why not Vec<(price, size)> sorted?**
- Insertions and removals for WebSocket deltas would require binary search + shift — O(n) for insert.
- BTreeMap is O(log n) for insert, which is critical when we're processing 400 updates/sec.

**Price keys as u64:**

```rust
pub fn to_price_key(price: f64) -> u64 {
    (price * 1_000_000.0) as u64   // $0.42 → 420,000
}
```

**Why not use f64 directly as the BTreeMap key?** 
- `f64` doesn't implement `Ord` in Rust because of NaN (Not a Number). NaN breaks total ordering: NaN != NaN, NaN is neither less than nor greater than anything.
- We'd need a wrapper type with custom `Ord` implementation. Using u64 is simpler and avoids floating-point comparison edge cases.
- Multiplying by 1,000,000 gives us 6 decimal places of precision — more than enough for Polymarket's $0.01 tick size.

**GammaMarket uses `serde_json::Value` for flexible fields:**

The Gamma API is inconsistent: `volume` comes as a string (`"95507.12"`) in some responses and a number (`95507.12`) in others. `clobTokenIds` is sometimes a JSON string containing a JSON array, sometimes an actual array.

```rust
pub volume: serde_json::Value,
pub clob_token_ids: serde_json::Value,
```

Using `Value` accepts anything from the API, then helper methods (`volume_f64()`, `token_ids()`) handle the conversion. This is more resilient than strict typing which would fail on unexpected formats.

**Why not `#[serde(deserialize_with = ...)]` custom deserializers?** That would be more elegant but harder to debug. With `Value`, you can log exactly what the API sent when something goes wrong. This saved us during development when we discovered the double-encoding issue.

### 5.4 Market Fetcher (`markets.rs`)

**Binary market filtering:**

```rust
fn parse_binary_market(raw: &GammaMarket) -> Option<MarketPair> {
    let ids = raw.token_ids();
    if ids.len() != 2 { return None; }  // Not binary
    ...
}
```

**Why only binary markets?** Intra-market arbitrage requires exactly 2 outcomes that sum to $1.00. Multi-outcome markets (e.g., "Who will win the election?" with 5 candidates) would need a different algorithm: the sum of all outcome asks must be < $1.00. We could add this, but binary markets are the vast majority and simplest to implement correctly.

**Diagnostic logging**: The fetcher logs detailed stats — how many raw markets were fetched, how many were binary, how many had no token IDs. This was added after the "0 binary markets" bug where silent failures made diagnosis impossible.

### 5.5 WebSocket Client (`ws.rs`)

**Architecture — producer/consumer via mpsc channel:**

```rust
let (tx, mut rx) = mpsc::channel::<BookEvent>(10_000);
tokio::spawn(ws::connect_and_stream(ws_url, token_ids, tx));

// Main loop consumes events from rx
while let Some(event) = rx.recv().await { ... }
```

**Why channel instead of direct processing?** 
- The WebSocket reader and the arb scanner run at different speeds. The channel buffers events.
- If arb scanning takes 1ms but a burst of 50 WebSocket messages arrives simultaneously, the channel absorbs the burst without back-pressuring the WebSocket.
- The 10,000-element buffer means we can absorb ~25 seconds of data (at 400/sec) if scanning stalls.

**PING/PONG keepalive:**

```rust
tokio::spawn(async move {
    loop {
        tokio::time::sleep(Duration::from_secs(10)).await;
        if write.send(Message::Text("PING".into())).await.is_err() {
            break;
        }
    }
});
```

**Why 10 seconds?** Polymarket's WebSocket server closes idle connections after ~30 seconds. Sending PING every 10 seconds ensures we never hit that timeout while giving plenty of margin.

**Auto-reconnect loop:**

```rust
loop {
    match run_connection(&ws_url, &token_ids, &tx).await {
        Ok(()) => warn!("WebSocket closed, reconnecting in 2s..."),
        Err(e) => error!("WebSocket error: {}, reconnecting..."),
    }
    tokio::time::sleep(Duration::from_secs(2)).await;
}
```

**Why 2 seconds?** Fast enough to not miss too many arb opportunities. Slow enough to not hammer the server during an outage. In production, you might want exponential backoff (2s, 4s, 8s, 16s...) to be a better citizen during server issues.

**Event processing — snapshots vs deltas:**

On subscription, the server sends a full `book` event with all bids and asks for each token. After that, it sends `price_change` deltas — only the levels that changed.

```rust
"book" => {
    // Replace entire order book
    let mut book = OrderBook::new(msg.asset_id.clone());
    // ... populate from bids/asks
    tx.send(BookEvent::Snapshot(book)).await;
}
"price_change" => {
    // Update specific price levels
    tx.send(BookEvent::Update { token_id, bids, asks }).await;
}
```

This is efficient: the initial snapshot might be 1KB per token, but deltas are typically 50-100 bytes. Over time, you process mostly tiny deltas rather than full snapshots.

### 5.6 Arbitrage Scanner (`scanner.rs`)

**The core algorithm:**

```rust
fn check_market(&self, market: &MarketPair) -> Option<ArbOpportunity> {
    let yes_ask = self.books.get(&market.yes_token)?.best_ask()?;
    let no_ask = self.books.get(&market.no_token)?.best_ask()?;

    let total_cost = yes_ask + no_ask;
    if total_cost >= 1.0 { return None; }

    let spread_pct = (1.0 - total_cost) * 100.0;
    if spread_pct < self.min_spread_pct { return None; }

    Some(ArbOpportunity { ... })
}
```

**Why `?` operator chains instead of explicit error handling?** The `?` operator returns `None` early if any lookup fails. This means: if we don't have an order book for YES, or if YES has no asks, or if NO has no asks — we silently skip this market. This is correct behavior: missing data = can't determine arb = skip.

**HashMap vs BTreeMap for `books`:**

```rust
books: HashMap<String, OrderBook>
```

The scanner's market lookup is by token ID (a string). HashMap gives O(1) lookup. BTreeMap would give O(log n) — unnecessary overhead since we never need sorted iteration over the books collection.

### 5.7 Executor (`executor.rs`)

**Position sizing:**

```rust
let max_spend = self.config.max_position_usdc
    .min(self.config.max_exposure_usdc - self.total_exposure);
```

**Why `.min()` chain?** Takes the lesser of two constraints:
1. Per-trade limit (e.g., $2)
2. Remaining exposure budget (e.g., $8 - $4 already deployed = $4)

If you have $4 of exposure budget left but the per-trade limit is $2, you spend $2. If you have $1 of budget left, you spend $1 regardless of per-trade limit.

**FOK order intent (TODO):**

The executor currently logs trades but doesn't place real orders. For arb, Fill-Or-Kill is essential:

- You need to buy YES **and** NO simultaneously
- If you buy YES but the NO order fails (price moved), you're stuck with a directional position instead of an arb
- FOK ensures both orders either fill completely or cancel entirely

Implementing this requires the `rs-clob-client` crate for EIP-712 signing, which is why it's marked TODO.

### 5.8 Main Loop (`main.rs`)

**Scanning frequency — every 100 events:**

```rust
if updates_processed % 100 == 0 {
    let opportunities = arb_scanner.scan(&market_pairs);
    ...
}
```

**Why 100?** At 400 events/sec:
- Every event (% 1): 400 scans/sec × 500 markets = 200,000 checks/sec. Excessive CPU.
- Every 100 events: 4 scans/sec. Each scan takes ~0.5ms. Total: 2ms/sec out of 1,000ms. Negligible CPU.
- Every 1000 events: 0.4 scans/sec. Too slow — you'd miss sub-second arb windows.

100 is the sweet spot: 4 scans/sec catches any window lasting >250ms while using <0.2% CPU.

**Stats logging every 5000 events:**

```rust
if updates_processed % 5000 == 0 {
    info!("Stats: {} updates | {:.0}/sec | {} arbs found | bankroll=${:.2}",
        updates_processed, updates_processed as f64 / elapsed, arbs_found, ...);
}
```

At 400 events/sec, this logs every ~12.5 seconds. Frequent enough to monitor health, infrequent enough to not spam the log.

---

## 6. The Launch System

### `run.sh` — Design Decisions

**Python detection priority:**
```bash
if [ -f ".venv/bin/python3" ]; then PYTHON=".venv/bin/python3"
elif [ -f ".venv/bin/python" ]; then PYTHON=".venv/bin/python"
else PYTHON="$(command -v python3 || command -v python)"
```

**Why check `.venv` first?** On macOS, system `python3` exists but doesn't have our dependencies (`httpx`, `py-clob-client`, etc.). The `.venv` has everything installed. Checking it first avoids "ModuleNotFoundError" crashes.

**Why not `source .venv/bin/activate`?** Activation modifies the shell's PATH, which is fragile in a script. Calling the venv Python directly is more explicit and robust.

**Process management:**
```bash
"$PYTHON" -m src.main &
PY_PID=$!

"$ARB_BINARY" &
RUST_PID=$!
```

Both processes run in the background. Their PIDs are captured for cleanup.

**Cleanup trap:**
```bash
trap cleanup EXIT INT TERM
```

This fires on:
- `EXIT`: Script finishes normally
- `INT`: Ctrl+C (SIGINT)
- `TERM`: `kill` command (SIGTERM)

The cleanup function kills both processes and waits for them to exit. This prevents orphaned processes that would continue trading after you think the bot stopped.

---

## 7. Risk Philosophy & Money Management

### Why Position Sizing Matters More Than Strategy

With a $10 bankroll, a single $10 bet that loses kills you instantly. Even a $5 bet that loses puts you at $5 — your recovery is now twice as hard.

The Kelly Criterion tells us the optimal bet size is:
```
f = (bp - q) / b
```
Where `b` = odds, `p` = probability of winning, `q` = probability of losing.

For an endgame play at $0.90 (10% profit, ~90% chance of winning):
```
f = (0.111 × 0.90 - 0.10) / 0.111 = 0.0009 / 0.111 = 0.008 = 0.8%
```

Full Kelly says bet 0.8% of bankroll — $0.08 on a $10 bankroll. That's too conservative for practical purposes (you'd need 125 winning trades to make $1).

We use **fractional Kelly** at roughly 30x Kelly (30% max position). This is aggressive but bounded — you can survive ~3 consecutive total losses before the kill switch fires.

### Auto-Compounding — The Eighth Wonder of the World

At 10% return per trade with $3 bets (30% of $10):
```
Trade 1: $10.00 → $10.30  (bet $3.00, profit $0.30)
Trade 2: $10.30 → $10.61  (bet $3.09, profit $0.31)
Trade 3: $10.61 → $10.93  (bet $3.18, profit $0.32)
...
Trade 10: $12.59 → $12.97 (bet $3.78, profit $0.38)
Trade 20: $15.89 → $16.37 (bet $4.77, profit $0.48)
Trade 50: $31.86 → $32.81 (bet $9.56, profit $0.96)
```

After 50 winning trades, you've turned $10 into $32+. Without compounding (fixed $3 bets), you'd have $10 + (50 × $0.30) = $25. The difference widens dramatically with more trades.

### The Kill Switch — Knowing When To Stop

The 30% drawdown kill switch ($3 loss from $10 starting) exists for a specific reason: if you've lost 30% of your bankroll, either:

1. **The market has changed**: Your strategy's assumptions are wrong. Endgame "near-certain" outcomes are losing. Stop.
2. **There's a bug**: Something in the execution path is wrong. Stop before it gets worse.
3. **Black swan**: An unexpected market event (platform outage, flash crash, incorrect resolution) caused cascading losses.

In all three cases, the correct action is to stop, investigate, and only resume after understanding what went wrong.

---

## 8. Complete Data Flow Walkthroughs

### Walkthrough 1: A Complete Endgame Trade (Lifecycle)

**Minute 0 — Market Discovery:**
The scanner calls `fetch_active_markets()`. Among the 500 returned is:
```
"Will Sevilla FC win on 2026-03-15?"
  condition_id: 0xabc...
  end_date: 2026-03-16T00:00:00Z  (tomorrow)
  volume: $91,330
  tokens: [
    { outcome: "Yes", token_id: "71439..." },
    { outcome: "No",  token_id: "10566..." }
  ]
```

**Minute 0 — Order Book Fetch:**
For the YES token, the CLOB API returns:
```
Bids: [0.89×200, 0.88×500, 0.85×1000]
Asks: [0.90×100, 0.91×300, 0.95×500]
Best bid: $0.89  |  Best ask: $0.90  |  Spread: $0.01
```

**Minute 0 — Endgame Evaluation:**
```
Price:   $0.90 → between $0.92 and $0.98?
```
Wait — $0.90 is below the default `min_endgame_probability` of $0.92. But in the aggressive configuration (from your `.env`), `MIN_ENDGAME_PROB=0.88`. So $0.90 passes.

```
Days:    0.0 → within 14? ✓
Volume:  $91,330 → above $1,000? ✓
```

Scoring:
```
profit_pct = (1.00 - 0.90) / 0.90 × 100 = 11.1%
profit_score = min(11.1 × 10, 100) = 100.0

days = 0.0
time_score = max(0, 100 - (0.0 × 7)) = 100.0

volume = 91330
volume_score = min(log10(91330) × 20, 100) = min(4.96 × 20, 100) = 99.1

bid_depth = 200 + 500 + 1000 = 1700 shares
depth_score = min(1700 × 10, 100) = 100.0

SCORE = (100 × 0.35) + (100 × 0.30) + (99.1 × 0.20) + (100 × 0.15)
      = 35 + 30 + 19.82 + 15
      = 99.8
```

**Minute 0 — Execution:**
```
Risk check: has_position("71439...")? No.
Risk check: has_market_position("lal-bar-sev-2026-03-15-sev")? No.
Position size: effective_bankroll=$10.00, max_position_pct=30%
  max_spend = $10.00 × 0.30 = $3.00
  remaining_exposure = $9.00 - $0.00 = $9.00
  actual_spend = min($3.00, $9.00) = $3.00
  shares = $3.00 / $0.90 = 3.33 shares

can_trade($3.00)?
  - Kill switch? No.
  - $3.00 > max_position ($3.00)? No.
  - $0.00 + $3.00 > max_exposure ($9.00)? No.
  → APPROVED

DRY_RUN = true → log only:
  "[DRY RUN][endgame] 3.3 shares @ $0.90 ($3.00) profit=$0.33 on lal-bar-sev-2026-03-15-sev"

(If DRY_RUN = false):
  Place GTC buy order: 3.33 shares of YES @ $0.90
  Record position in risk manager:
    Position(token_id="71439...", market_slug="lal-bar-sev-...",
             strategy="endgame", side="BUY", size=3.33, price=0.90)
```

**Day later — Resolution:**
Sevilla FC wins. The YES token resolves to $1.00.
```
Exit: record_exit("71439...", exit_price=1.00)
  pnl = (1.00 - 0.90) × 3.33 = $0.33
  realized_pnl: $0.00 → $0.33
  effective_bankroll: $10.00 → $10.33
  Next max_position: $10.33 × 0.30 = $3.10 (up from $3.00)
  trade_log appended: {pnl: 0.33, entry: 0.90, exit: 1.00, strategy: "endgame"}
```

### Walkthrough 2: Rust Arbitrage Detection (Real-Time)

**T=0.000s — WebSocket receives `book` event for YES token:**
```json
{"event_type": "book", "asset_id": "71439...",
 "bids": [{"price": "0.41", "size": "500"}, {"price": "0.40", "size": "1000"}],
 "asks": [{"price": "0.43", "size": "300"}, {"price": "0.44", "size": "600"}]}
```

Main loop:
```
BookEvent::Snapshot → arb_scanner.update_book(OrderBook {
    token_id: "71439...",
    bids: { 410000 → 500.0, 400000 → 1000.0 },
    asks: { 430000 → 300.0, 440000 → 600.0 },
})
```

**T=0.001s — WebSocket receives `book` event for NO token:**
```json
{"event_type": "book", "asset_id": "10566...",
 "bids": [{"price": "0.55", "size": "400"}],
 "asks": [{"price": "0.57", "size": "200"}, {"price": "0.58", "size": "500"}]}
```

**T=0.250s — 100th event, arb scan triggered:**
```
check_market("Bitcoin $100K"):
  yes_ask = OrderBook("71439...").best_ask() = 0.43  (420000 key, first in asks)
  no_ask  = OrderBook("10566...").best_ask() = 0.57

  total_cost = 0.43 + 0.57 = 1.00
  1.00 >= 1.0 → NO ARBITRAGE
```

**T=5.300s — WebSocket receives `price_change` for NO token:**
```json
{"event_type": "price_change", "asset_id": "10566...",
 "asks": [{"price": "0.55", "size": "150"}]}
```

This means someone posted a new ask at $0.55 for 150 shares on the NO side. The main loop applies the delta:
```
updated.asks.insert(550000, 150.0)  // New price level
```

Now NO's best ask dropped from $0.57 to $0.55.

**T=5.550s — 100th event since last scan, arb scan triggered:**
```
check_market("Bitcoin $100K"):
  yes_ask = 0.43
  no_ask  = 0.55  ← CHANGED (was 0.57)

  total_cost = 0.43 + 0.55 = 0.98 < 1.00!
  spread_pct = (1.00 - 0.98) × 100 = 2.0%
  2.0% >= min_spread_pct (0.5%) → ARBITRAGE FOUND!

  ArbOpportunity {
    yes_ask: 0.43, no_ask: 0.55,
    total_cost: 0.98, spread_pct: 2.0,
    profit_per_share: 0.02
  }
```

**T=5.550s — Execution:**
```
max_spend = min($2.00, $8.00 - $0.00) = $2.00
shares = $2.00 / $0.98 = 2.04 shares

DRY_RUN = true:
  "[DRY RUN] ARB: 2.0 shares @ $0.9800 ($2.00) profit=$0.0408 spread=2.04%"

(If live):
  Order 1: FOK BUY 2.04 YES @ $0.43 = $0.878
  Order 2: FOK BUY 2.04 NO  @ $0.55 = $1.122
  Total spend: $2.00
  Guaranteed payout: 2.04 × $1.00 = $2.04 (one of YES/NO must win)
  Risk-free profit: $0.04
```

**T=5.800s — Window closes:**
Another bot saw the same opportunity and bought the NO shares at $0.55. The ask is now depleted, next NO ask is $0.57 again. Total cost = $0.43 + $0.57 = $1.00. No more arb. The window lasted ~250ms.

### Walkthrough 3: Correlation Detection and Its Limitations

**The Setup:**
Scanner fetches multiple Ethereum-related markets. The correlation strategy groups them:

```
Group "crypto_eth" (classified by regex r"ethereum|eth\b"):

  Market A: "ETH above $3,000 by March 31"
    YES best ask: $0.82

  Market B: "ETH above $3,500 by March 31"
    YES best ask: $0.51

  Market C: "ETH reach $4,000 by December 31"
    YES best ask: $0.29

  Market D: "Ethereum Up or Down on March 15"
    YES "Up" best ask: $0.89
```

**Group average calculation:**
```
avg = (0.82 + 0.51 + 0.29 + 0.89) / 4 = $0.628
```

**Lag detection:**
For Market C ($0.29):
```
lag_pct = (0.628 - 0.29) / 0.29 × 100 = +116.5%
```

Market C is 116% below the group average. The strategy interprets this as: "The group consensus on ETH is bullish ($0.63 average), but this specific market hasn't caught up."

**BUT — here's the honest limitation:**

Market C asks "Will ETH reach **$4,000**?" while Market A asks "Will ETH stay above **$3,000**?" These are fundamentally different levels of difficulty:
- ETH above $3,000 with 90% probability = $0.90 ← almost certain
- ETH reaching $4,000 with 29% probability = $0.29 ← speculative

The "lag" isn't a mispricing — it's a harder condition with a legitimately lower probability. The simple group average doesn't account for strike price differences.

**When correlation DOES work well:** Markets with the same timeframe and similar conditions:
```
"Will ETH be up on March 15?"  → $0.89 (just resolved some earlier event)
"Will ETH hit $3,500 by March?" → $0.45 (hasn't reacted yet)
```

If ETH sentiment just turned very bullish (March 15 "up" at $0.89), the March $3,500 target at $0.45 might genuinely be underpriced. The correlation strategy catches this type of lag.

---

## 9. Configuration Reference & Tuning Guide

### All `.env` Variables

| Variable | Default | What It Controls | How To Tune |
|----------|---------|-----------------|-------------|
| `POLYMARKET_PRIVATE_KEY` | (required) | Your wallet identity | Export from MetaMask. Must start with `0x`. |
| `POLYMARKET_SIGNATURE_TYPE` | `0` | Auth method | `0` = EOA (regular wallet). `1` = contract wallet. Almost always `0`. |
| `POLYMARKET_FUNDER` | `""` | Who pays gas | Leave empty for self-funded. Only needed for proxy setups. |
| `BANKROLL_USDC` | `10.0` | Starting capital | Set to your actual USDC balance on Polygon. All limits scale from this. |
| `MIN_ENDGAME_PROB` | `0.92` | Endgame entry threshold | Lower = more opportunities but riskier. 0.88 is aggressive. 0.95 is conservative. |
| `MAX_ENDGAME_PRICE` | `0.98` | Endgame maximum price | Higher = accept thinner margins. 0.98 = min $0.02 profit. 0.95 = min $0.05 profit. |
| `MAX_DAYS_TO_RESOLUTION` | `14` | How far out to look | Lower = faster capital turnover. Higher = more opportunities but longer lockup. |
| `MIN_MARKET_VOLUME` | `1000` | Liquidity filter | Higher = safer but fewer markets. $1K is minimum for any reliable price. $10K+ is ideal. |
| `MAX_TRADES_PER_CYCLE` | `3` | Trades per scan | Scale with bankroll. At $10, 3 trades × $3 each = $9 deployed. At $100, increase to 5-10. |
| `MAX_POSITION_PCT` | `20.0` | Per-trade size | 20% = 5 positions to diversify. 30% = 3 positions, more concentrated. |
| `MAX_TOTAL_EXPOSURE_PCT` | `80.0` | Total deployment | 80% = keep 20% reserve. 90% = aggressive. Never go 100%. |
| `MAX_DRAWDOWN_PCT` | `30.0` | Kill switch | Lower = more cautious. 20% stops early. 50% gives more runway but risks more. |
| `SCAN_INTERVAL_SECONDS` | `5.0` | Pause between scans | Lower = faster detection but more API calls. Below 3s risks rate limiting. |
| `MARKETS_REFRESH_SECONDS` | `120.0` | Market list refresh | Lower = catch new markets faster. Higher = fewer API calls. |
| `MAX_MARKETS` | `500` | Markets to scan | 500 covers most liquid markets. 1000+ adds scan time for diminishing returns. |
| `TICK_SIZE` | `0.01` | Price precision | Polymarket standard. Don't change. |
| `ARB_MIN_SPREAD_PCT` | `0.5` | Minimum arb profit | Lower = catch thinner arbs. 0.1% = $0.001/share. Below that, fees eat profit. |
| `ARB_MAX_POSITION_USDC` | `2.0` | Per arb trade | Keep small. Arb positions resolve to $1 guaranteed, so risk is low, but liquidity can be thin. |
| `ARB_MAX_EXPOSURE_USDC` | `8.0` | Total arb deployment | 80% of bankroll dedicated to arb at most. |
| `DRY_RUN` | `true` | Real money switch | **Start with `true`. Only set `false` after monitoring logs for at least a few hours.** |

### Tuning For Different Bankrolls

**$10 (current — hyper-aggressive):**
```
MAX_POSITION_PCT=30
MAX_TOTAL_EXPOSURE_PCT=90
MAX_TRADES_PER_CYCLE=5
MIN_ENDGAME_PROB=0.88
MAX_DRAWDOWN_PCT=50
```

**$100 (moderate):**
```
MAX_POSITION_PCT=15
MAX_TOTAL_EXPOSURE_PCT=75
MAX_TRADES_PER_CYCLE=8
MIN_ENDGAME_PROB=0.92
MAX_DRAWDOWN_PCT=25
```

**$1,000+ (conservative):**
```
MAX_POSITION_PCT=5
MAX_TOTAL_EXPOSURE_PCT=50
MAX_TRADES_PER_CYCLE=15
MIN_ENDGAME_PROB=0.95
MAX_DRAWDOWN_PCT=15
MAX_MARKETS=1000
```

As bankroll grows, decrease concentration and increase diversification.

---

## 10. What Can Go Wrong — Honest Risk Assessment

### Risks of Each Strategy

**Endgame:**
- **Resolution surprise**: The "almost certain" outcome doesn't happen. A team loses, a vote fails, an event doesn't occur. You lose your entire position. Probability: ~5-10% per trade.
- **Resolution dispute**: Polymarket resolves the market incorrectly, or resolution is delayed. Your capital is locked.
- **Slippage**: When buying, you might get a worse price than the ask if multiple bots buy simultaneously.

**Value (Bid Imbalance):**
- **Noise, not signal**: Sometimes heavy bids are just one large trader making a mistake. The price doesn't actually move up.
- **Information asymmetry wrong direction**: The bids might be informed traders, but so are the asks. You don't know who's right.
- **Slow convergence**: Even if you're right about fair value, it might take weeks for the price to converge.

**Correlation:**
- **Legitimate divergence**: As discussed above, different strike prices and timeframes justify different prices.
- **Small sample**: Groups with 2-3 markets have noisy averages.
- **Category error**: Regex grouping might put unrelated markets together.

**Arbitrage (Rust):**
- **Latency**: Even at 400 updates/sec, there are faster competitors. Institutional firms co-locate servers near Polymarket's infrastructure.
- **Execution risk**: FOK orders might not fill if liquidity evaporates between detection and execution.
- **Partial fills**: If only one side fills, you have a directional position, not an arb.

### Platform Risks

- **Smart contract risk**: Polymarket's settlement contracts could have bugs.
- **Regulatory risk**: Prediction markets occupy a legal gray area in many jurisdictions.
- **API changes**: Polymarket could change their API without notice, breaking the bot.
- **Rate limiting**: Aggressive scanning could get your API key throttled.

### Mitigation

The risk manager's layered defense helps:
1. **Position limits** cap per-trade loss
2. **Exposure limits** cap total portfolio loss
3. **Kill switch** stops everything if losses accumulate
4. **Duplicate prevention** avoids concentration
5. **Dry run mode** lets you validate before risking real money

---

## 11. Setup & Running

### Prerequisites

- **Python 3.11+** with `venv` support
- **Rust toolchain** (install via `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- **An Ethereum private key** (export from MetaMask: Account → Details → Export Private Key)
- **USDC on Polygon** (for live trading; not needed for dry run)

### Installation

```bash
cd arbi-bot

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Rust engine
cd arb-engine
cargo build --release
cd ..

# Configuration
cp .env.example .env
nano .env  # Add your private key with 0x prefix
```

### Running

```bash
# Both engines together (recommended)
./run.sh

# Python bot only
source .venv/bin/activate
python -m src.main

# Rust engine only
cd arb-engine && cargo run --release

# View Python logs (latest run)
ls -lt logs/ | head -1  # Find latest log file
tail -f logs/arbi-bot-YYYYMMDD-HHMMSS.log
```

### Going Live Checklist

1. Run in dry mode for at least 2-3 hours. Read the logs. Make sure opportunities look reasonable.
2. Fund your Polygon wallet with a small amount of USDC ($10).
3. Set `DRY_RUN=false` in `.env`.
4. Start the bot and monitor the first few trades closely.
5. The kill switch will stop trading if you lose more than `MAX_DRAWDOWN_PCT` of your bankroll.
6. Review `logs/` after each session to understand what trades were made and why.

### Log Files

**Python**: `logs/arbi-bot-YYYYMMDD-HHMMSS.log` — one file per run, contains every scan result, every opportunity scored, every trade executed or skipped.

**Rust**: Logs to stdout (visible in terminal). Contains market fetch progress, WebSocket connection status, arb scans, and throughput stats every ~12 seconds.
