# Potential Bot Strategies - Verified True Intraday

**Document Created:** December 30, 2025
**Purpose:** Document all verified TRUE INTRADAY trading strategies for bot implementation
**Criteria:** All positions MUST close same day (no overnight holding)

---

## Executive Summary

After extensive research across academic papers, SSRN, QuantConnect, and trading platforms, these are the **ONLY strategies verified to be true intraday** (positions opened after market open and closed before market close, same day).

### Quick Comparison Table

| Rank | Strategy | Win Rate | Profit Factor | Sharpe | Best For |
|------|----------|----------|---------------|--------|----------|
| 1 | ORB 60-min (NQ Futures) | **74.56%** | **2.512** | N/A | Futures trading |
| 2 | Overnight-Intraday Reversal | N/A | N/A | **4.44** | Stock/ETF reversal |
| 3 | ORB Stocks in Play | 17-42% | 1.23 | **2.81** | Active stock picking |
| 4 | Intraday Momentum SPY | N/A | N/A | **1.33** | Single instrument |
| 5 | VWAP Trend (QQQ) | N/A | N/A | **2.1** | ETF trend following |
| 6 | Market Intraday Momentum | N/A | N/A | **1.08** | Academic benchmark |
| 7 | 0DTE Options ORB | **89.4%** | 1.44 | N/A | Options trading |
| 8 | S&P 500 ORB | **65%** | **2.0** | N/A | Index futures |

---

## Strategy 1: Opening Range Breakout 60-Min (NQ Futures)

### Overview
| Metric | Value |
|--------|-------|
| **Source** | Trade That Swing |
| **Instrument** | NQ (Nasdaq E-mini Futures) |
| **Backtest Period** | Oct 2024 - Oct 2025 |
| **Trade Count** | 114 trades |
| **Win Rate** | **74.56%** |
| **Profit Factor** | **2.512** |
| **Max Drawdown** | $2,725 (~12%) |
| **Avg Winner** | $846 |
| **Avg Loser** | $987 |
| **Max Consecutive Losses** | 2 |

### Entry Rules
1. Wait for first 15 minutes to establish opening range (high/low)
2. Buy when 5-min candle CLOSES above opening range high
3. Only take LONG trades during uptrends

### Exit Rules
1. **Stop Loss:** Opposite side of opening range (max $1,000)
2. **Target:** 50% of opening range height
3. **Time Exit:** Close all positions at 3:00 PM CT (before market close)

### Filters
- Opening range width capped at 0.8%
- Maximum 1 trade per day
- Long-only during uptrends

### Same-Day Exit Verification
**VERIFIED:** Explicitly states "Positions are closed at the end of the day (1500 local time)"

### Caveats
- Only 114 trades (small sample size)
- Long-only bias during bull market
- NQ futures require margin account

