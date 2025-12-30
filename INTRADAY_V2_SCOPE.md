# Intraday Bot V2 Scope Document

## Strategy Replacement Plan

**Document Created:** December 30, 2025
**Purpose:** Replace 3 current intraday strategies with 3 verified true intraday strategies
**Status:** Planning

---

## Executive Summary

This document outlines the replacement of the current intraday trading strategies with three new academically-verified true intraday strategies. All positions will continue to close same-day with no overnight exposure.

### Strategy Mapping

| Current Strategy | Replacement Strategy | Account (Unchanged) |
|------------------|---------------------|---------------------|
| ORB (60-min VWAP+EMA) | ORB 60-min (Simplified) | PKUWXI5LD5GMPQTLHTGZLJMHMA |
| WMA(20) + Heikin Ashi | Overnight-Intraday Reversal | PKEWDBHRFW7RMW2YXXRCAGE6ZJ |
| HMA + Heikin Ashi | ORB Stocks in Play | PKTGRHXB4LUKDH7T4PK3SOZIPX |

### Performance Comparison

| Metric | Old Strategies | New Strategies |
|--------|---------------|----------------|
| ORB Win Rate | 89.4% (claimed) | 74.56% (verified) |
| Strategy 2 Win Rate | 83% (claimed) | N/A (Sharpe 4.44) |
| Strategy 3 Win Rate | 77% (claimed) | 17-42% (Sharpe 2.81) |
| Data Source | Daily bars converted | 1-min bars native |
| Academic Verification | None | SSRN papers |

---

## 1. New Strategy Specifications

### 1.1 Strategy 1: ORB 60-Min (Simplified)

**Account:** PKUWXI5LD5GMPQTLHTGZLJMHMA (ORB account)
**Source:** Trade That Swing (verified 74.56% win rate, 2.51 profit factor)

#### Entry Rules
| Rule | Description |
|------|-------------|
| Time Window | After 10:30 AM ET (60-min range established) |
| Signal | 5-min candle CLOSES above opening range high |
| Direction | LONG ONLY (no short entries) |
| Filter | Opening range width <= 0.8% of open price |
| Max Trades | 1 trade per day per symbol |

#### Exit Rules
| Rule | Description |
|------|-------------|
| Stop Loss | Opposite side of opening range (range low) |
| Target | 50% of opening range height (NOT 100%) |
| Time Exit | 3:00 PM ET (close all positions) |
| EOD | Force close any remaining positions |

#### Position Sizing
| Parameter | Value |
|-----------|-------|
| Max Positions | 5 |
| Position Size | 10% of equity |
| Max Risk | Stop at range low (varies) |

#### Key Differences from Current ORB
1. **Simplified entry**: Only price breakout required (no VWAP, no EMA slope)
2. **Different target**: 50% of range (not 100% measured move)
3. **Earlier exit**: 3:00 PM instead of 2:00 PM
4. **Range width filter**: Skip if range > 0.8% of open

---

### 1.2 Strategy 2: Overnight-Intraday Reversal

**Account:** PKEWDBHRFW7RMW2YXXRCAGE6ZJ (WMA account)
**Source:** SSRN #2730304 (Sharpe 4.44)

#### Entry Rules
| Rule | Description |
|------|-------------|
| Time | Market open (9:30 AM ET) |
| Signal | Buy stocks with WORST overnight returns (bottom decile) |
| Calculation | Overnight return = (Open - Previous Close) / Previous Close |
| Universe | All stocks in database with valid prior close and current open |
| Selection | Bottom 10% of overnight returns (biggest losers) |

#### Exit Rules
| Rule | Description |
|------|-------------|
| Time Exit | Market close 4:00 PM ET |
| Stop Loss | NONE (pure time-based exit) |
| Target | NONE (pure time-based exit) |

#### Position Sizing
| Parameter | Value |
|-----------|-------|
| Max Positions | 10 (spread across bottom decile) |
| Position Size | 10% of equity per position |
| Total Exposure | Up to 100% of equity |

#### Key Implementation Notes
1. **Requires prior day close**: Need to fetch from Alpaca API or cache previous closes
2. **MOO execution**: Enter at market open, need fast execution
3. **No intraday management**: Set and forget until close
4. **High turnover**: 100% daily (all positions replaced each day)

#### Data Requirements
- Previous day close for all symbols
- Current day open (from 9:30 bar)
- Decile calculation across entire universe

