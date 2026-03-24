# The Playbook: Polymarket, Kalshi, and How This Bot Makes Money

A practical breakdown of both major prediction market platforms, how they work under the hood, where money can actually be made, and how our system exploits those opportunities.

---

## Table of Contents

**Part I — The Two Platforms**
1. [Polymarket: The Crypto-Native Exchange](#1-polymarket-the-crypto-native-exchange)
2. [Kalshi: The Regulated Exchange](#2-kalshi-the-regulated-exchange)
3. [Head-to-Head Comparison](#3-head-to-head-comparison)

**Part II — How Money Moves on Prediction Markets**
4. [The Fundamental Economics](#4-the-fundamental-economics)
5. [Where Value Gets Created and Destroyed](#5-where-value-gets-created-and-destroyed)
6. [Why Most People Lose](#6-why-most-people-lose)
7. [The Edges That Actually Work](#7-the-edges-that-actually-work)

**Part III — Our Implementation**
8. [System Architecture at a Glance](#8-system-architecture-at-a-glance)
9. [Strategy 1: Endgame Sniping (Python)](#9-strategy-1-endgame-sniping)
10. [Strategy 2: Value Betting (Python)](#10-strategy-2-value-betting)
11. [Strategy 3: Cross-Market Correlation (Python)](#11-strategy-3-cross-market-correlation)
12. [Strategy 4: Intra-Market Arbitrage (Rust)](#12-strategy-4-intra-market-arbitrage)
13. [Risk Management and Auto-Compounding](#13-risk-management-and-auto-compounding)
14. [Realistic P&L Expectations](#14-realistic-pl-expectations)

**Part IV — The Roadmap**
15. [What We Don't Do Yet (But Could)](#15-what-we-dont-do-yet)
16. [Cross-Platform Arbitrage: The Holy Grail](#16-cross-platform-arbitrage)

---

# Part I — The Two Platforms

## 1. Polymarket: The Crypto-Native Exchange

### What It Is

Polymarket is a prediction market built on the Polygon blockchain. You deposit USDC (a stablecoin pegged 1:1 to the US dollar), buy outcome tokens, and collect $1.00 per winning token when the market resolves. It is the largest prediction market in the world by volume, processing over $500 million monthly as of 2026.

### How a Trade Actually Happens

To understand where money can be made, you need to understand the full lifecycle of a trade.

**Step 1: Funding.**
You transfer USDC to your Polygon wallet. Polymarket supports deposits via credit card, bank transfer, or direct crypto transfer. Your wallet is an Ethereum-compatible address (the same private key works on Ethereum mainnet, Polygon, and other EVM chains). Internally, your USDC sits in a smart contract that Polymarket's exchange can access when you sign orders.

**Step 2: The Order Book.**
Polymarket uses a Central Limit Order Book (CLOB) — the exact same mechanism that powers the NYSE and NASDAQ. This is not an AMM (Automated Market Maker) like Uniswap. The distinction matters because:

- An AMM uses a mathematical formula (constant product: x * y = k) to set prices. You trade against a pool of liquidity, and the price moves along a curve. Slippage is predictable but often significant.
- A CLOB matches individual buy orders against individual sell orders. You can see every resting order at every price level. You can place a limit order that sits on the book until someone fills it. Slippage depends on depth.

Polymarket's CLOB is a **hybrid system**: order matching happens off-chain (on Polymarket's servers, for speed), but settlement happens on-chain (on the Polygon blockchain, for trust). This is the same architecture that dYdX and other high-performance DEXs use. It gives you centralized exchange speed with decentralized settlement guarantees.

Example order book for "Will Bitcoin exceed $100K by July 2026?" YES token:

```
ASKS (sellers willing to sell YES)
  $0.42 × 1,500 shares     ← best ask (cheapest YES available)
  $0.43 × 3,200 shares
  $0.45 × 8,000 shares
  $0.50 × 12,000 shares

  ---- spread = $0.03 ----

BIDS (buyers willing to buy YES)
  $0.39 × 2,000 shares     ← best bid
  $0.38 × 4,500 shares
  $0.35 × 6,000 shares
  $0.30 × 10,000 shares
```

If you place a **market buy** for 1,000 YES shares, you take the $0.42 ask. Cost: $420. If the market resolves YES, you get $1,000 back. Profit: $580.

If you place a **limit buy** at $0.39, your order rests on the bid side until a seller agrees to sell at that price.

**Step 3: Token Mechanics.**
When your order is matched, Polymarket mints ERC-1155 tokens on the Polygon blockchain. Each market has two token types: YES and NO. These tokens are the *actual assets* you own — they're transferable NFTs on the blockchain. This is important because it means:

- Your positions survive even if Polymarket's website goes down.
- You can verify your holdings independently on Polygonscan.
- The $1.00 payout per winning token is enforced by a smart contract, not by Polymarket's goodwill.

The token framework is called the **Conditional Token Framework (CTF)**, originally developed by Gnosis. A CTF split works like this: you take $1.00 of collateral (USDC) and split it into one YES token + one NO token. Exactly one of these will be redeemable for $1.00. The other becomes worthless.

For some markets, Polymarket uses **negRisk** — a variation where tokens are shares of a negative risk set. This matters for multi-outcome markets (like "Who will win the Oscar for Best Picture?" with 10 nominees). In negRisk markets, you don't buy YES directly — you buy a position that pays out if a specific outcome wins. The mechanics are similar, but the token IDs and the signing process differ. Our bot checks the `neg_risk` flag on every market and adjusts accordingly.

**Step 4: Resolution.**
When the event occurs, the market needs to "resolve" — someone has to declare which outcome won. Polymarket uses UMA's Optimistic Oracle for this:

1. Anyone can **propose** a resolution by posting a bond (~$750 USDC).
2. A **2-hour challenge window** opens. If nobody disputes the proposal, the market resolves and the proposer gets their bond back.
3. If disputed, a **counter-bond** is posted and the dispute escalates to a second round.
4. If still disputed, it goes to a **UMA token holder vote** (~48 hours).

This system is designed to be fast in the common case (2 hours) but robust against manipulation. Historically, 92-97% of markets resolve without dispute. When disputes happen, it's usually on politically contentious markets.

Why this matters for trading: **resolution latency is your enemy for endgame sniping.** If you buy a $0.95 token and the market takes 48 hours to resolve due to a dispute, your capital is locked earning 5% return over 48 hours instead of 2 hours. That's a 24x difference in annualized return.

### Polymarket's API Stack

Polymarket exposes three APIs, each serving a different purpose:

| API | Base URL | Purpose |
|-----|----------|---------|
| **Gamma API** | `https://gamma-api.polymarket.com` | Market metadata: questions, outcomes, end dates, volumes, token IDs. This is where you discover what markets exist. |
| **CLOB API** | `https://clob.polymarket.com` | Order books, order placement, trade execution. This is where you trade. |
| **WebSocket API** | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | Real-time order book streaming. Pushes every price change as it happens. |

**Authentication** uses two levels:

- **L1 (API key creation)**: You sign an EIP-712 message with your Ethereum private key. This proves wallet ownership and returns API credentials (key, secret, passphrase).
- **L2 (trading)**: Every subsequent request is signed with HMAC-SHA256 using the API secret. This is faster than signing with your private key every time.

### Order Types

| Type | Behavior | When to Use |
|------|----------|-------------|
| **GTC** (Good-Til-Cancelled) | Sits on the book forever until filled or manually cancelled | Passive limit orders; you're a market maker |
| **GTD** (Good-Til-Date) | Like GTC but auto-expires at a timestamp you specify | Time-sensitive bets; "I want this price, but only until the debate starts" |
| **FOK** (Fill-Or-Kill) | Must fill the entire quantity immediately, or the whole order is cancelled | Aggressive takes; our arbitrage bot uses this because partial fills create risk |
| **FAK** (Fill-And-Kill) | Fills as much as possible immediately, cancels the rest | When you want liquidity but can accept partial fills |

### Fee Structure

The majority of Polymarket markets have **zero trading fees**. This is a major structural advantage for strategies like arbitrage, where even a 0.5% fee can eat your entire edge.

Fees only apply to specific market categories:

- **15-minute crypto markets** (BTC, ETH, SOL, XRP): 0.25% fee rate, up to 1.56% effective rate at 50% probability
- **Serie A markets**: 1.75% fee rate, up to 0.44% effective at 50%
- **NCAAB markets**: Same as Serie A

The fee formula is: `fee = contracts × price × feeRate × (price × (1 - price))^exponent`. This means fees peak at 50% probability and decrease toward the extremes (near 0% or 100%). For endgame sniping (buying at 90%+), effective fees are negligible even on fee-bearing markets.

Polymarket also offers **maker rebates**: 25% of collected fees on sports markets, 20% on crypto markets, redistributed daily to market makers.

---

## 2. Kalshi: The Regulated Exchange

### What It Is

Kalshi is the first CFTC-regulated prediction market exchange in the United States. It operates as a Designated Contract Market (DCM) — the same regulatory category as the Chicago Mercantile Exchange (CME). This means it follows traditional finance rules: KYC (Know Your Customer), segregated funds, and CFTC oversight.

### How It Differs Fundamentally

Where Polymarket is crypto-native (blockchain settlement, token-based positions, pseudonymous accounts), Kalshi is tradfi-native (centralized settlement, contract-based positions, verified identities).

**Funding.**
You deposit USD via bank transfer (ACH), wire, or credit card. Your money sits in an FDIC-protected account. There are no crypto wallets, no gas fees, no bridging between networks. This is the experience most Americans are used to.

**Contracts, Not Tokens.**
On Kalshi, you buy and sell "event contracts" — standardized binary options. A YES contract costs between $0.01 and $0.99 and pays out $1.00 if the event occurs. The difference from Polymarket: these are **not tokens on a blockchain.** They're entries in Kalshi's centralized database. You cannot transfer them, verify them independently, or access them if Kalshi goes offline.

This centralization has tradeoffs:

| Aspect | Polymarket (Decentralized) | Kalshi (Centralized) |
|--------|--------------------------|---------------------|
| Position visibility | On-chain, verifiable by anyone | In Kalshi's database only |
| Counterparty risk | Smart contract holds funds | Kalshi holds funds (FDIC protected) |
| Censorship resistance | High (blockchain settlement) | Low (centralized operator) |
| Speed | ~2s block confirmation + off-chain matching | Sub-second matching |
| Account recovery | You control your private key | KYC-based account recovery |

**Resolution.**
Kalshi uses a centralized oracle. They designate official data sources (Bureau of Labor Statistics, Associated Press, official election results, etc.) and a Kalshi employee triggers resolution when the data source publishes. There is no dispute mechanism like UMA — Kalshi's resolution is final.

This is faster (usually minutes to hours after the event) but requires trust in Kalshi's operations. In practice, Kalshi has been reliable since launch, but the centralization is a philosophical difference from Polymarket's trust-minimized approach.

### Kalshi's API

Kalshi offers three API interfaces:

| Interface | Purpose | Speed |
|-----------|---------|-------|
| **REST API v2** | `https://api.elections.kalshi.com/trade-api/v2` — Order placement, market data, portfolio management | ~50-200ms |
| **WebSocket** | `wss://api.elections.kalshi.com/trade-api/ws/v2` — Real-time price streaming, fill notifications | Sub-10ms |
| **FIX 4.4** | Low-latency institutional trading protocol | Sub-1ms |

**Authentication** uses RSA-PSS signatures. You generate an RSA key pair, register the public key with Kalshi, and sign every request with the private key. Every request includes a `KALSHI-ACCESS-SIGNATURE` header containing a signed timestamp + method + path.

**Rate limits** are tiered:

| Tier | Requests/sec | Requirement |
|------|-------------|-------------|
| Basic | 20 | Default |
| Standard | 50 | ~$108M monthly volume |
| Premier | 100 | ~$217M monthly volume |
| Prime | 400 | ~$435M monthly volume |

For a $10 bankroll, you're in the Basic tier. 20 req/s is fine for our strategies.

### Fee Structure

Kalshi's fee formula: `fee = ceil(0.07 × contracts × price × (1 - price))`

This means:
- At 50% probability ($0.50): maximum fee of $0.0175 per contract (1.75%)
- At 90% probability ($0.90): fee of $0.0063 per contract (0.63%)
- At 10% probability ($0.10): fee of $0.0063 per contract (0.63%)

**Maker fees** are 25% of taker fees: `ceil(0.0175 × contracts × price × (1 - price))`

Kalshi has advertised zero fees on some market categories (notably politics), but the standard formula applies to most markets.

### Order Types

| Type | Behavior |
|------|----------|
| **Limit** | Rests on the book at specified price |
| **Market** | Takes best available price immediately |

Kalshi's order types are simpler than Polymarket's. No GTD, no FAK — just limit and market. This reflects its tradfi heritage.

---

## 3. Head-to-Head Comparison

### For a $10 Bankroll Trader

| Factor | Polymarket | Kalshi | Winner for Us |
|--------|-----------|-------|---------------|
| **Minimum trade** | ~$0.01 | $0.01 per contract | Tie |
| **Fees on most markets** | 0% | 0.63-1.75% | Polymarket |
| **KYC required** | No (international) | Yes | Polymarket |
| **API access** | Free, no tier limits | Free, 20 req/s limit | Polymarket |
| **Market coverage** | ~1,000 active | ~350,000 active | Kalshi |
| **Liquidity (non-sports)** | Higher | Lower | Polymarket |
| **Liquidity (sports)** | Good | Better | Kalshi |
| **Resolution speed** | 2 hours to 5 days | Minutes to hours | Kalshi |
| **WebSocket data** | Free, real-time | Free, real-time | Tie |
| **US legal access** | Only via Polymarket US (limited) | Full access | Kalshi |
| **Crypto deposits** | Yes | No | Depends |
| **Smart contract guarantees** | Yes | No | Polymarket |

### For a Bot

The critical factors for automated trading:

**Latency.** Kalshi's FIX 4.4 protocol is faster than Polymarket's REST API. But for our strategies (endgame sniping, value betting), we're operating on seconds-to-minutes timeframes, not milliseconds. Latency matters most for arbitrage.

**Fee impact on edge.** With zero fees on most Polymarket markets, a 2% arbitrage edge is pure profit. On Kalshi, that same 2% edge shrinks to 0.25-1.37% after fees. For a $10 bankroll, this difference matters.

**Market diversity.** Polymarket has fewer markets but each is more liquid. Kalshi has massive market count but thinner books. More markets = more scanning work but more opportunities.

**Authentication complexity.** Polymarket requires EIP-712 + HMAC-SHA256 signing. Kalshi requires RSA-PSS signing. Both are well-supported in Python and Rust.

### Why We Chose Polymarket First

1. **Zero fees** on most markets — preserves thin edges on our small bankroll.
2. **No KYC** — faster to get started.
3. **On-chain settlement** — positions are verifiable; reduces counterparty risk.
4. **Better SDK** — `py-clob-client` is a mature Python library that handles authentication, signing, and order placement.
5. **Higher non-sports liquidity** — our strategies (endgame, value, correlation) focus on politics, crypto, and current events where Polymarket dominates.

---

# Part II — How Money Moves on Prediction Markets

## 4. The Fundamental Economics

### Zero-Sum vs. Negative-Sum

At the contract level, prediction markets are **zero-sum**: for every winning dollar, there's a losing dollar. But at the portfolio level, after fees and slippage, they're **slightly negative-sum** for the average participant. Kalshi charges fees on every trade. Polymarket charges fees on some markets. Both have bid-ask spreads that eat into returns.

This means: **the average trader loses money.** To be profitable, you must have a systematic edge that compensates for these frictions.

### Where Does the Money Come From?

Your profits come from other participants' mistakes:

1. **Recreational bettors** who trade on vibes, not math. They bet on "Will my team win?" based on loyalty, not probability. They overpay for long shots and underpay for favorites.

2. **Late reacters** who don't update fast enough when news breaks. When the Associated Press calls a primary result, the first person to buy the winning token at the old price profits.

3. **Liquidity providers** who set their spreads too wide (creating value betting opportunities) or too narrow (creating arbitrage opportunities when they should widen).

4. **Panickers** who dump positions at fire-sale prices when volatility spikes. If the market drops from $0.50 to $0.35 on a rumor that turns out to be false, the person who bought at $0.35 profits when it rebounds.

5. **Mispriced market makers** who don't account for correlation between markets. If "Bitcoin above $80K" reprices but "Bitcoin above $75K" doesn't move, the second market is mechanically mispriced.

### Expected Value: The Only Metric That Matters

Every trade should be evaluated on **Expected Value (EV):**

```
EV = (probability_of_winning × payout) − (probability_of_losing × cost)
```

Example: You buy a YES token at $0.92 in a market that you estimate has a 96% chance of resolving YES.

```
EV = (0.96 × $1.00) − (0.04 × $0.92)
   = $0.96 − $0.0368
   = $0.9232
```

Since $0.9232 > $0.92 (the cost), this is a **positive EV** trade. The edge is $0.0032 per share, or about 0.35%.

Is 0.35% worth it? On a single trade, barely. But if you make this trade 100 times, expected total profit is $0.32 per share × 100 = $32 on ~$92 of capital. That's a 34.8% return — from a tiny, seemingly negligible edge repeated consistently.

This is the core philosophy of all our strategies: **find small, positive-EV edges and execute them repeatedly.**

---

## 5. Where Value Gets Created and Destroyed

### Value Creation Points

**New information.** When a news event occurs that changes the probability of an outcome, there's a brief window where the market price lags the new reality. The person who trades first captures the value between the old price and the new true probability.

**Resolution certainty.** As an event approaches and the outcome becomes increasingly obvious, the price asymptotically approaches $1.00 or $0.00. But it never quite gets there until formal resolution. The gap between $0.95 and $1.00 is real money that the market "hasn't distributed yet."

**Structural inefficiency.** Order books don't perfectly balance. Sometimes YES + NO asks add up to $0.97 instead of $1.00. This is free money for anyone fast enough to grab it.

**Cross-market lag.** When 8 Bitcoin markets exist with different thresholds ($70K, $75K, $80K, etc.), a move in one doesn't instantly propagate to all others. The lag is value waiting to be captured.

### Value Destruction Points

**Fees.** Every fee-bearing trade destroys a small amount of value.

**Slippage.** The difference between the price you expect and the price you get. In thin markets, buying 100 shares can move the price 2-3%.

**Resolution risk.** A disputed resolution on Polymarket can lock your capital for 5+ days. The opportunity cost of that locked capital destroys value.

**Gas costs.** On Polygon, gas is cheap (~$0.01 per transaction) but not free. For micro-trades on a $10 bankroll, gas adds up.

---

## 6. Why Most People Lose

Research shows roughly **80% of prediction market participants are net losers.** Here's why:

### Overconfidence Bias
People overestimate their ability to predict outcomes. "I follow politics closely, so I know who'll win" — but the market already prices in all public information. Your surface-level knowledge is already reflected in the price.

### Favorite-Longshot Bias
People systematically overpay for low-probability outcomes (longshots) and underpay for high-probability outcomes (favorites). A 5% probability event at $0.05 is "only a nickel!" — but that nickel is usually overpriced at $0.05 when the true probability is 3%. Meanwhile, a 95% probability event at $0.95 feels like "paying too much" when it's actually a bargain.

This bias is well-documented in horse racing, sports betting, and prediction markets. It's one of the reasons endgame sniping works — high-probability tokens are systematically under-bought.

### Emotional Trading
Humans buy on excitement and sell on fear. A market drops from $0.60 to $0.40 on a scary headline, and a human panic-sells. A bot doesn't.

### Ignoring Liquidity
Buying a token at $0.50 doesn't matter if you can't sell it when you need to. Thin order books with no bids below your entry price mean you're trapped. Most retail traders don't check order book depth before trading.

### Not Accounting for Time Value
A $0.92 token that pays $1.00 in 2 hours has a very different return profile than a $0.92 token that pays $1.00 in 30 days. Most traders just look at the potential profit ($0.08) without considering the annualized return.

- 2-hour resolution: 8% return in 2 hours = ~35,000% annualized
- 30-day resolution: 8% return in 30 days = ~97% annualized

Both are good, but the first is 360x better in terms of capital efficiency.

---

## 7. The Edges That Actually Work

Based on academic research and real trading results on Polymarket in 2024-2026:

### Edge 1: Speed (Arbitrage)
**What:** Buy YES + NO when their asks sum below $1.00.
**Why it works:** Order books briefly misprice due to asynchronous updates. One side adjusts before the other.
**Typical edge:** 0.5-3% per trade.
**Competition:** Extremely fierce. 73% of arb profits go to sub-100ms bots. Average window: 2.7 seconds in 2026 (down from 12.3 seconds in 2024).
**Our approach:** Rust engine with WebSocket streaming for minimum latency.

### Edge 2: Near-Certainty Discount (Endgame Sniping)
**What:** Buy tokens priced at $0.88-$0.98 for events with >88% probability of occurring.
**Why it works:** The favorite-longshot bias in reverse. Many traders exit profitable positions early ("I've already doubled my money, time to sell"). The few remaining shares near expiry trade at a slight discount to true probability.
**Typical edge:** 2-12% per trade, but must account for the 4-8% of the time the "certain" outcome doesn't happen.
**Competition:** Moderate. Requires market-specific knowledge to estimate true probability.
**Our approach:** Python scanner with composite scoring (profit, time-to-resolution, volume, bid depth).

### Edge 3: Order Book Asymmetry (Value Betting)
**What:** Detect markets where bid depth is 3x+ the ask depth, suggesting directional pressure that hasn't fully repriced.
**Why it works:** Large limit orders (bids) signal informed traders accumulating a position. The current ask price hasn't caught up to this pressure yet.
**Typical edge:** 3-10%, but higher risk (these are directional bets, not structural).
**Competition:** Low for retail-sized trades. Market makers see the same signals but can't profitably act on them at every price level.
**Our approach:** Python scanner with imbalance ratio detection and wide-spread analysis.

### Edge 4: Correlation Lag (Cross-Market)
**What:** When a group of related markets exists (Bitcoin at various price thresholds), buy the laggard when the leader moves.
**Why it works:** Market makers and liquidity providers adjust one market at a time. The re-pricing ripples through related markets over seconds to minutes.
**Typical edge:** 5-15%, but dependent on the correlation holding.
**Competition:** Low-medium. Requires building a classification system for which markets are correlated.
**Our approach:** Python scanner with regex-based market grouping and lag detection.

### Edge 5: Cross-Platform Arbitrage (Not Yet Implemented)
**What:** Same event, different price on Polymarket vs. Kalshi.
**Why it works:** Different user bases, regulatory constraints, and information processing speeds create persistent price gaps.
**Typical edge:** 2.5-6.8%, lasting 2-15 seconds.
**Competition:** Very high for automated execution. Lower for larger, slower-moving divergences.
**Our approach:** Not yet implemented — requires Kalshi API integration.

---

# Part III — Our Implementation

## 8. System Architecture at a Glance

```
┌────────────────────────────────────────────────────────┐
│                     run.sh (launcher)                  │
│  Starts both processes, handles graceful shutdown       │
├──────────────────────┬─────────────────────────────────┤
│                      │                                 │
│   Python Strategy    │      Rust Arbitrage             │
│   Bot (src/)         │      Engine (arb-engine/)       │
│                      │                                 │
│   ┌──────────┐       │      ┌──────────────┐          │
│   │ Scanner  │       │      │ WebSocket    │          │
│   │ (REST)   │       │      │ Client       │          │
│   │ 500 mkts │       │      │ (real-time)  │          │
│   │ every    │       │      │              │          │
│   │ 18 sec   │       │      └──────┬───────┘          │
│   └────┬─────┘       │             │                   │
│        │             │      ┌──────▼───────┐          │
│   ┌────▼─────┐       │      │ Arb Scanner  │          │
│   │Strategies│       │      │ YES+NO<$1?   │          │
│   │•Endgame  │       │      └──────┬───────┘          │
│   │•Value    │       │             │                   │
│   │•Correltn │       │      ┌──────▼───────┐          │
│   └────┬─────┘       │      │ Executor     │          │
│        │             │      │ (FOK orders) │          │
│   ┌────▼─────┐       │      └──────────────┘          │
│   │ Risk Mgr │       │                                 │
│   │ Executor │       │                                 │
│   │ Dashboard│       │                                 │
│   └──────────┘       │                                 │
│                      │                                 │
│   Scan: 18s cycle    │      Scan: on every WS event    │
│   Latency: ~200ms    │      Latency: <10ms             │
│   API: Gamma+CLOB    │      API: WebSocket+CLOB        │
│   Lang: Python 3.11+ │      Lang: Rust (tokio async)   │
└──────────────────────┴─────────────────────────────────┘
```

**Why two languages?** Endgame, value, and correlation strategies operate on a 5-18 second scan cycle — Python's ~200ms API response time is irrelevant when you're sleeping for 5 seconds between scans. Arbitrage operates on sub-second windows — every millisecond of latency is lost money. Rust with `tokio` and WebSocket streaming gives us event-driven, zero-overhead processing.

---

## 9. Strategy 1: Endgame Sniping

### The Theory

A market asks "Will Team X win the championship?" The championship game ended 10 minutes ago and Team X won. The YES token is trading at $0.93 because the market hasn't formally resolved yet (UMA needs 2 hours). Everyone *knows* the outcome, but the token can't be redeemed until resolution.

Why isn't it at $0.99? Several reasons:

1. **Opportunity cost**: $0.07 profit over 2 hours is 3.5% — good but not amazing. Some traders exit to deploy capital elsewhere.
2. **Resolution risk**: There's a small chance someone disputes the resolution, locking funds for days.
3. **Thin liquidity near resolution**: Market makers widen spreads when resolution is imminent because they don't want to be the last person holding inventory.

Our bot buys these tokens at $0.88-$0.98, holds until resolution, and collects $1.00.

### How We Find Them

The scanner pulls the top 500 markets by volume from the Gamma API, then for each market:

1. **Check volume** — minimum $1,000. Below this, the market is too illiquid and the order book data is unreliable.
2. **Check time to resolution** — maximum 14 days. Beyond this, capital is locked too long.
3. **For each token, check the best ask price** — must be between $0.88 and $0.98.
4. **Score the opportunity** using four weighted factors:

| Factor | Weight | Logic |
|--------|--------|-------|
| Profit per share | 35% | `(1.0 - price) / price × 100`, capped at 100 |
| Time to resolution | 30% | `100 - (days × 7)`, so closer = better |
| Volume | 20% | `log10(volume) × 20`, rewards liquid markets |
| Bid depth | 15% | Sum of bid sizes × 10, rewards exit liquidity |

### The Math on a $10 Bankroll

Suppose we find a token at $0.93 resolving in 6 hours:

- Position size: 20% of $10 = $2.00
- Shares bought: $2.00 / $0.93 = 2.15 shares
- Payout if correct: 2.15 × $1.00 = $2.15
- Profit: $0.15 (7.5% return in 6 hours)
- Annualized: ~10,950% (but we can't compound this continuously)

If we find 3 of these per day and compound:

| Day | Bankroll | Trades | Profit |
|-----|----------|--------|--------|
| 1 | $10.00 | 3 | $0.45 |
| 7 | $13.15 | 21 | $2.87 |
| 30 | $36.78 | 90 | $22.43 |

These numbers assume a 100% hit rate, which is unrealistic. With a 90% hit rate (10% of "sure things" fail), expected daily return drops from ~4.5% to ~2.6% — still strong.

### Risk

The biggest risk is the 4-12% of the time a "near-certain" outcome doesn't resolve as expected. Examples:

- A recount reverses an election result
- An API call is disputed and resolution takes days
- A market is declared "void" due to ambiguous resolution criteria

Our mitigation: position sizing. No single position exceeds 20% of bankroll. A total loss on one endgame trade costs $2 on a $10 bankroll — painful but survivable.

---

## 10. Strategy 2: Value Betting

### The Theory

Order books reveal information that the current price doesn't fully reflect. Two specific patterns:

**Pattern A: Bid-Ask Imbalance.**
If the bid side has $5,000 in resting orders and the ask side has $500, someone (or many someones) believes the price should be higher. They're accumulating at the current price. The ask-side thinness means a single market buy will push the price up. We buy before that happens.

Why the price hasn't moved yet: the imbalance exists in *resting* orders (limits), not in *matched* orders (fills). The market price only changes when orders actually fill. A large bid wall signals intent but not yet execution.

**Pattern B: Wide Spread.**
A market has best bid at $0.40 and best ask at $0.48 — an $0.08 spread. This usually means the market maker has withdrawn or thinned out. The "true" price is likely near the midpoint ($0.44). Buying at $0.48 when fair value is $0.44 is a losing trade, but if the midpoint is $0.44 and we buy at $0.44 by placing a limit order at that price, we capture the reversion when the spread tightens.

In our implementation, we actually buy the ask in wide-spread markets where the midpoint is *above* the ask — which only happens in specific conditions where the bid side is much deeper.

### How We Find Them

For each token in each market:

1. **Skip extremes** — ignore prices below $0.15 or above $0.85. At the extremes, the order book dynamics are dominated by resolution mechanics, not value.
2. **Calculate imbalance** — bid_depth / ask_depth. If this ratio exceeds 3.0, significant directional pressure exists.
3. **Estimate fair value** — `price + min(log2(imbalance_ratio) × 0.03, 0.10)`. The logarithm prevents wild estimates from extreme imbalances.
4. **Require minimum edge** — at least 3% estimated edge for imbalance, 2% for wide spread.
5. **Score** — edge (40%), volume (25%), depth (20%), minus a spread penalty (15%).

### Risk

Value betting is our highest-risk strategy because it's **directional** — we're betting on a price move, not a structural inefficiency. If the imbalance reverses (the large bidder cancels their orders), our position loses money. We mitigate this with position limits and by requiring a large imbalance (3x) before acting.

---

## 11. Strategy 3: Cross-Market Correlation

### The Theory

Polymarket often has clusters of related markets:

- "Bitcoin above $70K by March" — YES at $0.82
- "Bitcoin above $75K by March" — YES at $0.65
- "Bitcoin above $80K by March" — YES at $0.40
- "Bitcoin above $85K by March" — YES at $0.22

These prices should move in a correlated way. If Bitcoin rallies and the $70K market moves to $0.90, the $75K market *should* also move up (maybe to $0.73). But it might lag at $0.65 for a few minutes because:

1. Different market makers cover different markets.
2. Liquidity varies — the $70K market might have 10x the volume.
3. Repricing is manual for many participants — they update one position at a time.

We buy the laggard ($0.65 when group average suggests it should be higher) and profit when it converges.

### How We Find Them

1. **Classify markets** into groups using regex patterns (bitcoin/btc, ethereum/eth, trump, temperature, S&P 500, etc.).
2. **Build groups** — for each group, collect all token prices between $0.10 and $0.95.
3. **Find laggards** — compute group average price, identify members trading 5%+ below the average.
4. **Score** — lag percentage (50%), volume (30%), group size (20%).

### Risk

Correlation isn't causation, and it isn't always synchronous. "Bitcoin above $70K" and "Bitcoin above $85K" are *related* but not *identical* — the $85K market should always trade lower. Our strategy accounts for this by comparing to the group average rather than the leader, but false signals occur when group members have genuinely different probabilities (which they often do). This strategy generates fewer trades than endgame sniping but with larger theoretical edges.

---

## 12. Strategy 4: Intra-Market Arbitrage

### The Theory

For any binary market: YES token pays $1.00 if the event occurs, NO token pays $1.00 if it doesn't. Exactly one must happen. Therefore, buying 1 YES + 1 NO should cost $1.00.

If the order book has:
- YES best ask: $0.42
- NO best ask: $0.55
- Total: $0.97

Buy both. Cost: $0.97. Guaranteed payout: $1.00. Profit: $0.03 per share (3.1%).

### Why We Use Rust

This opportunity exists for 2.7 seconds on average (2026 data). Our Rust engine:

1. **WebSocket connection** — receives order book updates in real-time as they happen. No polling.
2. **BTreeMap order books** — sorted data structure gives O(1) best bid/ask lookup and O(log n) insertions. We use integer keys (price × 10000) to avoid floating-point comparison issues.
3. **Event-driven scanning** — every order book update triggers an arb check. We don't wait for a scan cycle.
4. **FOK execution** — Fill-Or-Kill orders ensure we either get the full position or nothing. Partial fills in arb create risk (you're long YES without the matching NO).

### The Pipeline

```
WebSocket event arrives
        │
        ▼
Parse JSON → BookEvent (token_id, bids, asks)
        │
        ▼
scanner.update_book(book)    ← O(n log n) for n price levels
        │
        ▼
Every 100 updates: scanner.scan(markets)
        │
        ▼
For each MarketPair:
  yes_ask = yes_book.best_ask()?    ← O(1), first key in BTreeMap
  no_ask  = no_book.best_ask()?     ← O(1)
  if yes_ask + no_ask < 1.0 && spread > min_spread_pct:
      executor.execute(opportunity)
```

### Why Every 100 Updates?

Scanning every single WebSocket update would be wasteful — most updates don't change the best ask price, they just add/remove depth at inner levels. Batching every 100 updates gives us ~1-2 scans per second (at typical update rates of 100-200/sec) while keeping CPU usage low. If a significant price change occurs that creates an arb, it persists until someone takes it — we'll catch it on the next scan.

---

## 13. Risk Management and Auto-Compounding

### The Risk Framework

Every trade, across all strategies, passes through the risk manager before execution.

**Position size cap:** No single trade exceeds 20% of effective bankroll.

**Total exposure cap:** All open positions combined cannot exceed 80% of effective bankroll. The remaining 20% is a cash buffer for:
- Gas fees
- Unexpected opportunities
- Drawdown absorption

**Kill switch:** If drawdown exceeds 30% of effective bankroll, all trading stops. This prevents catastrophic losses during a string of bad trades or a market anomaly.

**Duplicate prevention:** Before entering any trade, the risk manager checks:
- Do we already hold this token? (prevents doubling down)
- Do we already have a position in this market? (prevents conflicting bets)

### Auto-Compounding

The effective bankroll grows with wins:

```
effective_bankroll = initial_bankroll + realized_pnl
```

If we start with $10 and make $2 in realized profits, our effective bankroll becomes $12. Position sizes scale up automatically:

- Max position: 20% × $12 = $2.40 (was $2.00)
- Max exposure: 80% × $12 = $9.60 (was $8.00)

This creates exponential growth when winning. A $10 bankroll making 2% per day compounds to $73.28 in 100 days. Without compounding, it would be $30.

The flip side: losses also compound. A drawdown from $12 to $9 means smaller positions ($1.80 max instead of $2.40), which means slower recovery. This is intentional — the system becomes more conservative when losing, which prevents ruin.

### Bankroll Trajectory Simulation

For a $10 starting bankroll, here's what different average daily returns look like over 90 days, assuming auto-compounding:

| Daily Return | Day 30 | Day 60 | Day 90 |
|-------------|--------|--------|--------|
| 1.0% | $13.49 | $18.17 | $24.51 |
| 2.0% | $18.11 | $32.81 | $59.46 |
| 3.0% | $24.27 | $58.92 | $143.02 |
| 5.0% | $43.22 | $186.79 | $807.17 |

These numbers look exciting, but achieving a consistent daily return is extremely hard. A more realistic scenario:

- 60% of days: +2% (endgame trades land)
- 25% of days: 0% (no opportunities found, or opportunities too thin)
- 15% of days: -3% (a "sure thing" fails, or value bet goes wrong)

Expected daily return: `(0.60 × 0.02) + (0.25 × 0) + (0.15 × -0.03)` = **+0.75%**

At 0.75% daily, compounded: $10 → $12.51 (30 days) → $15.63 (60 days) → $19.53 (90 days).

---

## 14. Realistic P&L Expectations

### Best Case

All strategies fire regularly. Multiple endgame opportunities per day, occasional value and correlation hits, rare but profitable arb captures.

- Month 1: $10 → $18-25
- Month 3: $25 → $50-80
- Month 6: $80 → $200-400

### Base Case

Endgame opportunities are sporadic (1-2 per day). Value and correlation rarely trigger due to high thresholds. Arb windows are captured by faster bots.

- Month 1: $10 → $12-15
- Month 3: $15 → $20-30
- Month 6: $30 → $50-80

### Worst Case

Markets are efficient, arb windows are instantly captured by institutional bots, endgame opportunities exist but our estimation of "near-certain" is wrong 20% of the time.

- Month 1: $10 → $7-10
- Month 3: $10 → $5-10 (kill switch triggers, manual restart)

### Why These Numbers Are Honest

Professional market makers on Polymarket (Theo4, Fredi9999) have made millions — but with multi-million-dollar bankrolls, custom infrastructure, and full-time teams. A $10 retail bot is competing in the same markets with vastly fewer resources. Our edge is that we're seeking opportunities they ignore (too small for them, perfect size for us). A $2 endgame trade isn't worth a market maker's attention, but it's 20% of our bankroll.

---

# Part IV — The Roadmap

## 15. What We Don't Do Yet (But Could)

### Market Making
Place simultaneous buy and sell limit orders around the midpoint, capturing the spread. Polymarket's liquidity rewards program pays additional incentives for tight quotes. This is the most consistent strategy for large bankrolls ($10K+) but requires sophisticated inventory management. On a $10 bankroll, the capital requirements make this impractical — you need enough to maintain both sides of the book.

### AI-Powered Probability Estimation
Train a model to estimate true event probabilities from news, polls, and historical data. When the model's estimate diverges significantly from the market price, trade. This is what some top Polymarket traders reportedly do. Requires ML infrastructure, training data, and careful backtesting.

### Copy Trading
Follow successful traders' on-chain transactions (visible on Polygonscan) and replicate their trades. Described as "the most rational approach for most people" because it outsources the hard problem (picking winners) to someone else. Implementation: subscribe to wallet activity for known successful addresses, replicate with a delay.

### Multi-Outcome Arbitrage
For markets with 3+ outcomes (like "Who will win the election?" with 5 candidates), the sum of all YES prices should equal $1.00. If it doesn't, buy the underpriced combination. More complex than binary arb but can have larger edges because fewer bots monitor multi-outcome markets.

### Settlement Timing Arbitrage
Kalshi settles sports events in minutes (via AP calls). Polymarket takes 2+ hours (UMA oracle). If a game ends and Kalshi settles at $1.00 for Team A, buy Team A YES on Polymarket at $0.96 (where it's still waiting for UMA resolution). This requires accounts on both platforms and fast capital deployment.

---

## 16. Cross-Platform Arbitrage: The Holy Grail

### The Opportunity

Polymarket and Kalshi often have the same markets at different prices. Documented divergences:

| Event Type | Avg. Divergence | Duration | Frequency |
|------------|----------------|----------|-----------|
| US Elections | 5.1-6.8% | up to 15.4 seconds | High (during election season) |
| Election Primaries | 3.5-4.2% | ~8.3 seconds | Medium |
| Crypto Events | 2-4% | 3-7 seconds | Daily |
| Sports | 2-5% | During peak betting | Daily |
| International Politics | 3-7% | 3-7 seconds | Irregular |

### Why They Diverge

1. **User base difference**: Polymarket skews international, crypto-savvy. Kalshi skews US, tradfi-savvy. They process information differently and at different speeds.

2. **Regulatory latency**: Kalshi's compliance requirements add 2-7 seconds of processing delay for non-US events.

3. **Fee asymmetry**: Zero fees on Polymarket vs. 0.6-1.75% on Kalshi mean the break-even price is different on each platform. A $0.50 token on Polymarket is equivalent to a $0.51-$0.52 token on Kalshi after fees.

4. **Settlement timing**: Kalshi settles in hours; Polymarket takes hours to days. This creates a window where one platform has paid out and the other hasn't.

### What It Would Take

To implement cross-platform arb:

1. **Kalshi API integration**: RSA-PSS authentication, REST + WebSocket clients, order placement.
2. **Price normalization**: Adjust for fee differences between platforms.
3. **Simultaneous execution**: Buy on the cheap platform and sell on the expensive platform within the same 2-7 second window.
4. **Capital on both platforms**: Need USDC on Polymarket and USD on Kalshi. Can't instantly move money between them.
5. **Market matching**: Map Polymarket market slugs to Kalshi tickers for the same event — no standard exists, this is a fuzzy matching problem.

### Why We Haven't Done It Yet

The $10 bankroll constraint. After splitting across two platforms ($5 each), position sizes are too small for the fees on the Kalshi side to leave any profit. Cross-platform arb becomes viable at ~$500+ bankroll, where the absolute dollar profit per trade justifies the fee overhead and infrastructure complexity.

---

## Appendix A: Glossary

| Term | Meaning |
|------|---------|
| **Ask** | The lowest price a seller is willing to accept |
| **Bid** | The highest price a buyer is willing to pay |
| **CLOB** | Central Limit Order Book — traditional exchange matching engine |
| **CTF** | Conditional Token Framework — Gnosis protocol for binary tokens |
| **EIP-712** | Ethereum typed structured data signing standard |
| **ERC-1155** | Multi-token standard on Ethereum/Polygon |
| **EV** | Expected Value — the probability-weighted average of all outcomes |
| **FAK** | Fill-And-Kill — execute what you can, cancel the rest |
| **FOK** | Fill-Or-Kill — execute everything or nothing |
| **GTC** | Good-Til-Cancelled — order rests until filled or you cancel it |
| **GTD** | Good-Til-Date — order rests until filled or a timestamp passes |
| **HMAC-SHA256** | Hash-based message authentication code using SHA-256 |
| **negRisk** | Polymarket's framework for multi-outcome markets |
| **Polygon** | Layer-2 Ethereum blockchain (low gas fees, fast blocks) |
| **RSA-PSS** | RSA Probabilistic Signature Scheme (Kalshi authentication) |
| **Slippage** | Difference between expected and actual execution price |
| **Spread** | Gap between best bid and best ask |
| **UMA** | Universal Market Access — Polymarket's oracle for resolution |
| **USDC** | USD Coin — stablecoin pegged 1:1 to USD |

## Appendix B: Key Numbers

| Metric | Polymarket | Kalshi |
|--------|-----------|--------|
| Weekly volume | $2.1B+ | $2.7B+ |
| Active markets | ~1,000 | ~350,000 |
| Standard fees | 0% (most markets) | 0.63-1.75% |
| Resolution time | 2 hours - 5 days | Minutes - hours |
| API rate limit | Unlimited (reasonable use) | 20-400 req/s |
| Settlement | On-chain (Polygon) | Centralized |
| KYC required | No (international) | Yes |
| Minimum deposit | ~$1 USDC | ~$1 USD |
| Blockchain | Polygon (EVM) | None |
| Token standard | ERC-1155 | N/A (contracts) |

## Appendix C: File Reference

| File | Role | Strategy |
|------|------|----------|
| `src/config.py` | Configuration and env vars | All |
| `src/client.py` | Polymarket API wrapper (Gamma + CLOB) | All |
| `src/scanner.py` | Parallel market scanning (500 markets, 20 concurrent) | All Python strategies |
| `src/strategies/endgame.py` | Near-resolution high-probability token detection | Endgame |
| `src/strategies/value.py` | Order book imbalance and wide-spread detection | Value |
| `src/strategies/correlation.py` | Cross-market lag detection via regex grouping | Correlation |
| `src/risk.py` | Position limits, exposure caps, kill switch, compounding | All |
| `src/executor.py` | Order sizing and placement | All Python strategies |
| `src/dashboard.py` | Rich terminal UI | Display |
| `src/main.py` | Orchestrator and main event loop | All |
| `arb-engine/src/config.rs` | Rust engine configuration | Arb |
| `arb-engine/src/types.rs` | Data structures (BTreeMap order books) | Arb |
| `arb-engine/src/markets.rs` | Gamma API market fetcher | Arb |
| `arb-engine/src/ws.rs` | WebSocket client with auto-reconnect | Arb |
| `arb-engine/src/scanner.rs` | YES+NO<$1.00 detection | Arb |
| `arb-engine/src/executor.rs` | Position sizing and risk checks | Arb |
| `arb-engine/src/main.rs` | Event loop and orchestrator | Arb |
| `run.sh` | Launch script for both processes | Infra |
