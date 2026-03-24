# The Complete Guide: Prediction Markets, Polymarket, and This Trading Bot

From absolute zero to understanding every line of code.

---

## Table of Contents

**Part I — Prediction Markets from First Principles**
1. [What Is a Prediction Market?](#1-what-is-a-prediction-market)
2. [The Math Behind Prices and Probability](#2-the-math-behind-prices-and-probability)
3. [Order Books — How Trading Actually Works](#3-order-books--how-trading-actually-works)
4. [The Blockchain Layer — Why Polygon, What Are Tokens](#4-the-blockchain-layer)
5. [Polymarket Specifically — APIs, Settlement, Resolution](#5-polymarket-specifically)

**Part II — Trading Strategies (The Theory)**
6. [Arbitrage — Guaranteed Profit, Zero Risk](#6-arbitrage)
7. [Endgame Sniping — Near-Certain Outcomes](#7-endgame-sniping)
8. [Value Betting — Reading the Order Book](#8-value-betting)
9. [Cross-Market Correlation — Exploiting Slow Repricing](#9-cross-market-correlation)
10. [Risk Management — Staying Alive](#10-risk-management)

**Part III — The Code (Every File, Every Line That Matters)**
11. [System Architecture — Why Two Languages](#11-system-architecture)
12. [Python Bot: Configuration](#12-python-configuration)
13. [Python Bot: The Client Layer](#13-python-client)
14. [Python Bot: The Scanner](#14-python-scanner)
15. [Python Bot: Endgame Strategy Implementation](#15-endgame-implementation)
16. [Python Bot: Value Strategy Implementation](#16-value-implementation)
17. [Python Bot: Correlation Strategy Implementation](#17-correlation-implementation)
18. [Python Bot: Risk Manager](#18-risk-manager-implementation)
19. [Python Bot: Executor](#19-executor-implementation)
20. [Python Bot: Dashboard & Main Loop](#20-dashboard-and-main-loop)
21. [Rust Engine: Types & Data Structures](#21-rust-types)
22. [Rust Engine: Market Fetcher](#22-rust-market-fetcher)
23. [Rust Engine: WebSocket Streaming](#23-rust-websocket)
24. [Rust Engine: Scanner & Executor](#24-rust-scanner-and-executor)
25. [Rust Engine: Main Loop](#25-rust-main-loop)
26. [The Launch Script](#26-launch-script)

**Part IV — Running It**
27. [Configuration & Tuning](#27-configuration)
28. [Setup & Running](#28-setup)
29. [What Can Go Wrong](#29-risks)

---

# Part I — Prediction Markets from First Principles

## 1. What Is a Prediction Market?

### The Concept

A prediction market is a place where people bet on the outcomes of future events using real money. Unlike a casino where the house sets the odds, a prediction market lets participants set the odds themselves by trading with each other.

The price of an outcome in a prediction market represents the crowd's collective belief about how likely that outcome is. If 1,000 people are trading on "Will it rain tomorrow?" and the YES price settles at $0.70, it means the crowd — with their own money on the line — believes there's roughly a 70% chance of rain.

### Why Prediction Markets Exist

Traditional ways of forecasting (polls, expert panels, models) have a problem: **people lie and experts are biased**. A political analyst on TV has no financial consequence for being wrong. A prediction market participant does. When you stand to lose real money if you're wrong, you think harder and research more carefully.

This is called the **wisdom of crowds** — aggregating many independent, incentivized opinions produces better forecasts than individual experts. Academic research (Arrow et al., 2008; Wolfers & Zitzewitz, 2004) has shown that prediction markets consistently outperform polls and expert panels in forecasting elections, economic indicators, and sporting events.

### Brief History

- **1988**: The Iowa Electronic Markets (IEM) launched at the University of Iowa for trading on US presidential elections. It beat polls in 74% of elections through 2004.
- **2003**: The Pentagon proposed a "Policy Analysis Market" where people could bet on geopolitical events (terrorism, coups). It was killed by Congress within 24 hours due to political backlash ("terrorism futures").
- **2014**: Augur launched as the first decentralized prediction market on Ethereum.
- **2020**: Polymarket launched on Polygon. It became the dominant platform during the 2024 US presidential election, processing over $3 billion in trading volume.
- **2026**: Polymarket is now the largest prediction market globally, with thousands of active markets covering politics, crypto, sports, weather, and pop culture.

### How It Differs from Sports Betting

| | Sports Betting | Prediction Market |
|---|---|---|
| Who sets odds? | The bookmaker (house) | The crowd (traders) |
| House edge? | Yes (5-10% vig/juice) | No (0% or minimal fees) |
| Can you sell? | Usually no | Yes, anytime |
| Outcomes | Fixed (team A wins/loses) | Anything ("Will it rain?") |
| Price changes? | Bookmaker adjusts | Market adjusts in real-time |
| Profit source | Other bettors minus house cut | Other bettors (zero-sum) |

The critical difference: in a prediction market, you can **sell your position before the event happens**. If you bought YES at $0.30 and it rises to $0.60, you can sell for a $0.30 profit without waiting for resolution. This makes prediction markets much more like stock markets than casinos.

---

## 2. The Math Behind Prices and Probability

### Price = Probability

In a prediction market, the price of a YES token directly represents the implied probability of that event occurring:

```
Price of YES = P(event happens)
Price of NO  = P(event doesn't happen) = 1 - P(event happens)
```

If YES is trading at $0.42:
- The market says there's a 42% chance the event happens
- If you believe the true probability is higher (say 60%), buying YES at $0.42 is a good bet

This is the fundamental idea: **you make money when you have a more accurate estimate of probability than the market**.

### Expected Value (EV) — The Core of All Betting Math

Expected value is what you'd earn on average if you made the same bet thousands of times:

```
EV = (Probability of winning × Profit if you win) - (Probability of losing × Loss if you lose)
```

**Example**: YES token at $0.42, you believe true probability is 60%:
```
EV = (0.60 × $0.58) - (0.40 × $0.42)
   = $0.348 - $0.168
   = +$0.18 per share
```

Positive EV = profitable bet over time. Every trade our bot makes should be positive EV.

**For endgame strategy**: YES at $0.90, estimated 95% probability:
```
EV = (0.95 × $0.10) - (0.05 × $0.90)
   = $0.095 - $0.045
   = +$0.05 per share
```

Still positive, even though the profit per share ($0.10) is small. The high probability (95%) makes it work.

**For arbitrage**: YES at $0.43 + NO at $0.55 = $0.98. Profit is guaranteed:
```
EV = 1.00 × $0.02 - 0.00 × $0.00 = +$0.02 per share
```

100% probability × $0.02 profit = always $0.02 profit. This is the only strategy with truly zero risk.

### Why YES + NO Should Equal $1.00

This is fundamental. In a binary market (two outcomes), exactly one outcome will win and pay $1.00. Therefore:

```
Fair price of YES + Fair price of NO = $1.00
```

If YES = $0.60, then NO should = $0.40. If you buy both for $1.00, you're guaranteed to get $1.00 back (one wins). No profit, no loss.

**But what if they don't add up to $1.00?**

If YES asks at $0.43 and NO asks at $0.55:
```
Total cost = $0.43 + $0.55 = $0.98
Guaranteed payout = $1.00
Free profit = $0.02 per share
```

This is arbitrage. It happens because the YES order book and the NO order book are maintained by different people (market makers), and they don't always perfectly coordinate.

If YES asks at $0.43 and NO asks at $0.59:
```
Total cost = $0.43 + $0.59 = $1.02
```

No arbitrage. You'd pay $1.02 to get $1.00. The $0.02 gap is the market maker's profit.

### The Implied Probability Distribution

Each market doesn't just give you one number — the order book gives you a *distribution*. The best ask is the marginal opinion, but the depth of bids and asks tells you how confident the market is.

```
Bids (buyers of YES)       Asks (sellers of YES)
$0.41 × 5,000 shares      $0.43 × 200 shares
$0.40 × 10,000 shares     $0.44 × 500 shares
$0.38 × 20,000 shares     $0.45 × 1,000 shares
$0.35 × 50,000 shares     $0.50 × 5,000 shares
```

The thin asks ($0.43 × only 200 shares) mean that price level is fragile. A $100 buy would push the price to $0.44. The thick bids ($0.38 × 20,000 shares) mean strong support — it would take $7,600 of selling to push the price below $0.38.

Our **value strategy** reads this imbalance. Heavy bids + thin asks = the price is about to go up.

---

## 3. Order Books — How Trading Actually Works

### What an Order Book Is

An order book is a list of all buy orders (bids) and sell orders (asks) for a given asset. It's the mechanism through which a prediction market (or stock exchange) matches buyers and sellers.

```
═══════════════════════════════════════════
        ORDER BOOK: "ETH above $3,500?"
═══════════════════════════════════════════

  ASKS (people selling YES tokens)
  ─────────────────────────────────
  $0.55 ×  100 shares  ← BEST ASK (cheapest available)
  $0.56 ×  300 shares
  $0.58 ×  500 shares
  $0.60 × 1,000 shares

  ─────────── SPREAD: $0.03 ───────────

  BIDS (people buying YES tokens)
  ─────────────────────────────────
  $0.52 ×  200 shares  ← BEST BID (highest someone will pay)
  $0.51 ×  500 shares
  $0.50 × 1,500 shares
  $0.48 × 3,000 shares
═══════════════════════════════════════════
```

### Key Concepts

**Best Bid**: The highest price anyone is currently willing to pay. If you want to sell immediately, you sell at the best bid.

**Best Ask**: The lowest price anyone is currently willing to sell at. If you want to buy immediately, you buy at the best ask.

**Spread**: The gap between best bid and best ask. A $0.03 spread in the example above. Tight spreads (< $0.02) mean high liquidity. Wide spreads (> $0.05) mean low liquidity and higher transaction costs.

**Depth**: How many shares are available at each price level. In the example, there are only 100 shares at $0.55 but 3,000 shares at $0.48. Depth tells you how much you can trade without moving the price.

**Slippage**: If you buy 400 shares in the example above, the first 100 cost $0.55, the next 300 cost $0.56. Your average price is $0.5575, not $0.55. This worsening price is slippage. It's why our bot limits position sizes — buying too much at once means worse prices.

### Order Types

**Limit Order (GTC — Good Till Cancelled)**: "I want to buy 100 shares at $0.50." The order sits in the book until someone agrees to sell at that price. Could take minutes, hours, or never fill.

**Market Order**: "I want to buy 100 shares at whatever the current ask is." Fills immediately but you accept whatever price is offered. On Polymarket, the closest equivalent is a limit order at the current ask price.

**Fill-Or-Kill (FOK)**: "Buy 100 shares at $0.55 right now, or cancel the entire order." No partial fills. Essential for arbitrage — you need both sides (YES and NO) to fill completely, or neither.

Our Python bot uses **GTC limit orders** for strategic positions (willing to wait for a good price). The Rust engine would use **FOK** for arbitrage (need instant execution on both sides).

### Why Order Books Matter for Our Bot

1. **Best ask** is the price we'd pay to enter a position. It's the input to all our strategies.
2. **Best bid** is the price we'd get if we need to exit before resolution. It determines our "exit liquidity."
3. **Bid depth** tells the endgame strategy how easy it is to exit if needed.
4. **Bid/ask imbalance** is the primary signal for the value strategy.
5. **Combined asks** (YES + NO) is the input to the arbitrage strategy.

---

## 4. The Blockchain Layer

### Why Blockchain?

Prediction markets need three things that blockchains provide:

1. **Trustless settlement**: When a market resolves, winners get paid automatically by a smart contract. No human middleman can steal the money or refuse to pay.

2. **Censorship resistance**: No government can shut down the market or freeze your funds (in theory — regulatory risk still exists).

3. **Transparency**: Every trade, every resolution, every payout is recorded on-chain. No hidden manipulation.

### Ethereum vs Polygon

Polymarket runs on **Polygon** (chain ID 137), not Ethereum mainnet. Why?

**Ethereum mainnet** has:
- High security (thousands of validators)
- Slow transactions (12-second block times)
- Expensive gas fees ($5-50 per transaction during congestion)

**Polygon** has:
- Moderate security (proof-of-stake with ~100 validators)
- Fast transactions (2-second block times)
- Near-zero gas fees ($0.001-0.01 per transaction)

For a trading bot making dozens of trades per day, Ethereum gas fees would eat all the profit. Polygon's near-zero fees make small-value trading viable. The tradeoff is slightly lower security, which is acceptable for the amounts we're trading.

### ERC-1155 Tokens — What You're Actually Trading

Every outcome in every Polymarket market is an **ERC-1155 token**. ERC-1155 is a standard for "semi-fungible" tokens — tokens that come in batches where each unit is identical.

When you buy 10 shares of "ETH above $3,500? YES", you receive 10 ERC-1155 tokens with a specific token ID. That token ID is a huge number:

```
71439730646235279808665335107954661987767386997501589451725217259692960672095
```

This 256-bit number uniquely identifies this specific outcome on the Polygon blockchain. It's what the CLOB API uses to look up order books and place orders.

When the market resolves:
- If ETH is above $3,500: Your 10 YES tokens can be redeemed for 10 USDC ($10.00)
- If ETH is below $3,500: Your 10 YES tokens are worth nothing ($0.00)

Redemption happens through Polymarket's smart contracts on Polygon.

### USDC — The Currency

All trading on Polymarket is denominated in **USDC** (USD Coin), a stablecoin pegged 1:1 to the US dollar. USDC on Polygon is a bridged version of USDC on Ethereum.

To trade, you need USDC in your Polygon wallet. You can get it by:
1. Buying USDC on an exchange (Coinbase, Kraken) and withdrawing to Polygon
2. Bridging USDC from Ethereum to Polygon
3. Using a fiat on-ramp directly to Polygon

### Private Keys — How You Authenticate

Your Ethereum private key is a 256-bit number (64 hex characters with a `0x` prefix). **Never paste a real key into docs or code** — only into your local `.env` (gitignored):
```
0xdeadbeef000000000000000000000000000000000000000000000000000000
```
(The value above is a non-secret placeholder for illustration only.)

This key proves you own a specific wallet address. On Polymarket, it's used for:

1. **Deriving API credentials**: Your key signs an EIP-712 message to create trading API keys (one-time)
2. **Signing orders**: Every order you place is cryptographically signed so the CLOB knows it's really you
3. **On-chain settlement**: When you redeem winning tokens, the transaction is signed with your key

**Never share your private key. Anyone with it can take all your funds.**

Our bot stores it in `.env` (which is in `.gitignore` so it's never committed to git).

### The Hybrid Architecture — Off-Chain Matching, On-Chain Settlement

Polymarket's CLOB is **hybrid decentralized**:

```
You place order → CLOB matches off-chain → Settlement on-chain (Polygon)
                  (fast, free)              (final, immutable)
```

**Off-chain (CLOB server)**: Order matching happens on Polymarket's centralized servers. This gives instant matching (no waiting for block confirmations) and zero gas fees for placing/cancelling orders.

**On-chain (Polygon)**: Actual token transfers and settlements happen on the blockchain. When your order is matched, the USDC leaves your wallet and tokens arrive — all on Polygon.

This hybrid approach gives the speed of centralized exchanges with the settlement guarantees of a blockchain.

---

## 5. Polymarket Specifically

### The Two APIs We Use

**Gamma API** (`https://gamma-api.polymarket.com`)

This is the market discovery API. No authentication needed. We use it to:
- Find all active markets
- Get market metadata (question, end date, volume, token IDs)
- Sort markets by volume to find the most liquid ones

**Example request:**
```
GET /markets?active=true&closed=false&limit=100&order=volume&ascending=false
```

**Example response (simplified):**
```json
{
  "question": "Will Bitcoin reach $100,000 by December 31, 2026?",
  "conditionId": "0xabc123...",
  "slug": "will-bitcoin-reach-100000-by-december-31-2026",
  "endDate": "2026-12-31T23:59:59Z",
  "volume": "95507.12",
  "liquidity": "23500.50",
  "outcomes": "[\"Yes\", \"No\"]",
  "clobTokenIds": "[\"71439730...\", \"10566953...\"]",
  "negRisk": false,
  "active": true,
  "closed": false
}
```

Notice: `volume` is a string ("95507.12"), not a number. `outcomes` and `clobTokenIds` are JSON strings containing JSON arrays (double-encoded). These quirks caused bugs that we had to fix in both the Python and Rust parsers.

**CLOB API** (`https://clob.polymarket.com`)

This is the trading API. Authentication required for placing orders (not for reading).

We use it to:
- Fetch live order books (GET, no auth)
- Place buy/sell orders (POST, requires auth)
- Cancel orders (DELETE, requires auth)
- Check positions and balances

**Order book request:**
```
GET /book?token_id=71439730...
```

**Response (the `py-clob-client` SDK parses this):**
```json
{
  "bids": [
    {"price": "0.41", "size": "500"},
    {"price": "0.40", "size": "1000"}
  ],
  "asks": [
    {"price": "0.43", "size": "300"},
    {"price": "0.44", "size": "600"}
  ]
}
```

**WebSocket API** (`wss://ws-subscriptions-clob.polymarket.com/ws/market`)

The Rust engine connects here for real-time streaming. No authentication needed (public market data).

**Subscribe:**
```json
{"assets_ids": ["token_1", "token_2", ...], "type": "market"}
```

**Server sends:**
- `book` events: Full order book snapshot (on initial subscribe)
- `price_change` events: Incremental updates (a price level added, removed, or changed)

You must send `PING` every 10 seconds or the server disconnects you. It responds with `PONG`.

### Market Resolution — How Winners Get Paid

When an event occurs (or the deadline passes), Polymarket resolves the market:

1. **An oracle** (usually UMA's optimistic oracle) proposes a resolution ("YES won")
2. **Challenge period**: Anyone can dispute the resolution by posting a bond
3. **If undisputed**: Resolution is finalized after the challenge period (usually 2 hours)
4. **Settlement**: Smart contract allows winning token holders to redeem for $1.00 USDC per token

For our endgame strategy, we're buying tokens just before this resolution. The oracle has often already proposed, and the challenge period is running out. The outcome is known, but the token still trades below $1.00.

### negRisk — A Special Market Type

Some Polymarket markets have `negRisk: true`. These use a different smart contract architecture where outcomes can be "negatively correlated" — meaning you can create markets like "Which party wins the election?" where the outcomes are mutually exclusive but more than two.

For our purposes, negRisk affects order signing. The `neg_risk` flag is passed to the order builder so it uses the correct contract.

---

# Part II — Trading Strategies (The Theory)

## 6. Arbitrage

### What It Is

Arbitrage is buying and selling the same thing simultaneously in different markets (or related instruments) to profit from a price discrepancy, with zero risk.

In prediction markets, the simplest form: if the cheapest available YES and cheapest available NO for the same market cost less than $1.00 combined, you buy both and lock in a guaranteed profit.

### A Concrete Example

Market: "Will the Lakers win tonight?"
```
YES order book best ask: $0.47
NO  order book best ask: $0.51

Total cost: $0.47 + $0.51 = $0.98
```

You buy 100 YES @ $0.47 = $47.00
You buy 100 NO  @ $0.51 = $51.00
Total spent: $98.00

**If Lakers win**: 100 YES tokens redeem for $100.00. Profit = $2.00.
**If Lakers lose**: 100 NO tokens redeem for $100.00. Profit = $2.00.

You profit $2.00 regardless of who wins. Zero risk. The 2% spread is your profit.

### Why It's Rare

Polymarket has market makers — bots and professional traders who continuously post bids and asks on both YES and NO. They keep the combined ask close to $1.00 (or slightly above, which is their profit margin).

An arb window opens when:
- A large buy order hits YES, pushing its ask up
- The market maker hasn't yet lowered NO's ask to compensate
- For a brief moment (milliseconds to seconds), YES ask + NO ask < $1.00

These windows close fast because other arb bots see the same thing. This is why our Rust engine needs to process 400 updates/second — to catch windows that last <1 second.

### Why Not Every Bot Does This

1. **Capital efficiency**: You tie up $0.98 to make $0.02 (2% return). But you might wait hours for the market to resolve. Annualized, if resolution takes 7 days, that's ~100% APR — actually great. But with a $10 bankroll, $0.02 per arb isn't exciting.

2. **Execution risk**: You need both sides (YES and NO) to fill. If only YES fills, you have a directional bet, not an arb. FOK orders solve this but they're harder to implement.

3. **Speed competition**: You're competing against everyone else running arb bots. The fastest wins. With a consumer laptop, you're unlikely to beat co-located servers.

---

## 7. Endgame Sniping

### What It Is

Buy tokens for outcomes that are almost certainly going to happen, just before they resolve. The market knows the outcome (price is $0.88-$0.98), but the token still trades below $1.00. The gap is your profit.

### Why The Gap Exists

You might ask: "If everyone knows the outcome is YES, why doesn't the price go to $1.00 immediately?"

Several reasons:

1. **Time value of money**: If the market resolves in 3 days, holding $0.95 in a token means you can't use that $0.95 elsewhere. Some traders sell at $0.95 rather than wait 3 days for $0.05 profit (1.7% return / 3 days).

2. **Residual uncertainty**: Even at $0.92, there's an 8% implied chance of losing. A football game might be 3-0 at halftime (the "Will Team X win?" market at $0.92), but comebacks happen.

3. **Thin order books near $1.00**: Market makers don't usually post asks at $0.99 because the profit per share ($0.01) isn't worth their capital. This means the ask can sit at $0.95 even when everyone agrees the probability is 99%.

4. **Withdrawal friction**: Claiming the $1.00 payout requires waiting for resolution and redemption. Some impatient holders sell at $0.96 to get their money back now.

### The Math — When Is It Worth It?

For a token at price \(p\) with estimated probability \(q\) of winning:

```
Expected profit = q × (1 - p) - (1 - q) × p
               = q - p
```

If \(q > p\), the trade is positive EV.

For endgame, \(p\) = $0.90 and our estimate of \(q\) ≈ 0.95 (based on the event being near-resolved):
```
Expected profit = 0.95 - 0.90 = $0.05 per share
```

On 3.3 shares ($3.00 investment): $0.165 expected profit. Return = 5.5%. If this resolves in 1 day, that's a 2,008% annualized return.

### The Scoring System

Not all endgame opportunities are equal. A $0.88 token resolving tomorrow with $90K volume is better than a $0.95 token resolving in 12 days with $2K volume. The scoring system ranks them:

```
score = 0.35 × profit_score + 0.30 × time_score + 0.20 × volume_score + 0.15 × depth_score
```

- **Profit (35%)**: How much you make per dollar risked. \((1 - price) / price \times 1000\), capped at 100.
- **Time (30%)**: How fast your capital comes back. \(100 - days \times 7\). Resolving today = 100. Resolving in 14 days = 2.
- **Volume (20%)**: How trustworthy the price is. \(\log_{10}(volume) \times 20\). $100K volume → score 100. $1K volume → score 60.
- **Depth (15%)**: Can you exit if needed? Sum of bid sizes × 10, capped at 100.

---

## 8. Value Betting

### What It Is

Value betting means buying an asset when you believe its true value is higher than its current price. In our case, we use order book dynamics to estimate "fair value" and buy when the market price is below it.

### The Order Book Imbalance Signal

When the bid side of an order book has significantly more volume than the ask side, it signals buying pressure that hasn't fully repriced the ask:

```
Bids: $0.60 × 2,000  |  $0.59 × 3,000  |  $0.58 × 5,000  = $10,000 total
Asks: $0.61 × 200     |  $0.62 × 300     |  $0.63 × 500   = $1,000 total

Imbalance ratio = $10,000 / $1,000 = 10.0x
```

10x more money waiting to buy than waiting to sell. Why hasn't the ask moved up? Because:
- The sellers at $0.61-$0.63 placed their orders earlier (before the bids piled up)
- Market makers haven't updated their asks yet
- New information (news, related market moves) reached bid-side traders first

The price *should* be higher. We buy at the current ask ($0.61) and expect it to move toward the fair value.

### How We Estimate Fair Value

```python
imbalance_ratio = bid_depth / ask_depth
pressure_boost = min(log2(imbalance_ratio) * 0.03, 0.10)
fair_value = current_ask + pressure_boost
```

Why `log2`? Because the relationship between imbalance and price movement is logarithmic. Going from 3x to 6x imbalance doesn't double the price move — diminishing returns.

Why cap at $0.10? Even extreme imbalances don't cause >$0.10 moves on Polymarket. The cap prevents unrealistic estimates.

### The Wide Spread Signal

When the bid-ask spread is unusually wide, the midpoint is a better estimate of fair value than the ask:

```
Best bid: $0.52    Best ask: $0.60    Spread: $0.08
Midpoint: $0.56
```

If you buy at $0.60 and the price converges to the midpoint ($0.56)... wait, that's a loss. The value strategy only takes wide-spread trades when the imbalance also favors the buy side — the midpoint should be *above* your entry price after accounting for the imbalance.

---

## 9. Cross-Market Correlation

### What It Is

When markets are about the same underlying topic (e.g., multiple Bitcoin markets), they should move in the same direction. If one reprices quickly after news breaks and another doesn't, the slow one is likely mispriced.

### The Theory — Law of One Price

In efficient markets, correlated assets should have correlated prices. If "BTC above $90K by March" jumps from $0.60 to $0.80 because Bitcoin rallied, then "BTC above $85K by March" should also increase (it's an easier condition to meet).

But Polymarket isn't perfectly efficient. Different market makers, different liquidity profiles, different attention from traders. One market reprices in seconds, another takes minutes.

### How We Detect It

1. **Group markets by keyword**: Regex patterns classify markets into topics (crypto_btc, crypto_eth, nba, russia_ukraine, etc.)

2. **Compute group average price**: For all markets in the "crypto_btc" group, average their YES prices.

3. **Find outliers**: Any market significantly below the group average is a potential buy.

```
Group "crypto_btc":
  "BTC above $90K March"  → $0.80
  "BTC above $85K March"  → $0.85
  "BTC reach $100K Dec"   → $0.42  ← 47% below group avg of $0.69
  "BTC above $80K March"  → $0.91

Laggard: "BTC reach $100K Dec" at $0.42 vs group average $0.74
Lag: +76%
```

### The Honest Limitation

Different markets in the same group may have **legitimately different prices**:
- "BTC above $85K" (easy condition) should be more expensive than "BTC reach $100K" (hard condition)
- "BTC above $90K by **March**" should be cheaper than "BTC above $90K by **December**" (less time)

Our regex grouping doesn't distinguish these. The lag might not be a mispricing at all. This is the highest-risk strategy — it works best when markets have similar strike prices and timeframes, and worst when they don't.

---

## 10. Risk Management

### Why It Matters More Than Anything

A trading system with amazing strategy and terrible risk management will go bankrupt. A trading system with mediocre strategy and excellent risk management will survive long enough to improve.

With a $10 bankroll, this is existential. One $10 loss = game over. Three $3 losses = game over. Risk management exists to prevent game over.

### Position Sizing — The Kelly Criterion

The Kelly Criterion tells you the mathematically optimal bet size to maximize long-term growth:

```
f* = (b × p - q) / b
```

Where:
- \(f*\) = fraction of bankroll to bet
- \(b\) = odds (net payout per dollar wagered)
- \(p\) = probability of winning
- \(q\) = probability of losing (1 - p)

For an endgame trade at $0.90 with 95% estimated probability:
```
b = (1.00 - 0.90) / 0.90 = 0.111
p = 0.95, q = 0.05

f* = (0.111 × 0.95 - 0.05) / 0.111 = 0.055 / 0.111 = 0.50 = 50%
```

Full Kelly says bet 50% of bankroll. But Kelly assumes you know the exact probability, which you don't. Practitioners use **fractional Kelly** (typically 1/4 to 1/2 of Kelly) to account for uncertainty.

Our bot uses ~60% of Kelly (30% max position ÷ 50% Kelly). This is aggressive but bounded.

### Auto-Compounding

Fixed bet sizes ($3 every time) leave money on the table. If your bankroll grows to $15, betting $3 is too conservative — you should bet $4.50 (30% of $15).

Auto-compounding recalculates position sizes every trade based on current bankroll:

```
effective_bankroll = initial_bankroll + realized_profits
max_bet = effective_bankroll × max_position_pct / 100
```

This creates geometric growth: wins increase bet sizes, which increase wins, which increase bet sizes...

After 50 wins of 10% each:
- With compounding: $10 → $32.81 (228% total return)
- Without compounding: $10 → $25.00 (150% total return)

### The Kill Switch

If cumulative losses exceed a threshold (default 30% of bankroll), the bot stops trading permanently. This exists because:

1. **If your strategy is wrong, more trading makes it worse.** Stopping forces human review.
2. **Systematic errors compound.** A bug in price parsing could cause every trade to lose. The kill switch limits damage.
3. **It enforces discipline.** Without it, a bot in a losing streak keeps going until the bankroll hits zero.

### Diversification

The bot never puts more than one bet per market. Even if endgame, value, AND correlation all flag the same market, only one trade is placed. This prevents concentration risk where a single market failure wipes out 90% of the bankroll.

---

# Part III — The Code

## 11. System Architecture

Two processes, two languages, one config file:

| Component | Language | What It Does | Speed |
|-----------|----------|-------------|-------|
| Python bot (`src/`) | Python 3.11+ | Endgame + Value + Correlation strategies | ~18s per cycle |
| Rust engine (`arb-engine/`) | Rust | Intra-market arbitrage | 400 updates/sec |
| Launch script (`run.sh`) | Bash | Starts both, manages lifecycle | N/A |

**Why two languages**: Python has the mature SDK (`py-clob-client`) for authentication and order placement. Rust has the speed for real-time WebSocket processing. Writing everything in one language would mean either sacrificing speed (all Python) or spending weeks reimplementing auth (all Rust).

The two processes share nothing except `.env`. They discover markets independently, track state independently, and can run independently. If one crashes, the other continues.

---

## 12. Python Configuration

**File**: `src/config.py`

Two immutable configuration objects loaded from environment variables at startup:

```python
@dataclass(frozen=True)
class PolymarketConfig:
    host: str = "https://clob.polymarket.com"
    gamma_host: str = "https://gamma-api.polymarket.com"
    chain_id: int = 137  # Polygon
    private_key: str = field(default_factory=lambda: os.environ["POLYMARKET_PRIVATE_KEY"])
    signature_type: int = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
    funder: str = os.getenv("POLYMARKET_FUNDER", "")
```

`chain_id = 137` identifies Polygon mainnet. Every EIP-712 signature includes the chain ID to prevent replay attacks across chains.

`signature_type = 0` means EOA (Externally Owned Account) — a regular MetaMask wallet. Type 1 would be a contract wallet (like a Gnosis Safe).

```python
@dataclass(frozen=True)
class TradingConfig:
    bankroll_usdc: float = float(os.getenv("BANKROLL_USDC", "10.0"))
    min_endgame_probability: float = float(os.getenv("MIN_ENDGAME_PROB", "0.92"))
    # ... (all other settings)
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() == "true"
```

`frozen=True` makes these objects immutable. Once created, no code can accidentally change `bankroll_usdc` from 10 to 0. This prevents an entire class of runtime bugs.

Module-level singletons are created at import time:
```python
polymarket_cfg = PolymarketConfig()
trading_cfg = TradingConfig()
```

Every other module does `from src.config import trading_cfg` to get the shared config.

---

## 13. Python Client

**File**: `src/client.py`

### Data Structures

**`Market`** — everything we know about a prediction market:
```python
@dataclass
class Market:
    condition_id: str    # On-chain identifier for the market
    question: str        # "Will Bitcoin reach $100K?"
    slug: str            # URL slug: "will-bitcoin-reach-100000"
    active: bool         # Currently tradeable?
    closed: bool         # Already resolved?
    tokens: list[TokenPair]  # YES and NO (or more for multi-outcome)
    volume: float        # Total USDC traded ($)
    liquidity: float     # Current USDC in the order book
    end_date: str        # When it resolves (ISO 8601)
    neg_risk: bool       # Uses negRisk contract
```

**`TokenPair`** — one outcome (one tradeable token):
```python
@dataclass
class TokenPair:
    outcome: str       # "Yes", "No", "Over 2.5", etc.
    token_id: str      # The 77-digit on-chain identifier
```

**`OrderBookSnapshot`** — live order book at a point in time:
```python
@dataclass
class OrderBookSnapshot:
    token_id: str
    bids: list          # All buy orders
    asks: list          # All sell orders
    timestamp: float    # When this snapshot was taken
```

The `best_bid`, `best_ask`, and `midpoint` properties compute from the raw lists:
```python
@property
def best_ask(self) -> float | None:
    if not self.asks:
        return None
    return min(self._get_price(a) for a in self.asks)
```

### Authentication Flow

```python
def connect(self):
    self._clob = ClobClient(
        host=self._cfg.host,
        key=self._cfg.private_key,   # Your Ethereum private key
        chain_id=self._cfg.chain_id, # 137 for Polygon
        signature_type=self._cfg.signature_type,  # 0 for EOA
    )
    creds = self._clob.create_or_derive_api_creds()  # Signs EIP-712 message
    self._clob.set_api_creds(creds)  # Sets API key/secret/passphrase
```

`create_or_derive_api_creds()` does the following internally:
1. Creates a structured EIP-712 message: "I want API access for wallet 0x..."
2. Signs it with your private key using the secp256k1 curve
3. Sends the signature to Polymarket's API key service
4. Receives back an API key, secret, and passphrase
5. These three values authenticate all future REST requests via HMAC-SHA256

### Market Fetching

The `fetch_active_markets()` method paginates through the Gamma API:

```python
while len(markets) < max_markets:
    resp = self._http.get("/markets", params={
        "active": "true", "closed": "false",
        "limit": 100, "offset": offset,
        "order": "volume", "ascending": "false",
    })
```

Key decisions:
- **`order=volume, ascending=false`**: Get highest-volume markets first. These have the best liquidity and most reliable prices.
- **`limit=100`**: Gamma API's maximum page size.
- **Pagination until `max_markets`**: Default 500. We don't need all 30,000+ markets — the top 500 by volume capture >95% of liquidity.

### Token Parsing — The Double-Encoding Fix

The Gamma API returns `clobTokenIds` as a JSON string containing a JSON array:
```json
"clobTokenIds": "[\"71439...\", \"10566...\"]"
```

This is double-encoded — a string that, when parsed, contains another string that, when parsed, contains an array. Our parser handles both the double-encoded case and the (rare) case where it's a real array:

```python
if isinstance(clob_ids, str):
    try:
        clob_ids = json.loads(clob_ids)  # Handle double-encoding
    except (json.JSONDecodeError, TypeError):
        # Fallback: manual string splitting
        clob_ids = [t.strip().strip('"') for t in clob_ids.strip("[]").split(",")]
```

This was one of the first bugs we hit. Without this fix, token IDs had extra `[`, `]`, and `"` characters, causing 404 errors when requesting order books from the CLOB API.

---

## 14. Python Scanner

**File**: `src/scanner.py`

### The Problem: 500 Sequential HTTP Requests

Each order book fetch takes ~0.5 seconds. 500 markets × 2 tokens each = 1,000 requests × 0.5s = 500 seconds per cycle. That's 8+ minutes — unacceptable.

### The Solution: Parallel Fetching

```python
CONCURRENCY = 20

class MarketScanner:
    def __init__(self, ...):
        self._pool = ThreadPoolExecutor(max_workers=CONCURRENCY)

    async def scan_all(self):
        sem = asyncio.Semaphore(CONCURRENCY)

        async def _snap(idx, market):
            async with sem:
                result = await loop.run_in_executor(
                    self._pool, self._snapshot_market_sync, market
                )
                return result

        tasks = [_snap(i, m) for i, m in enumerate(self._markets)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
```

20 concurrent requests → 500 markets completed in ~13 seconds (25x speedup).

Why `ThreadPoolExecutor` instead of `asyncio` native? The `py-clob-client` SDK uses synchronous `requests` internally. You can't make a synchronous HTTP library async. The standard pattern is to run sync code in a thread pool and await the result.

Why `Semaphore(20)`? Without it, `asyncio.gather` would launch all 500 tasks at once. The semaphore limits to 20 in-flight at a time, preventing API rate limiting and network congestion.

### MarketSnapshot

```python
@dataclass
class MarketSnapshot:
    market: Market                        # The market metadata
    books: dict[str, OrderBookSnapshot]   # token_id → live order book
    timestamp: float                      # When this was captured
```

This bundles everything a strategy needs: market question, end date, volume, AND live prices. Strategies receive a list of these and can analyze without making additional API calls.

---

## 15. Endgame Implementation

**File**: `src/strategies/endgame.py`

### The Filter Chain

For each market snapshot:

```python
def _check_market(self, snap):
    market = snap.market

    # Filter 1: Minimum volume
    if market.volume < self._cfg.min_market_volume:
        return []  # Skip illiquid markets

    # Filter 2: Time to resolution
    days_to_end = self._days_until_end(market.end_date)
    if days_to_end is None or days_to_end > self._cfg.max_days_to_resolution:
        return []  # Skip markets too far in the future

    for token in market.tokens:
        book = snap.books.get(token.token_id)
        if book is None or book.best_ask is None:
            continue  # No order book data

        price = book.best_ask

        # Filter 3: Price in endgame range
        if price < self._cfg.min_endgame_probability:
            continue  # Too uncertain
        if price > self._cfg.max_endgame_price:
            continue  # Too expensive (not enough profit)

        # Passed all filters — score and add
        bid_depth = self._compute_bid_depth(book)
        score = self._score(price, days_to_end, market.volume, bid_depth)
        results.append(EndgameOpportunity(...))
```

### The Scoring Formula (Detailed)

```python
@staticmethod
def _score(price, days, volume, bid_depth):
    import math

    # Component 1: Profit attractiveness
    profit_pct = ((1.0 - price) / price) * 100
    # At $0.90: (0.10/0.90)*100 = 11.1%
    # At $0.95: (0.05/0.95)*100 = 5.3%
    profit_score = min(profit_pct * 10, 100)
    # 11.1% * 10 = 111 → capped at 100

    # Component 2: Time urgency
    time_score = max(0, 100 - (days * 7))
    # 0 days: 100 - 0 = 100
    # 1 day: 100 - 7 = 93
    # 14 days: 100 - 98 = 2

    # Component 3: Market reliability
    volume_score = min(math.log10(max(volume, 1)) * 20, 100)
    # $1K: log10(1000)*20 = 60
    # $10K: log10(10000)*20 = 80
    # $100K: log10(100000)*20 = 100

    # Component 4: Exit liquidity
    depth_score = min(bid_depth * 10, 100)
    # 10 shares: 10*10 = 100
    # 0.5 shares: 0.5*10 = 5

    return (profit_score * 0.35) + (time_score * 0.30) + \
           (volume_score * 0.20) + (depth_score * 0.15)
```

### EndgameOpportunity — What Gets Returned

```python
@dataclass
class EndgameOpportunity:
    market_question: str   # "Will Sevilla FC win?"
    market_slug: str       # "lal-bar-sev-2026-03-15-sev"
    condition_id: str      # On-chain market ID
    neg_risk: bool         # Contract type
    token_id: str          # Which token to buy
    outcome: str           # "Yes"
    price: float           # $0.90
    end_date: str          # "2026-03-16T00:00:00Z"
    days_to_end: float     # 0.1
    volume: float          # 91330.0
    liquidity: float       # 5000.0
    bid_depth: float       # 1700.0
    score: float           # 99.8
```

The executor only needs `token_id`, `price`, `market_slug`, `neg_risk`, and `profit_per_share`. The rest is for logging and dashboard display.

---

## 16. Value Implementation

**File**: `src/strategies/value.py`

### Bid Imbalance Detection

```python
def _check_imbalance(self, snap, token, book, price, bid_depth, ask_depth, spread):
    if bid_depth <= 0 or ask_depth <= 0:
        return None

    imbalance_ratio = bid_depth / ask_depth
    if imbalance_ratio < 3.0:
        return None  # Not enough imbalance

    import math
    pressure_boost = min(math.log2(imbalance_ratio) * 0.03, 0.10)
    fair_value = min(price + pressure_boost, 0.99)
    edge_pct = ((fair_value - price) / price) * 100

    if edge_pct < 3.0:
        return None  # Edge too small after costs/slippage
```

**Why 3% minimum edge?** Below 3%, the expected profit is eaten by:
- Bid-ask spread when entering (~1%)
- Potential slippage on exit (~1%)
- Residual model uncertainty (~1%)

At 3%+, there's enough cushion to be profitable even with execution costs.

### Price Range Filter

```python
if price < 0.15 or price > 0.85:
    continue
```

Tokens near $0 or $1 have structurally wide spreads and extreme imbalances that don't signal mispricing. At $0.05, a 3x bid imbalance is noise. At $0.50, a 3x bid imbalance is a signal.

---

## 17. Correlation Implementation

**File**: `src/strategies/correlation.py`

### Group Classification

```python
CORRELATION_GROUPS = [
    (r"bitcoin|btc", "crypto_btc"),
    (r"ethereum|eth\b", "crypto_eth"),
    (r"solana|sol\b", "crypto_sol"),
    (r"trump.*truth\s*social|trump.*post", "trump_truth"),
    (r"russia.*enter|russia.*capture", "russia_ukraine"),
    (r"nba\b", "nba"),
    (r"oscars?\b", "oscars"),
    # ... 20+ groups
]
```

Each regex is compiled once at `__init__`:
```python
self._compiled = [(re.compile(pat, re.IGNORECASE), name) for pat, name in CORRELATION_GROUPS]
```

`re.IGNORECASE` because market questions have inconsistent capitalization ("Bitcoin" vs "bitcoin" vs "BTC").

The `\b` in `r"eth\b"` is a word boundary — matches "ETH" and "Ethereum" but not "Bethany" or "Seth".

### Building Groups and Finding Laggards

For each group, the strategy:
1. Collects all matching markets and their YES prices
2. Computes the group average price
3. For each market below the average: computes lag percentage
4. Scores by lag, preferring larger groups (more reliable averages) and lower prices (more upside)

---

## 18. Risk Manager Implementation

**File**: `src/risk.py`

### Thread Safety

```python
self._lock = Lock()
```

All position dictionary access is wrapped in `with self._lock:`. This is necessary because:
- The scanner runs in 20 threads (via ThreadPoolExecutor)
- The main loop reads positions for dashboard updates
- Without the lock, concurrent read/write could corrupt the dictionary

### The Compounding Mechanism

```python
@property
def effective_bankroll(self):
    return max(self._cfg.bankroll_usdc + self._realized_pnl, 0.01)
```

Every time a trade is closed (`record_exit()`), `_realized_pnl` is updated. This immediately flows through to `effective_bankroll`, which flows through to `max_position_usdc`, which flows through to the next trade's position size. No manual recalculation needed — it's all property chains.

### Trade Logging

```python
self._trade_log.append({
    "token_id": token_id,
    "market_slug": pos.market_slug,
    "strategy": pos.strategy,
    "pnl": pnl,
    "entry": pos.entry_price,
    "exit": exit_price,
    "size": pos.size,
})
```

Every closed trade is logged with full details. This enables post-run analysis: which strategy is winning? What's the average PnL per endgame trade vs value trade? Where are the losses coming from?

---

## 19. Executor Implementation

**File**: `src/executor.py`

### The Universal Execute Flow

```python
def execute(self, opp, strategy_name):
    # Gate 1: Duplicate check (token level)
    if self._risk.has_position(opp.token_id):
        return self._skip(opp, strategy_name, "Already have position on this token")

    # Gate 2: Duplicate check (market level)
    if self._risk.has_market_position(opp.market_slug):
        return self._skip(opp, strategy_name, "Already have position on this market")

    # Gate 3: Position sizing
    max_shares = self._risk.compute_position_size(opp.price)
    if max_shares <= 0:
        return self._skip(opp, strategy_name, "Position sizing returned 0")

    # Gate 4: Risk check
    total_cost = opp.price * max_shares
    ok, reason = self._risk.can_trade(total_cost)
    if not ok:
        return self._skip(opp, strategy_name, reason)

    # Gate 5: Dry run check
    if self._cfg.dry_run:
        return self._dry_run_result(opp, strategy_name, max_shares, total_cost)

    # All gates passed — place the order
    self._client.place_limit_buy(...)
    self._risk.record_entry(...)
```

Five gates between a strategy signal and an actual order. Every gate is logged when triggered, so you can trace exactly why a trade was or wasn't executed.

---

## 20. Dashboard and Main Loop

**File**: `src/dashboard.py` and `src/main.py`

### Dashboard

Uses the Rich library for a live-updating terminal UI. Three panels show the top opportunities from each strategy side by side. A fourth panel shows recent executions.

The dashboard updates 2× per second but data only changes every ~18 seconds (scan cycle). The fast refresh keeps the UI responsive.

### Main Loop

```python
async def run(self):
    self._client.connect()  # Auth and connect to CLOB
    live = self._dashboard.start()

    with live:
        while self._running:
            await self._tick()
            await asyncio.sleep(cfg.scan_interval_seconds)
```

Each tick:
1. **Scan**: Parallel order book fetch for 500 markets (~13s)
2. **Strategize**: Run all three strategies on the snapshots (< 100ms)
3. **Execute**: Pick top opportunities, pass through executor gates
4. **Display**: Update dashboard with results

### Budget Allocation

```python
budget = trading_cfg.max_trades_per_cycle  # e.g., 5
endgame_budget = max(1, budget // 2)       # 2
value_budget = max(1, (budget - endgame_budget) // 2 + (budget - endgame_budget) % 2)  # 2
corr_budget = max(1, budget - endgame_budget - value_budget)  # 1
```

Endgame gets the most because it's lowest risk. Correlation gets the least because it's highest risk. Each strategy is guaranteed at least 1 trade per cycle via `max(1, ...)`.

---

## 21. Rust Types

**File**: `arb-engine/src/types.rs`

### OrderBook — BTreeMap Design

```rust
pub struct OrderBook {
    pub token_id: String,
    pub bids: BTreeMap<u64, f64>,  // price (as integer) → size
    pub asks: BTreeMap<u64, f64>,
}
```

**BTreeMap** is a sorted balanced tree. Keys are always in order. This means:

```rust
pub fn best_bid(&self) -> Option<f64> {
    self.bids.keys().next_back()  // Last key = highest bid = O(1)
        .map(|&k| from_price_key(k))
}

pub fn best_ask(&self) -> Option<f64> {
    self.asks.keys().next()  // First key = lowest ask = O(1)
        .map(|&k| from_price_key(k))
}
```

HashMap would require scanning ALL entries to find min/max — O(n). With order books that might have 50+ price levels and we're checking 500 markets 4× per second, that's 100,000 O(n) operations per second. BTreeMap makes them O(1).

### Price Keys — Integer Representation

```rust
pub fn to_price_key(price: f64) -> u64 {
    (price * 1_000_000.0) as u64
}
// $0.42 → 420,000
// $0.4201 → 420,100
```

Why not use f64 as the key directly? In Rust, `f64` doesn't implement `Ord` (total ordering) because `NaN != NaN`. BTreeMap requires `Ord` for its keys. Using u64 avoids this issue and eliminates floating-point comparison edge cases.

### GammaMarket — Flexible Deserialization

```rust
pub struct GammaMarket {
    pub clob_token_ids: serde_json::Value,  // Not String, not Vec
    pub volume: serde_json::Value,          // Not f64, not String
}
```

Using `serde_json::Value` (JSON's "any type") because the Gamma API is inconsistent:
- `volume`: Sometimes `"95507.12"` (string), sometimes `95507.12` (number)
- `clob_token_ids`: Sometimes `"[\"id1\", \"id2\"]"` (string containing JSON), sometimes `["id1", "id2"]` (actual array)

Helper methods handle all cases:
```rust
pub fn volume_f64(&self) -> f64 {
    match &self.volume {
        Value::Number(n) => n.as_f64().unwrap_or(0.0),
        Value::String(s) => s.parse().unwrap_or(0.0),
        _ => 0.0,
    }
}
```

---

## 22. Rust Market Fetcher

**File**: `arb-engine/src/markets.rs`

Same pagination logic as Python, using `reqwest` (Rust HTTP client):

```rust
while markets.len() < limit {
    let url = format!(
        "{}/markets?active=true&closed=false&limit=100&offset={}",
        gamma_url, offset
    );
    let resp = client.get(&url).send().await?;
    let batch: Vec<GammaMarket> = serde_json::from_str(&body)?;
    // ... parse binary markets
    offset += 100;
}
```

Only keeps markets with exactly 2 token IDs (binary YES/NO). Multi-outcome markets need different arb logic.

Diagnostic logging was added after the "0 binary markets" bug. It now logs sample market data, skip reasons, and page-by-page progress so you can see exactly what the API is returning.

---

## 23. Rust WebSocket

**File**: `arb-engine/src/ws.rs`

### Connection Architecture

```
                ┌─────────────────┐
WebSocket  ───→ │  ws::connect_   │ ───→  mpsc::channel  ───→  Main Loop
(streaming)     │  and_stream()   │       (10,000 buffer)      (consumes)
                └─────────────────┘
```

The WebSocket reader runs in its own `tokio::spawn` task. It parses messages and sends `BookEvent` objects through a channel. The main loop receives events from the channel.

The 10,000-element buffer means the WebSocket can run ahead of the scanner by up to 25 seconds (at 400 events/sec) without blocking.

### Event Types

```rust
pub enum BookEvent {
    Snapshot(OrderBook),
    Update { token_id: String, bids: Vec<PriceLevel>, asks: Vec<PriceLevel> },
}
```

- **Snapshot**: Complete order book. Received once per token on subscribe. Replaces the entire in-memory book.
- **Update**: Delta. A price level was added, removed, or changed size. Applied incrementally to the existing book. A size of 0 means the level was removed.

### Auto-Reconnect

```rust
pub async fn connect_and_stream(ws_url: String, token_ids: Vec<String>, tx: mpsc::Sender<BookEvent>) {
    loop {
        match run_connection(&ws_url, &token_ids, &tx).await {
            Ok(()) => warn!("WebSocket closed, reconnecting in 2s..."),
            Err(e) => error!("WebSocket error: {}, reconnecting in 2s...", e),
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
}
```

The outer loop never exits. Any connection failure (network drop, server restart, error) triggers a 2-second wait and reconnect. On reconnect, the server sends fresh snapshots for all subscribed tokens, so the in-memory state is rebuilt.

---

## 24. Rust Scanner and Executor

**File**: `arb-engine/src/scanner.rs` and `arb-engine/src/executor.rs`

### Scanner

Maintains a `HashMap<String, OrderBook>` of all 1,000 tokens (500 markets × 2). On each scan:

```rust
fn check_market(&self, market: &MarketPair) -> Option<ArbOpportunity> {
    let yes_ask = self.books.get(&market.yes_token)?.best_ask()?;
    let no_ask  = self.books.get(&market.no_token)?.best_ask()?;

    let total_cost = yes_ask + no_ask;
    if total_cost >= 1.0 { return None; }

    let spread_pct = (1.0 - total_cost) * 100.0;
    if spread_pct < self.min_spread_pct { return None; }

    Some(ArbOpportunity { market, yes_ask, no_ask, total_cost, spread_pct, ... })
}
```

The `?` operator chains give us early-return-on-None behavior: if either book is missing or has no asks, we silently skip to the next market. No error handling needed because missing data = can't determine arb = skip.

### Executor

```rust
pub fn execute(&mut self, opp: &ArbOpportunity) {
    let max_spend = self.config.max_position_usdc
        .min(self.config.max_exposure_usdc - self.total_exposure);

    if max_spend <= 0.0 {
        warn!("No budget left");
        return;
    }

    let shares = max_spend / opp.total_cost;

    if self.config.dry_run {
        info!("[DRY RUN] ARB: {:.1} shares @ ${:.4} profit=${:.4}", ...);
        return;
    }

    // In live mode: would place FOK orders for both YES and NO
    self.total_exposure += opp.total_cost * shares;
}
```

---

## 25. Rust Main Loop

**File**: `arb-engine/src/main.rs`

```rust
#[tokio::main]
async fn main() {
    // 1. Load config from .env
    dotenvy::from_filename("../.env").ok();
    let config = Config::from_env();

    // 2. Fetch markets from Gamma API
    let market_pairs = markets::fetch_binary_markets(&config.gamma_url, 500).await;

    // 3. Extract all token IDs
    let token_ids: Vec<String> = market_pairs.iter()
        .flat_map(|m| vec![m.yes_token.clone(), m.no_token.clone()])
        .collect();
    // 500 markets × 2 = 1,000 token IDs

    // 4. Start WebSocket in background task
    let (tx, mut rx) = mpsc::channel::<BookEvent>(10_000);
    tokio::spawn(ws::connect_and_stream(config.ws_url.clone(), token_ids, tx));

    // 5. Event loop
    while let Some(event) = rx.recv().await {
        // Apply event to in-memory order books
        match event {
            BookEvent::Snapshot(book) => scanner.update_book(book),
            BookEvent::Update { token_id, bids, asks } => { /* apply deltas */ },
        }

        updates_processed += 1;

        // Every 100 events: scan for arb
        if updates_processed % 100 == 0 {
            let opportunities = scanner.scan(&market_pairs);
            for opp in &opportunities {
                executor.execute(opp);
            }
        }

        // Every 5000 events: log stats
        if updates_processed % 5000 == 0 {
            info!("Stats: {} updates | {:.0}/sec | {} arbs found", ...);
        }
    }
}
```

At 400 events/sec:
- Arb scan every 100 events = **4 scans/second**
- Stats log every 5000 events = **every ~12.5 seconds**

---

## 26. Launch Script

**File**: `run.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Auto-detect Python (prefer venv over system)
if [ -f ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

# Build Rust if needed
ARB_BINARY="arb-engine/target/release/arb-engine"
if [ ! -f "$ARB_BINARY" ]; then
    (cd arb-engine && cargo build --release)
fi

# Start both
"$PYTHON" -m src.main &
PY_PID=$!

"$ARB_BINARY" &
RUST_PID=$!

# Clean shutdown on Ctrl+C
trap 'kill $PY_PID $RUST_PID 2>/dev/null; wait' EXIT INT TERM
wait
```

---

# Part IV — Running It

## 27. Configuration

See `.env.example` for all settings. Key ones to tune:

| Setting | Conservative | Aggressive | Why |
|---------|-------------|------------|-----|
| `MIN_ENDGAME_PROB` | 0.95 | 0.88 | Lower catches more opportunities but with higher failure risk |
| `MAX_POSITION_PCT` | 10 | 30 | Higher means larger bets, faster compounding, bigger losses |
| `MAX_TOTAL_EXPOSURE_PCT` | 50 | 90 | Higher means more capital deployed, less reserve |
| `MAX_DRAWDOWN_PCT` | 15 | 50 | Higher gives more runway but risks more capital |
| `ARB_MIN_SPREAD_PCT` | 1.0 | 0.1 | Lower catches thinner arbs, may not be worth execution costs |

## 28. Setup

```bash
# Python
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Rust
cd arb-engine && cargo build --release && cd ..

# Config
cp .env.example .env
# Edit .env: add your private key with 0x prefix

# Run (both bots)
./run.sh

# Run (Python only)
source .venv/bin/activate && python -m src.main

# Run (Rust only)
cd arb-engine && cargo run --release
```

## 29. Risks

**Strategy risks**: Endgame outcomes can surprise (5-10% of the time). Value imbalances can be noise. Correlation lag can be legitimate price differences.

**Execution risks**: Slippage, partial fills, API rate limiting, stale data.

**Platform risks**: Smart contract bugs, regulatory action, API changes.

**Infrastructure risks**: Network outages, process crashes, system clock skew.

**Mitigations**: Position limits, exposure caps, kill switch, duplicate prevention, dry run mode, comprehensive logging.

Always start with `DRY_RUN=true`. Always monitor the first few live trades. The kill switch exists because everything described above can go wrong simultaneously.