---

### 1.3 Strategy 3: ORB Stocks in Play

**Account:** PKTGRHXB4LUKDH7T4PK3SOZIPX (HMA account)
**Source:** SSRN #4729284 (Sharpe 2.81, 1600% return over 8 years)

#### Pre-Market Screening ("Stocks in Play")
| Criteria | Value |
|----------|-------|
| Price | > $5.00 |
| Average Volume | > 1 million shares (20-day avg) |
| ATR | > $0.50 (14-day ATR) |
| Relative Volume | Top 20 by relative volume |
| News Catalyst | Optional (enhances selection) |

#### Entry Rules
| Rule | Description |
|------|-------------|
| Time Window | 9:35 AM ET (after first 5-min candle) |
| Signal - LONG | First 5-min candle bullish (close > open) |
| Signal - SHORT | First 5-min candle bearish (close < open) |
| No Trade | First candle is doji (close ~ open) |
| Universe | Top 20 "Stocks in Play" only |

#### Exit Rules
| Rule | Description |
|------|-------------|
| Stop Loss | 10% of 14-day ATR from entry price |
| EOD Exit | Market close 4:00 PM ET |
| Target | NONE (ride winners, cut losers) |

#### Position Sizing
| Parameter | Value |
|-----------|-------|
| Max Positions | 5 (from top 20 candidates) |
| Position Size | 10% of equity |
| Risk Per Trade | Stop at 10% of ATR |

#### Key Implementation Notes
1. **Pre-market screening**: Run before 9:30 AM (or at 9:30 using prior day data)
2. **ATR calculation**: Need 14-day price history per symbol
3. **Volume calculation**: Need 20-day volume history
4. **Relative volume**: Compare pre-market volume to average
5. **Low win rate is OK**: Profitability from risk/reward ratio (Sharpe 2.81)

#### Data Requirements
- 14-day ATR (requires daily OHLC history)
- 20-day average volume
- Current day's first 5-minute candle
- Pre-market volume (if available) or prior day relative volume

---

## 2. Architecture Changes

### 2.1 Files to Modify

| File | Changes |
|------|---------|
| `config.py` | Update strategy names, add new parameters |
| `strategies/__init__.py` | Export new strategy classes |
| `intraday_bot.py` | Update initialization and strategy references |

### 2.2 Files to Create

| File | Purpose |
|------|---------|
| `strategies/orb_v2_strategy.py` | Simplified ORB (60-min range, 50% target) |
| `strategies/overnight_reversal_strategy.py` | Overnight-Intraday Reversal |
| `strategies/stocks_in_play_strategy.py` | ORB on Stocks in Play |
| `data/historical_data.py` | Helper for prior close, ATR, avg volume |

### 2.3 Files to Delete (After Migration)

| File | Reason |
|------|--------|
| `strategies/orb_strategy.py` | Replaced by orb_v2_strategy.py |
| `strategies/wma_ha_strategy.py` | Replaced by overnight_reversal_strategy.py |
| `strategies/hma_ha_strategy.py` | Replaced by stocks_in_play_strategy.py |

### 2.4 Files Unchanged

| File | Reason |
|------|--------|
| `strategies/base_strategy.py` | Interface remains compatible |
| `execution/alpaca_client.py` | Order execution unchanged |
| `data/intraday_indicators.py` | Add new methods, keep existing |

---

## 3. Implementation Phases

### Phase 1: Data Layer Enhancements

**Goal:** Add required data access methods for new strategies

#### Task 1.1: Add Prior Day Close Retrieval
- [ ] Add `get_prior_close(symbol)` method to `intraday_indicators.py`
- [ ] Query last bar before today's market open
- [ ] Cache prior closes for performance
- [ ] Handle missing data gracefully

**Test:** `python -c "from data.intraday_indicators import IntradayIndicators; i = IntradayIndicators(); print(i.get_prior_close('AAPL'))"`

#### Task 1.2: Add Overnight Return Calculation
- [ ] Add `calculate_overnight_return(symbol)` method
- [ ] Formula: (today_open - prior_close) / prior_close
- [ ] Return None if data missing

**Test:** `python -c "from data.intraday_indicators import IntradayIndicators; i = IntradayIndicators(); print(i.calculate_overnight_return('AAPL'))"`