### Source
- [Trade That Swing - Opening Range Breakout Strategy](https://tradethatswing.com/opening-range-breakout-strategy-up-400-this-year/)

---

## Strategy 2: Overnight-Intraday Reversal (CO-OC)

### Overview
| Metric | Value |
|--------|-------|
| **Source** | SSRN Academic Paper |
| **Authors** | Liu, Liu, Wang, Zhou, Zhu |
| **SSRN ID** | 2730304 |
| **Sharpe Ratio** | **4.44** (up to 9.0+ on financial ETFs) |
| **Backtest Period** | Multi-year academic study |

### Entry Rules
1. At market open (9:30 AM ET), calculate overnight return for all stocks/ETFs
2. Overnight return = (Open Price - Previous Close) / Previous Close
3. **GO LONG:** Bottom decile (biggest overnight losers)
4. **GO SHORT:** Top decile (biggest overnight winners)

### Exit Rules
1. **Close ALL positions at market close (4:00 PM ET)**
2. No stops, no targets - pure time-based exit

### Why the Name is Confusing
- "Overnight" refers to the **SIGNAL** (overnight returns used to select stocks)
- "Intraday" refers to the **HOLDING PERIOD** (hold only during the day)
- You are **NEVER** holding overnight

### Same-Day Exit Verification
**VERIFIED:** Academic paper confirms positions opened at open, closed at close, zero overnight exposure.

### Implementation Requirements
- Requires market-on-open (MOO) orders or very fast execution at open
- Slippage at open can destroy returns
- Need universe of liquid stocks/ETFs for ranking

### Caveats
- Requires precise execution at market open
- High turnover (100% daily)
- Academic returns may not include realistic transaction costs
- Paper notes strategy may not be fully implementable in real-time

### Source
- [SSRN - Overnight-Intraday Reversal Everywhere](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2730304)

---

## Strategy 3: ORB on Stocks in Play (Zarattini/Aziz)

### Overview
| Metric | Value |
|--------|-------|
| **Source** | SSRN Academic Paper |
| **Authors** | Zarattini, Barbon, Aziz (Swiss Finance Institute) |
| **SSRN ID** | 4729284 |
| **Backtest Period** | 2016-2023 (8 years) |
| **Universe** | 7,000+ US stocks |
| **Win Rate** | 17-42% (low but profitable) |
| **Profit Factor** | 1.23 |
| **Sharpe Ratio** | **2.81** |
| **Total Return** | 1,600% (top 20 stocks) |
| **Beta** | Near zero (market neutral) |

### Entry Rules
1. **Pre-market screening:** Identify "Stocks in Play" (high relative volume + news catalyst)
2. Select top 20 stocks with highest relative volume
3. Wait for first 5-minute candle (9:30-9:35 AM)
4. **LONG:** If first candle bullish (close > open), enter at 9:35 AM
5. **SHORT:** If first candle bearish (close < open), enter at 9:35 AM
6. **NO TRADE:** If first candle is doji (open ~ close)

### Exit Rules
1. **Stop Loss:** 5-10% of 14-day ATR from entry price
2. **End of Day:** Positions not stopped out are closed at market close (4:00 PM ET)

### Stock Selection Criteria ("Stocks in Play")
- Price > $5
- Average volume > 1 million shares
- ATR > $0.50
- Has news catalyst or unusual pre-market volume

### Same-Day Exit Verification
**VERIFIED:** Paper explicitly states: "positions not stopped out are closed at the end of the trading session"

### Key Finding
The strategy ONLY works on "Stocks in Play" (20 stocks/day). Applied to all stocks = failure (only 29% return over 8 years).

### Caveats
- Requires daily pre-market screening (manual or automated)
- Low win rate (17-42%) - profitability from risk/reward ratio
- High turnover

### Source
- [SSRN - A Profitable Day Trading Strategy For The U.S. Equity Market](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284)

---

## Strategy 4: Intraday Momentum SPY (Zarattini/Aziz/Barbon)

### Overview
| Metric | Value |
|--------|-------|
| **Source** | SSRN Academic Paper |
| **Authors** | Zarattini, Aziz, Barbon (Swiss Finance Institute) |
| **SSRN ID** | 4824172 |
| **Instrument** | SPY (S&P 500 ETF) |
| **Backtest Period** | 2007 - Early 2024 (17 years) |
| **Total Return** | 1,985% (net of costs) |
| **Annualized Return** | 19.6% |
| **Sharpe Ratio** | **1.33** |
| **Transaction Costs** | $0.0035/share commission + $0.001/share slippage |

### Entry Rules
1. Compute "noise boundaries" each minute based on 14-day average daily return
2. Entry only at clock hours (:00) or half-hours (:30)
3. **LONG:** When SPY breaks above upper noise boundary
4. **SHORT:** When SPY breaks below lower noise boundary
5. Trading window: 10:00 AM - 4:00 PM ET

### Exit Rules
1. **Dynamic trailing stop** (VWAP-based)
2. **MANDATORY:** All positions closed at market close (4:00 PM ET)

### Same-Day Exit Verification
**VERIFIED:** Paper states: "Terminate any open positions at each market close to avoid exposure to overnight moves"

### Advantages
- Single instrument (simple)
- 17 years of backtest data
- Academic rigor
- Transaction costs included

### Caveats
- Win rate not explicitly stated (estimated 36-43%)
- Requires minute-level data processing
- Complex boundary calculations

### Source
- [SSRN - Beat the Market: Intraday Momentum Strategy for SPY](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172)

---

## Strategy 5: VWAP Trend Trading (QQQ)

### Overview
| Metric | QQQ | TQQQ (3x Leveraged) |
|--------|-----|---------------------|
| **Source** | SSRN Academic Paper |
| **Authors** | Zarattini, Aziz |
| **SSRN ID** | 4631351 |
| **Backtest Period** | Jan 2018 - Sep 2023 |
| **Starting Capital** | $25,000 | $25,000 |
| **Ending Capital** | $192,656 | $2,085,417 |
| **Total Return** | 671% | 8,242% |
| **Annualized Return** | ~45% | 116% |
| **Max Drawdown** | 9.4% | ~37% |
| **Sharpe Ratio** | **2.1** | Lower |

### Entry Rules
1. **LONG:** When price crosses above VWAP
2. **SHORT:** When price crosses below VWAP
3. Position flips with each VWAP crossover

### Exit Rules
1. Position reverses on opposite signal
2. All positions closed at market close (VWAP resets daily)

### Same-Day Exit Verification
**VERIFIED:** VWAP resets daily; strategy designed for day trading with no overnight positions.

### Caveats - IMPORTANT
**This strategy has been DISPUTED:**
- Independent replication by Seth Lingafeldt found discrepancies
- Different trade counts (paper: 21,967 vs replication: 24,879)
- Results degraded significantly when realistic bid/ask spreads applied
- "Simulating 'no spread' produced almost the same performance as the paper"

### Source
- [SSRN - VWAP The Holy Grail for Day Trading Systems](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4631351)
- [LinkedIn - Independent Critique](https://www.linkedin.com/pulse/bear-bull-traders-paper-holy-grail-so-fast-seth-lingafeldt-2o3cf)

---

## Strategy 6: Market Intraday Momentum (Gao/Han/Li/Zhou)

### Overview
| Metric | Value |
|--------|-------|
| **Source** | Journal of Financial Economics (Peer-Reviewed) |
| **Authors** | Gao, Han, Li, Zhou |
| **Publication** | 2018 |
| **Instrument** | SPY |
| **Backtest Period** | 1993-2013 |
| **Annual Return** | 6.67% |
| **Sharpe Ratio** | **1.08** |
| **Standard Deviation** | 6.19% |

### Entry Rules
1. Calculate first half-hour return (9:30-10:00 AM)
2. **LONG:** If first half-hour return is positive
3. **SHORT:** If first half-hour return is negative
4. **FLAT:** If mixed signals

### Exit Rules
1. Enter position in last half-hour of trading (3:30-4:00 PM)
2. Close at market close (4:00 PM)

### Same-Day Exit Verification
**VERIFIED:** Published in top-tier finance journal with explicit same-day methodology.

### Key Finding
First half-hour return predicts last half-hour return. The effect is linked to hedging demand from options market makers.

### Caveats
- QuantConnect verification showed **lower returns** in recent periods
- Strategy may have degraded since publication
- Only holds position for 30 minutes at end of day

### Source
- [Journal of Financial Economics - Market Intraday Momentum](https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351)

---

## Strategy 7: 0DTE Options ORB (60-Minute)

### Overview
| Metric | 15-min | 30-min | 60-min |
|--------|--------|--------|--------|
| **Source** | Option Alpha |
| **Win Rate** | 78.1% | 82.6% | **89.4%** |
| **Profit Factor** | 1.17 | 1.19 | **1.44** |
| **Max Drawdown** | $7,602 | $8,306 | $3,231 |
| **Avg P/L** | $35 | $31 | $51 |

### Entry Rules
1. Wait for opening range to complete (15, 30, or 60 minutes)
2. Sell credit spreads in the direction of the breakout
3. Use 0DTE (zero days to expiration) options

### Exit Rules
1. Options expire same day by definition
2. Manage position if threatened

### Same-Day Exit Verification
**VERIFIED:** 0DTE options expire at end of day - cannot hold overnight by definition.

### Important Notes
- This is OPTIONS trading, not stock/futures
- Different risk profile (limited profit, defined risk)
- Requires options approval and understanding
- 60-minute variant shows best risk-adjusted returns

### Source
- [Option Alpha - Opening Range Breakout 0DTE Options](https://optionalpha.com/blog/opening-range-breakout-0dte-options-trading-strategy-explained)

---

## Strategy 8: S&P 500 ORB (QuantifiedStrategies)

### Overview
| Metric | Value |
|--------|-------|
| **Source** | QuantifiedStrategies |
| **Instrument** | S&P 500 |
| **Trade Count** | 198 trades |
| **Win Rate** | **65%** |
| **Profit Factor** | **2.0** |
| **Avg Gain/Trade** | 0.27% |

### Entry Rules
1. Record opening range (first X minutes)
2. Buy when price breaks above range high
3. Short when price breaks below range low

### Exit Rules
1. Exit at closing price of daily session

### Same-Day Exit Verification
**VERIFIED:** "selling at the closing price of the daily session"

### Major Warning
**QuantifiedStrategies explicitly states:** "Opening range breakout trading strategies don't work very well anymore... The effectiveness has diminished over time as more traders adopt it... much less relevant now than they used to be."

### Source
- [QuantifiedStrategies - Opening Range Breakout](https://www.quantifiedstrategies.com/opening-range-breakout-strategy/)

---

## Strategies REJECTED (Not True Intraday)

These strategies are often called "intraday" but actually hold overnight:

| Strategy | Why NOT Intraday | Actual Hold Time |
|----------|------------------|------------------|
| **RSI(2) Connors** | Holds until price > 5-day MA | 1-6 days |
| **IBS Mean Reversion** | Uses daily bars | 5.8 days average |
| **WMA(20) + Heikin Ashi** | Backtested on DAILY charts | Multi-day |
| **HMA + Heikin Ashi** | Backtested on DAILY charts | Multi-day |
| **Double Seven** | Entry on 7-day low, exit on 7-day high | 7+ days |
| **Williams %R** | Multi-day mean reversion | 2-5 days |
| **3-Day Mean Reversion** | By definition | 3+ days |

---

## Implementation Recommendations

### For Stocks (Current Setup)
1. **Best Option:** Overnight-Intraday Reversal (Sharpe 4.44)
2. **Alternative:** ORB on Stocks in Play (requires pre-market screening)

### For Single Instrument (Simpler)
1. **Best Option:** Intraday Momentum SPY (17 years tested, Sharpe 1.33)
2. **Alternative:** VWAP Trend QQQ (disputed but Sharpe 2.1)

### For Futures
1. **Best Option:** ORB 60-min on NQ (74.56% win rate, 2.51 profit factor)

### For Options
1. **Best Option:** 0DTE ORB 60-min (89.4% win rate)

---

## Key Takeaways

1. **True intraday strategies have lower win rates** than swing strategies (typically 17-65% vs 70-85%)

2. **Profitability comes from risk/reward ratio**, not win rate

3. **Transaction costs are critical** - many strategies fail after realistic costs

4. **Strategy decay is real** - ORB strategies have degraded significantly

5. **Academic papers report Sharpe ratio**, not win rate - makes comparison difficult

6. **Most "intraday" strategies online actually hold overnight** - verify carefully

---

## Data Requirements

To implement these strategies, you need:

| Strategy | Data Required |
|----------|---------------|
| ORB 60-min | 5-min or 15-min bars, volume |
| Overnight-Intraday Reversal | Previous close, current open for all stocks |
| ORB Stocks in Play | Pre-market volume, news screening, 5-min bars |
| Intraday Momentum SPY | 1-min bars for SPY, 14-day history |
| VWAP Trend | 1-min or 5-min bars with volume (for VWAP calc) |
| Market Intraday Momentum | 30-min bars for SPY |

---

## Next Steps

1. Choose strategy based on:
   - Available instruments (stocks, ETFs, futures, options)
   - Data availability
   - Account type and margin
   - Risk tolerance

2. Implement with paper trading first

3. Monitor for at least 1-3 months before live trading

4. Track actual vs. expected performance

---

*Document will be updated as new verified strategies are discovered.*