#### Task 1.3: Add Decile Ranking
- [ ] Add `get_overnight_return_deciles(min_price=5.0)` method
- [ ] Calculate overnight return for all symbols
- [ ] Return bottom decile (worst performers) as list

**Test:** `python -c "from data.intraday_indicators import IntradayIndicators; i = IntradayIndicators(); print(len(i.get_overnight_return_deciles()))"`

#### Task 1.4: Create Historical Data Helper
- [ ] Create `data/historical_data.py`
- [ ] Add `get_atr(symbol, period=14)` method using Alpaca API
- [ ] Add `get_average_volume(symbol, period=20)` method
- [ ] Add caching to minimize API calls

**Test:** `python -c "from data.historical_data import HistoricalData; h = HistoricalData(); print(h.get_atr('AAPL'))"`

#### Task 1.5: Add Stocks in Play Screening
- [ ] Add `get_stocks_in_play(top_n=20, min_price=5.0, min_avg_volume=1_000_000, min_atr=0.50)` method
- [ ] Screen all symbols for criteria
- [ ] Return sorted by relative volume

**Test:** `python -c "from data.intraday_indicators import IntradayIndicators; i = IntradayIndicators(); print(i.get_stocks_in_play())"`

#### Task 1.6: Add First 5-Min Candle Analysis
- [ ] Add `get_first_5min_candle(symbol)` method
- [ ] Aggregate bars from 9:30-9:35 AM
- [ ] Return dict with open, high, low, close, is_bullish, is_bearish, is_doji

**Test:** `python -c "from data.intraday_indicators import IntradayIndicators; i = IntradayIndicators(); print(i.get_first_5min_candle('AAPL'))"`

### Phase 1 Acceptance Criteria
- [ ] All 6 new data methods implemented and return valid data
- [ ] Each method has error handling for missing data
- [ ] Methods work within intraday_indicators.py context
- [ ] All tests pass with real database

---

### Phase 2: Strategy 1 - ORB V2 (Simplified)

**Goal:** Replace current ORB with simplified version

#### Task 2.1: Create ORB V2 Strategy Class
- [ ] Create `strategies/orb_v2_strategy.py`
- [ ] Extend `BaseStrategy` class
- [ ] Implement `__init__` with new parameters (range_width_max=0.008)

**Test:** `python -c "from strategies.orb_v2_strategy import ORBV2Strategy; print(ORBV2Strategy.__doc__)"`

#### Task 2.2: Implement Entry Logic
- [ ] `check_entry(symbol)`: Return EntrySignal if breakout above range high
- [ ] Add range width filter (skip if range > 0.8% of open)
- [ ] Remove VWAP, EMA slope requirements
- [ ] Track daily trade count per symbol (max 1)

**Test:** Create unit test that mocks data and verifies entry signal generation

#### Task 2.3: Implement Exit Logic
- [ ] `check_exit(symbol, position)`: Check target (50% of range), stop (range low), time (3 PM)
- [ ] Target = entry_price + (range_high - range_low) * 0.5
- [ ] Stop = range_low

**Test:** Create unit test that verifies exit signals at target, stop, and time

#### Task 2.4: Implement Candidate Screening
- [ ] `get_candidates()`: Screen all symbols for entry criteria
- [ ] Use existing `get_opening_range()` method
- [ ] Filter by range width
- [ ] Sort by range width (smaller = better)

**Test:** `python -c "from strategies.orb_v2_strategy import ORBV2Strategy; s = ORBV2Strategy(...); print(s.get_candidates())"`

#### Task 2.5: Add Daily Trade Tracking
- [ ] Add `_daily_trades` dict to track symbols traded today
- [ ] Reset at midnight or new trading day
- [ ] Check before allowing entry

**Test:** Verify same symbol cannot be traded twice in one day

### Phase 2 Acceptance Criteria
- [ ] ORBV2Strategy class compiles without errors
- [ ] Entry only triggers after 10:30 AM
- [ ] Entry only triggers on range breakout (no VWAP/EMA)
- [ ] Range width > 0.8% symbols are filtered out
- [ ] Target is 50% of range (not 100%)
- [ ] Stop is at range low
- [ ] EOD exit at 3:00 PM ET
- [ ] Max 1 trade per symbol per day

---

### Phase 3: Strategy 2 - Overnight-Intraday Reversal

**Goal:** Replace WMA+HA with overnight reversal strategy

#### Task 3.1: Create Overnight Reversal Strategy Class
- [ ] Create `strategies/overnight_reversal_strategy.py`
- [ ] Extend `BaseStrategy` class
- [ ] Set EOD exit time to 4:00 PM (MARKET_CLOSE)

**Test:** `python -c "from strategies.overnight_reversal_strategy import OvernightReversalStrategy; print(OvernightReversalStrategy.__doc__)"`

#### Task 3.2: Implement Entry Logic
- [ ] `check_entry(symbol)`: Only valid at market open (9:30-9:35 AM window)
- [ ] Check if symbol is in bottom decile of overnight returns
- [ ] Return EntrySignal with no target/stop (time-based exit only)

**Test:** Create unit test that verifies entry only at market open

#### Task 3.3: Implement Exit Logic
- [ ] `check_exit(symbol, position)`: Only EOD exit at 4:00 PM
- [ ] NO stop loss (per strategy spec)
- [ ] NO target (per strategy spec)

**Test:** Verify no exit signal before 4:00 PM except EOD

#### Task 3.4: Implement Candidate Screening
- [ ] `get_candidates()`: Call `get_overnight_return_deciles()` from data layer
- [ ] Only return candidates during 9:30-9:35 AM window
- [ ] Return empty list outside market open window

**Test:** `python -c "from strategies.overnight_reversal_strategy import OvernightReversalStrategy; s = OvernightReversalStrategy(...); print(s.get_candidates())"`

#### Task 3.5: Add Position Entry Timing
- [ ] Override `is_trading_time()` to only allow 9:30-9:35 AM entries
- [ ] No entries after 9:35 AM (strategy only trades at open)

**Test:** Verify is_trading_time() returns False after 9:35 AM

### Phase 3 Acceptance Criteria
- [ ] OvernightReversalStrategy class compiles without errors
- [ ] Entry only during 9:30-9:35 AM window
- [ ] Selects bottom decile of overnight returns
- [ ] NO stop loss implemented (per strategy)
- [ ] NO target implemented (per strategy)
- [ ] EOD exit at exactly 4:00 PM
- [ ] Max 10 positions (configurable)

---

### Phase 4: Strategy 3 - ORB Stocks in Play

**Goal:** Replace HMA+HA with Stocks in Play ORB strategy

#### Task 4.1: Create Stocks in Play Strategy Class
- [ ] Create `strategies/stocks_in_play_strategy.py`
- [ ] Extend `BaseStrategy` class
- [ ] Add ATR-based stop loss calculation

**Test:** `python -c "from strategies.stocks_in_play_strategy import StocksInPlayStrategy; print(StocksInPlayStrategy.__doc__)"`

#### Task 4.2: Implement Pre-Market Screening
- [ ] Create `_refresh_stocks_in_play()` method
- [ ] Call `get_stocks_in_play()` from data layer
- [ ] Cache results for the trading day
- [ ] Refresh if called on new day

**Test:** Verify screening returns ~20 high-volume stocks

#### Task 4.3: Implement Entry Logic
- [ ] `check_entry(symbol)`: Only valid at 9:35 AM (after first 5-min candle)
- [ ] Check if symbol is in Stocks in Play list
- [ ] Check first 5-min candle direction (bullish = long, bearish = short)
- [ ] Skip doji candles (open ~ close within 0.1%)

**Test:** Create unit test for bullish/bearish/doji detection

#### Task 4.4: Implement Exit Logic
- [ ] `check_exit(symbol, position)`: Check ATR stop, EOD
- [ ] Stop = entry_price - (ATR * 0.10) for longs
- [ ] Stop = entry_price + (ATR * 0.10) for shorts
- [ ] EOD exit at 4:00 PM

**Test:** Verify stop calculation with known ATR values

#### Task 4.5: Implement Candidate Screening
- [ ] `get_candidates()`: Return Stocks in Play with valid first candle signal
- [ ] Only return candidates during 9:35-9:40 AM window
- [ ] Filter out doji candles

**Test:** Verify candidate filtering logic

#### Task 4.6: Add Short Selling Support
- [ ] Modify `execute_entry()` to handle short positions
- [ ] Add `side` field to EntrySignal (default 'buy')
- [ ] Update AlpacaClient if needed for short orders

**Test:** Verify short order submission works

### Phase 4 Acceptance Criteria
- [ ] StocksInPlayStrategy class compiles without errors
- [ ] Pre-market screening identifies top 20 by relative volume
- [ ] Entry only during 9:35-9:40 AM window
- [ ] Bullish first candle = long entry
- [ ] Bearish first candle = short entry
- [ ] Doji first candle = no trade
- [ ] Stop at 10% of ATR from entry
- [ ] EOD exit at 4:00 PM
- [ ] Max 5 positions

---

### Phase 5: Integration and Config Updates

**Goal:** Wire up new strategies to intraday_bot.py

#### Task 5.1: Update config.py Strategy Enum
- [ ] Rename StrategyType values:
  - `ORB` -> `ORB_V2`
  - `WMA20_HA` -> `OVERNIGHT_REVERSAL`
  - `HMA_HA` -> `STOCKS_IN_PLAY`
- [ ] Update STRATEGY_CONFIG with new parameters

**Test:** `python -c "from config import StrategyType; print(list(StrategyType))"`

#### Task 5.2: Update config.py Parameters
- [ ] ORB_V2: eod_exit_time = 15:00, target_pct = 0.50
- [ ] OVERNIGHT_REVERSAL: eod_exit_time = 16:00, no_stops = True
- [ ] STOCKS_IN_PLAY: eod_exit_time = 16:00, atr_stop_pct = 0.10

**Test:** `python -c "from config import STRATEGY_CONFIG; print(STRATEGY_CONFIG)"`

#### Task 5.3: Update strategies/__init__.py
- [ ] Remove old strategy imports
- [ ] Add new strategy imports
- [ ] Update __all__ list

**Test:** `python -c "from strategies import *; print([s for s in dir() if 'Strategy' in s])"`

#### Task 5.4: Update intraday_bot.py Initialization
- [ ] Update `_init_orb()` to use ORBV2Strategy
- [ ] Rename `_init_wma_ha()` to `_init_overnight_reversal()`
- [ ] Rename `_init_hma_ha()` to `_init_stocks_in_play()`
- [ ] Update strategy instantiation parameters

**Test:** `python intraday_bot.py --help` (should not error)

#### Task 5.5: Update intraday_bot.py Logging
- [ ] Update log file names for new strategies
- [ ] Update console output strategy names
- [ ] Update journal file names

**Test:** Check logs directory has correct file names

#### Task 5.6: Handle Short Positions
- [ ] Update `_execute_entry()` to handle short orders
- [ ] Update `_execute_exit()` for short P&L calculation
- [ ] Update position tracking for side

**Test:** Manual test with paper trading short

### Phase 5 Acceptance Criteria
- [ ] `python intraday_bot.py` starts without errors
- [ ] All 3 strategies initialize successfully
- [ ] Startup checks pass for all 3 accounts
- [ ] Log files created with new names
- [ ] Console output shows new strategy names

---

### Phase 6: Testing and Validation

**Goal:** Ensure all strategies work correctly in paper trading

#### Task 6.1: Unit Tests for Data Layer
- [ ] Test `get_prior_close()` returns valid prices
- [ ] Test `calculate_overnight_return()` math is correct
- [ ] Test `get_overnight_return_deciles()` returns bottom 10%
- [ ] Test `get_atr()` calculation matches known values
- [ ] Test `get_stocks_in_play()` filtering logic

#### Task 6.2: Unit Tests for ORB V2
- [ ] Test entry at range breakout
- [ ] Test range width filter
- [ ] Test target calculation (50% of range)
- [ ] Test stop at range low
- [ ] Test EOD exit at 3:00 PM
- [ ] Test max 1 trade per day per symbol

#### Task 6.3: Unit Tests for Overnight Reversal
- [ ] Test entry only at market open
- [ ] Test bottom decile selection
- [ ] Test no stop loss behavior
- [ ] Test EOD exit at 4:00 PM

#### Task 6.4: Unit Tests for Stocks in Play
- [ ] Test pre-market screening
- [ ] Test first 5-min candle detection
- [ ] Test bullish/bearish/doji classification
- [ ] Test ATR stop calculation
- [ ] Test short position handling

#### Task 6.5: Integration Test - Paper Trading
- [ ] Run bot for full trading day (paper mode)
- [ ] Verify ORB V2 entries after 10:30 AM
- [ ] Verify Overnight Reversal entries at open
- [ ] Verify Stocks in Play entries at 9:35 AM
- [ ] Verify all positions close by EOD
- [ ] Verify trade journals populated correctly

#### Task 6.6: Performance Monitoring Setup
- [ ] Add metrics logging for each strategy
- [ ] Track win rate, profit factor, avg hold time
- [ ] Compare to documented performance

### Phase 6 Acceptance Criteria
- [ ] All unit tests pass
- [ ] Integration test completes full trading day
- [ ] No positions held overnight
- [ ] Trade journals have complete data
- [ ] No errors in log files

---

### Phase 7: Cleanup and Documentation

**Goal:** Remove old code and document new system

#### Task 7.1: Remove Old Strategy Files
- [ ] Delete `strategies/orb_strategy.py`
- [ ] Delete `strategies/wma_ha_strategy.py`
- [ ] Delete `strategies/hma_ha_strategy.py`

#### Task 7.2: Remove Old Data Methods
- [ ] Remove `get_wma_ha_candidates()` from intraday_indicators.py
- [ ] Remove `get_hma_ha_candidates()` from intraday_indicators.py
- [ ] Keep `get_orb_candidates()` if still useful, else remove

#### Task 7.3: Update CLAUDE.md
- [ ] Update Intraday Bot section with new strategies
- [ ] Document new strategy rules
- [ ] Update file references

#### Task 7.4: Archive Old Documentation
- [ ] Move old strategy docs to `docs/archive/`
- [ ] Create new strategy reference docs

### Phase 7 Acceptance Criteria
- [ ] No references to old strategies in codebase
- [ ] CLAUDE.md updated with new strategies
- [ ] Old files deleted or archived
- [ ] Git history preserved

---

## 4. Risk Management Rules

### 4.1 ORB V2 Risk Rules

| Rule | Value | Rationale |
|------|-------|-----------|
| Max Positions | 5 | Diversification |
| Position Size | 10% equity | Limit concentration |
| Stop Loss | Range low | Defined by strategy |
| Target | 50% of range | Conservative target |
| Max Loss Per Trade | ~0.8% of equity | Range-based stop |
| Daily Trade Limit | 1 per symbol | Avoid overtrading |

### 4.2 Overnight Reversal Risk Rules

| Rule | Value | Rationale |
|------|-------|-----------|
| Max Positions | 10 | Diversification across losers |
| Position Size | 10% equity | Spread across decile |
| Stop Loss | NONE | Strategy has no stops |
| Target | NONE | Time-based exit only |
| Max Loss Per Trade | Unlimited | Controlled by position size |
| Daily Trade Limit | 10 total | Enter all at open |

**WARNING:** This strategy has NO STOP LOSSES. Risk is controlled by:
1. Position size (10% max per position)
2. Same-day exit (no overnight exposure)
3. Diversification (10 positions)

### 4.3 Stocks in Play Risk Rules

| Rule | Value | Rationale |
|------|-------|-----------|
| Max Positions | 5 | Focus on best candidates |
| Position Size | 10% equity | Limit concentration |
| Stop Loss | 10% of ATR | Tight stop for day trading |
| Target | NONE (EOD exit) | Let winners run |
| Max Loss Per Trade | ~0.1% of ATR | Very tight stops |
| Daily Trade Limit | 5 total | Limited to top stocks |

---

## 5. Data Requirements Verification

### 5.1 Current Data Available (intraday.db)

| Data | Available | Notes |
|------|-----------|-------|
| 1-min OHLCV bars | Yes | ~10,000 symbols, 3 days |
| Relative Volume | Yes (calculated) | From bar data |
| Opening Range | Yes (calculated) | 9:30-10:30 bars |
| VWAP | Yes (calculated) | From bar data |
| Prior Close | Partial | Last bar of prior day |

### 5.2 Data Needed from Alpaca API

| Data | Method | Frequency |
|------|--------|-----------|
| 14-day ATR | `get_bars()` daily bars | Once per day |
| 20-day Avg Volume | `get_bars()` daily bars | Once per day |
| Account Equity | `get_account()` | Each cycle |

### 5.3 Data Not Required (Removed)

| Data | Reason |
|------|--------|
| EMA(20) slope | Not used in ORB V2 |
| WMA(20) | Replaced strategy |
| HMA | Replaced strategy |
| Heikin Ashi | Replaced strategy |

---

## 6. Implementation Schedule

### Estimated Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Data Layer | 2-3 hours | None |
| Phase 2: ORB V2 | 2-3 hours | Phase 1 |
| Phase 3: Overnight Reversal | 2-3 hours | Phase 1 |
| Phase 4: Stocks in Play | 3-4 hours | Phase 1 |
| Phase 5: Integration | 2-3 hours | Phases 2-4 |
| Phase 6: Testing | 4-8 hours | Phase 5 |
| Phase 7: Cleanup | 1-2 hours | Phase 6 |

**Total Estimated Time:** 16-26 hours

### Recommended Order

1. Complete Phase 1 fully before any strategy work
2. Implement strategies in order (1, 2, 3) for incremental testing
3. Integrate each strategy as completed
4. Run paper trading after each strategy integration
5. Full cleanup only after all strategies validated

---

## 7. Rollback Plan

If new strategies underperform or have bugs:

1. **Git Tags:** Tag current working version before changes
   ```bash
   git tag v1.0-intraday-old
   ```

2. **Branch Strategy:** Develop on feature branch
   ```bash
   git checkout -b feature/intraday-v2
   ```

3. **Quick Rollback:** Revert to old strategies
   ```bash
   git checkout v1.0-intraday-old
   ```

4. **Parallel Running:** Keep old strategy files until new ones proven
   - Rename old files with `.bak` suffix
   - Delete only after 1 week of successful paper trading

---

## 8. Success Metrics

### Paper Trading Validation (1 Week)

| Strategy | Target Win Rate | Target Sharpe | Target Trades |
|----------|-----------------|---------------|---------------|
| ORB V2 | > 60% | > 1.5 | > 20 |
| Overnight Reversal | N/A | > 2.0 | > 50 |
| Stocks in Play | > 25% | > 1.5 | > 20 |

### Live Trading Validation (1 Month)

| Metric | Target |
|--------|--------|
| Total P&L | > $0 (profitable) |
| Max Drawdown | < 15% |
| Sharpe Ratio | > 1.0 |
| Win Rate | > 40% |

---

## 9. Checklist Summary

### Phase 1: Data Layer
- [ ] 1.1 Add `get_prior_close()`
- [ ] 1.2 Add `calculate_overnight_return()`
- [ ] 1.3 Add `get_overnight_return_deciles()`
- [ ] 1.4 Create `historical_data.py` with ATR, avg volume
- [ ] 1.5 Add `get_stocks_in_play()`
- [ ] 1.6 Add `get_first_5min_candle()`

### Phase 2: ORB V2 Strategy
- [ ] 2.1 Create ORBV2Strategy class
- [ ] 2.2 Implement entry logic (breakout, range filter)
- [ ] 2.3 Implement exit logic (50% target, range low stop, 3 PM)
- [ ] 2.4 Implement candidate screening
- [ ] 2.5 Add daily trade tracking

### Phase 3: Overnight Reversal Strategy
- [ ] 3.1 Create OvernightReversalStrategy class
- [ ] 3.2 Implement entry logic (bottom decile at open)
- [ ] 3.3 Implement exit logic (4 PM only, no stops)
- [ ] 3.4 Implement candidate screening
- [ ] 3.5 Add entry timing restriction

### Phase 4: Stocks in Play Strategy
- [ ] 4.1 Create StocksInPlayStrategy class
- [ ] 4.2 Implement pre-market screening
- [ ] 4.3 Implement entry logic (first 5-min candle)
- [ ] 4.4 Implement exit logic (ATR stop, 4 PM)
- [ ] 4.5 Implement candidate screening
- [ ] 4.6 Add short selling support

### Phase 5: Integration
- [ ] 5.1 Update config.py StrategyType enum
- [ ] 5.2 Update config.py parameters
- [ ] 5.3 Update strategies/__init__.py
- [ ] 5.4 Update intraday_bot.py initialization
- [ ] 5.5 Update logging
- [ ] 5.6 Handle short positions

### Phase 6: Testing
- [ ] 6.1 Unit tests for data layer
- [ ] 6.2 Unit tests for ORB V2
- [ ] 6.3 Unit tests for Overnight Reversal
- [ ] 6.4 Unit tests for Stocks in Play
- [ ] 6.5 Integration test (full trading day)
- [ ] 6.6 Performance monitoring setup

### Phase 7: Cleanup
- [ ] 7.1 Remove old strategy files
- [ ] 7.2 Remove old data methods
- [ ] 7.3 Update CLAUDE.md
- [ ] 7.4 Archive old documentation

---

*Document Version: 1.0*
*Last Updated: December 30, 2025*
