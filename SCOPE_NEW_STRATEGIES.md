# Project Scope: 3 New Intraday Trading Strategies

## Overview

**Goal:** Replace ALL 3 current strategies with 3 proven intraday strategies that work with 1-5 minute candle data.

**New Strategies (LONG ONLY):**
1. **Gap and Go** - Morning momentum (9:30-10:00 AM)
2. **VWAP Pullback** - Mid-day mean reversion (10:00 AM - 2:00 PM)
3. **Opening Range Breakout (ORB) 15-min** - Clean breakout signals (9:45 AM+)

**Remove:** `ORB_V2`, `OVERNIGHT_REVERSAL`, `STOCKS_IN_PLAY`

**Direction:** All strategies are **LONG ONLY** (no shorting, no margin required)

---

## Architecture Decisions

### Account Allocation (1:1 mapping)
| Strategy | Account | API Key |
|----------|---------|---------|
| Gap and Go | ORB Account | PKUWXI5L... |
| VWAP Pullback | WMA Account | PKEWDBHR... |
| ORB 15-min | HMA Account | PKTGRHXB... |

### Data Requirements
All strategies use existing `IntradayIndicators` class with:
- 1-minute bars from VV7 SQLite database
- VWAP calculations (already implemented)
- Volume data for confirmation

### New Indicator Needs
- [ ] Pre-market gap calculation (today open vs yesterday close)
- [ ] Pre-market volume tracking (if VV7 has pre-market data)
- [ ] 15-minute opening range (separate from 60-min)
- [ ] VWAP deviation bands (+/- 1 std dev)

### Direction
- **All strategies: LONG ONLY**
- No short selling
- No margin account required
- Simpler execution, fewer edge cases

---

## Development Phases

### Phase 1: Data Layer Enhancements
**Goal:** Add indicator calculations needed by new strategies

#### 1.1 Pre-market Gap Calculator
- [ ] **1.1.1** Add `get_overnight_gap(symbol)` method to `IntradayIndicators`
  - Returns: `{gap_pct, prev_close, today_open, direction}`
  - Gap % = (today_open - prev_close) / prev_close * 100
  - Only consider **positive gaps** (gap ups) for long-only
  - **Acceptance:** Returns correct gap for AAPL on any trading day

- [ ] **1.1.2** Add `get_gap_up_stocks(min_gap_pct=4.0)` method
  - Scans all symbols for stocks gapping UP > threshold
  - Filter: Only positive gaps (for long-only strategy)
  - Returns: List of `{symbol, gap_pct, today_open, volume}` sorted by gap %
  - **Acceptance:** Returns 10-50 stocks each morning with >4% gap ups

#### 1.2 Pre-market Volume Tracking
- [ ] **1.2.1** Add `get_premarket_volume(symbol)` method
  - Sum volume from 4:00 AM to 9:30 AM (if available in VV7)
  - Fallback: Use first 5-min volume as proxy
  - **Acceptance:** Returns non-zero volume for active stocks

- [ ] **1.2.2** Add `get_relative_premarket_volume(symbol)` method
  - Compare to 20-day average pre-market volume
  - Returns: multiple (e.g., 2.5x = 250% of normal)
  - **Acceptance:** High-activity stocks show >2x relative volume

#### 1.3 Opening Range (15-minute)
- [ ] **1.3.1** Add `get_opening_range_15min(symbol)` method
  - High/low of first 15 minutes (9:30-9:45 AM)
  - Returns: `{high, low, range_size, range_pct}`
  - **Acceptance:** Different from 60-min range, smaller range_size

#### 1.4 VWAP Deviation Bands
- [ ] **1.4.1** Add `get_vwap_with_bands(symbol)` method
  - Returns: `{vwap, upper_band, lower_band, std_dev}`
  - Bands = VWAP +/- 1 standard deviation
  - **Acceptance:** Price oscillates between bands during the day

---

### Phase 2: Gap and Go Strategy (LONG ONLY)
**Goal:** Implement morning momentum strategy (9:30-10:00 AM)

#### 2.1 Strategy Class Creation
- [ ] **2.1.1** Create `strategies/gap_and_go_strategy.py`
  - Inherit from `BaseStrategy`
  - Initialize with `IntradayIndicators` reference
  - **Acceptance:** File created, imports work

- [ ] **2.1.2** Implement `__init__()` with constants
  ```python
  ENTRY_WINDOW_START = time(9, 30)
  ENTRY_WINDOW_END = time(10, 0)
  MIN_GAP_PCT = 4.0  # Only gap UPS (long only)
  MIN_PREMARKET_VOLUME = 100_000
  MIN_RELATIVE_VOLUME = 1.5
  ```
  - **Acceptance:** Constants accessible, configurable via config.py

#### 2.2 Entry Logic (LONG ONLY)
- [ ] **2.2.1** Implement `get_candidates()` method
  - Scan for stocks gapping UP >4% with high pre-market volume
  - Filter: Price > $5, relative volume > 1.5x
  - Filter: Only POSITIVE gaps (long only)
  - Sort by gap % descending
  - Return top 10 candidates
  - **Acceptance:** Returns valid long candidates at 9:30 AM

- [ ] **2.2.2** Implement `check_entry()` method
  - Time check: 9:30-10:00 AM only
  - Entry trigger: Price breaks above pre-market high
  - OR: First 1-min candle high broken
  - Confirmation: Volume spike on breakout candle
  - Direction: LONG ONLY
  - **Acceptance:** Entry signals generated only during window

- [ ] **2.2.3** Calculate entry signal with targets/stops
  - Entry: Current price (breakout level)
  - Stop: Pre-market low OR first candle low
  - Target: 2:1 R/R based on stop distance
  - Direction: 'long' always
  - **Acceptance:** EntrySignal has valid target/stop, direction='long'

#### 2.3 Exit Logic
- [ ] **2.3.1** Implement `check_exit()` method
  - Target hit: price >= target
  - Stop hit: price <= stop
  - Momentum loss: Price drops below VWAP
  - Time exit: 10:00 AM forced exit if no target/stop
  - **Acceptance:** Exits triggered correctly for each condition

#### 2.4 Configuration
- [ ] **2.4.1** Add `GAP_AND_GO` to `StrategyType` enum
- [ ] **2.4.2** Add strategy config to `STRATEGY_CONFIG`
  ```python
  StrategyType.GAP_AND_GO: {
      "name": "Gap and Go",
      "max_positions": 3,
      "position_size_pct": 0.15,
      "risk_per_trade_pct": 0.02,
      "eod_exit_time": time(10, 0),
      "min_gap_pct": 4.0,
      "direction": "long",  # Long only
  }
  ```
- [ ] **2.4.3** Assign ORB account to Gap and Go
  - **Acceptance:** Config compiles, account credentials work

---

### Phase 3: VWAP Pullback Strategy (LONG ONLY)
**Goal:** Implement mid-day mean reversion (10:00 AM - 2:00 PM)

#### 3.1 Strategy Class Creation
- [ ] **3.1.1** Create `strategies/vwap_pullback_strategy.py`
  - Inherit from `BaseStrategy`
  - **Acceptance:** File created, imports work

- [ ] **3.1.2** Implement `__init__()` with constants
  ```python
  ENTRY_WINDOW_START = time(10, 0)
  ENTRY_WINDOW_END = time(14, 0)
  MIN_PRICE = 10.0
  MIN_AVG_VOLUME = 500_000
  PULLBACK_THRESHOLD = 0.002  # 0.2% from VWAP
  ```
  - **Acceptance:** Constants accessible

#### 3.2 Universe Screening
- [ ] **3.2.1** Implement `_get_tradeable_universe()` method
  - Filter: Price > $10, avg volume > 500k
  - Filter: Stocks ABOVE VWAP (for long-only pullback)
  - **Acceptance:** Returns 50-200 liquid stocks above VWAP

#### 3.3 Entry Logic (LONG ONLY)
- [ ] **3.3.1** Implement `get_candidates()` method
  - Find stocks pulling back TO VWAP from above
  - Long only: Price was above VWAP, now touching VWAP
  - Confirm: RSI(14) > 50 (bullish bias)
  - **Acceptance:** Returns candidates touching VWAP from above

- [ ] **3.3.2** Implement `check_entry()` method
  - Time check: 10:00 AM - 2:00 PM
  - Entry: Price within 0.2% of VWAP (from above)
  - Confirmation: 3 candles holding above VWAP after touch
  - Volume: Above average on bounce candle
  - Direction: LONG ONLY
  - **Acceptance:** Entry signals are long only

- [ ] **3.3.3** Calculate entry signal with targets/stops
  - Entry: Current price (at VWAP bounce)
  - Stop: Just below VWAP (0.3% below)
  - Target: Prior high or 1.5:1 R/R
  - Direction: 'long' always
  - **Acceptance:** EntrySignal has valid target/stop, direction='long'

#### 3.4 Exit Logic
- [ ] **3.4.1** Implement `check_exit()` method
  - Target hit: price >= target
  - Stop hit: price falls 0.3% below VWAP
  - Reversal: Price loses VWAP for 3 candles
  - EOD: 2:00 PM forced exit
  - **Acceptance:** Exits triggered correctly

#### 3.5 Configuration
- [ ] **3.5.1** Add `VWAP_PULLBACK` to `StrategyType` enum
- [ ] **3.5.2** Add strategy config to `STRATEGY_CONFIG`
  ```python
  StrategyType.VWAP_PULLBACK: {
      "name": "VWAP Pullback",
      "max_positions": 5,
      "position_size_pct": 0.10,
      "risk_per_trade_pct": 0.015,
      "eod_exit_time": time(14, 0),
      "direction": "long",  # Long only
  }
  ```
- [ ] **3.5.3** Assign WMA account to VWAP Pullback
  - **Acceptance:** Config compiles, account credentials work

---

### Phase 4: ORB 15-Minute Strategy (LONG ONLY)
**Goal:** Implement clean opening range breakout (9:45 AM+)

#### 4.1 Strategy Class Creation
- [ ] **4.1.1** Create `strategies/orb_15min_strategy.py`
  - Inherit from `BaseStrategy`
  - **Acceptance:** File created, imports work

- [ ] **4.1.2** Implement `__init__()` with constants
  ```python
  OPENING_RANGE_END = time(9, 45)
  ENTRY_START = time(9, 45)
  ENTRY_END = time(11, 0)
  MIN_RANGE_PCT = 0.003  # 0.3% minimum range
  MAX_RANGE_PCT = 0.015  # 1.5% maximum range
  ```
  - **Acceptance:** Constants accessible

#### 4.2 Opening Range Calculation
- [ ] **4.2.1** Implement `_get_opening_range()` method
  - Calculate high/low of 9:30-9:45 AM
  - Return: `{high, low, range_size, range_pct, mid}`
  - **Acceptance:** Correct range for any symbol

#### 4.3 Entry Logic (LONG ONLY)
- [ ] **4.3.1** Implement `get_candidates()` method
  - Filter: Range width between 0.3% and 1.5%
  - Filter: Volume > 1.5x average in first 15 min
  - Filter: Price above VWAP (bullish bias for long)
  - **Acceptance:** Returns valid long breakout candidates

- [ ] **4.3.2** Implement `check_entry()` method
  - Time check: 9:45 AM - 11:00 AM
  - Entry (Long only): 5-min candle CLOSES above range high
  - Confirmation: RVOL > 1.5x, price above VWAP
  - Direction: LONG ONLY (ignore breakdowns)
  - **Acceptance:** Entry on candle close above range high only

- [ ] **4.3.3** Calculate entry signal with targets/stops
  - Entry: Current price (breakout close)
  - Stop: Range low OR middle of range
  - Target: 100% of range height from entry
  - Direction: 'long' always
  - **Acceptance:** EntrySignal has valid target/stop, direction='long'

#### 4.4 Exit Logic
- [ ] **4.4.1** Implement `check_exit()` method
  - Target hit: price moves 100% of range from entry
  - Stop hit: price returns to range low
  - Failed breakout: Price re-enters range and closes inside
  - EOD: 11:00 AM forced exit (early cutoff)
  - **Acceptance:** Exits triggered correctly

#### 4.5 Configuration
- [ ] **4.5.1** Add `ORB_15MIN` to `StrategyType` enum
- [ ] **4.5.2** Add strategy config to `STRATEGY_CONFIG`
  ```python
  StrategyType.ORB_15MIN: {
      "name": "ORB 15-Minute",
      "max_positions": 3,
      "position_size_pct": 0.10,
      "risk_per_trade_pct": 0.02,
      "eod_exit_time": time(11, 0),
      "direction": "long",  # Long only
  }
  ```
- [ ] **4.5.3** Assign HMA account to ORB 15-min
  - **Acceptance:** Config compiles, account credentials work

---

### Phase 5: Integration & Orchestrator Updates
**Goal:** Wire new strategies into the bot, remove old ones

#### 5.1 Remove ALL Old Strategies
- [ ] **5.1.1** Remove `ORB_V2` from `StrategyType` enum
- [ ] **5.1.2** Remove `OVERNIGHT_REVERSAL` from `StrategyType` enum
- [ ] **5.1.3** Remove `STOCKS_IN_PLAY` from `StrategyType` enum
- [ ] **5.1.4** Remove all old strategy configs from `STRATEGY_CONFIG`
- [ ] **5.1.5** Delete `strategies/orb_v2_strategy.py`
- [ ] **5.1.6** Delete `strategies/overnight_reversal_strategy.py`
- [ ] **5.1.7** Delete `strategies/stocks_in_play_strategy.py`
  - **Acceptance:** Bot compiles without old strategies

#### 5.2 Add New Strategies to Bot
- [ ] **5.2.1** Add `_init_gap_and_go()` method to `IntradayBot`
- [ ] **5.2.2** Add `_init_vwap_pullback()` method to `IntradayBot`
- [ ] **5.2.3** Add `_init_orb_15min()` method to `IntradayBot`
- [ ] **5.2.4** Remove old init methods (`_init_orb_v2`, `_init_overnight_reversal`, `_init_stocks_in_play`)
- [ ] **5.2.5** Update `__init__()` to call only new init methods
  - **Acceptance:** Bot initializes all 3 new strategies

#### 5.3 Update Account Mapping
- [ ] **5.3.1** Update `ACCOUNTS` dict in config.py
  ```python
  ACCOUNTS = {
      StrategyType.GAP_AND_GO: {
          "api_key": ALPACA_ORB_API_KEY,
          "secret_key": ALPACA_ORB_SECRET_KEY,
          "name": "GAP_AND_GO",
      },
      StrategyType.VWAP_PULLBACK: {
          "api_key": ALPACA_WMA_API_KEY,
          "secret_key": ALPACA_WMA_SECRET_KEY,
          "name": "VWAP_PULLBACK",
      },
      StrategyType.ORB_15MIN: {
          "api_key": ALPACA_HMA_API_KEY,
          "secret_key": ALPACA_HMA_SECRET_KEY,
          "name": "ORB_15MIN",
      },
  }
  ```
  - **Acceptance:** Each strategy has valid credentials

#### 5.4 Update Logging
- [ ] **5.4.1** Remove old log files references
- [ ] **5.4.2** Add log files for new strategies
  - `logs/trading_gap_and_go.log`
  - `logs/trading_vwap_pullback.log`
  - `logs/trading_orb_15min.log`
- [ ] **5.4.3** Add trade journals for new strategies
  - `logs/trade_journal_gap_and_go.csv`
  - `logs/trade_journal_vwap_pullback.csv`
  - `logs/trade_journal_orb_15min.csv`
  - **Acceptance:** Logs created on bot start

---

### Phase 6: Testing & Validation
**Goal:** Verify strategies work correctly

#### 6.1 Unit Tests (Indicators)
- [ ] **6.1.1** Test `get_overnight_gap()` with known values
- [ ] **6.1.2** Test `get_opening_range_15min()` correctness
- [ ] **6.1.3** Test `get_vwap_with_bands()` calculation
  - **Acceptance:** All indicator tests pass

#### 6.2 Strategy Logic Tests
- [ ] **6.2.1** Test Gap and Go entry logic with mock data
- [ ] **6.2.2** Test VWAP Pullback entry/exit logic
- [ ] **6.2.3** Test ORB 15-min breakout detection
- [ ] **6.2.4** Verify all strategies only generate LONG signals
  - **Acceptance:** Strategies generate correct long-only signals

#### 6.3 Integration Tests
- [ ] **6.3.1** Run bot in paper mode for full trading day
- [ ] **6.3.2** Verify entries execute at correct times
- [ ] **6.3.3** Verify exits trigger correctly (target/stop/eod)
- [ ] **6.3.4** Verify no short positions are opened
  - **Acceptance:** Full day runs without errors, long only

#### 6.4 Performance Monitoring
- [ ] **6.4.1** Review trade journals after 1 week
- [ ] **6.4.2** Calculate actual win rate per strategy
- [ ] **6.4.3** Identify any false signals or missed entries
  - **Acceptance:** Strategies perform as expected

---

### Phase 7: Documentation & Cleanup
**Goal:** Finalize and document

#### 7.1 Update CLAUDE.md
- [ ] **7.1.1** Update strategy table with new strategies
- [ ] **7.1.2** Document new entry/exit rules
- [ ] **7.1.3** Update account allocation
- [ ] **7.1.4** Note: All strategies are LONG ONLY
  - **Acceptance:** CLAUDE.md reflects current state

#### 7.2 Code Cleanup
- [ ] **7.2.1** Remove any dead code references to old strategies
- [ ] **7.2.2** Ensure consistent code style
- [ ] **7.2.3** Add docstrings to new methods
  - **Acceptance:** Code is clean and documented

#### 7.3 Git Commits
- [ ] **7.3.1** Commit Phase 1 (data layer)
- [ ] **7.3.2** Commit Phase 2 (Gap and Go)
- [ ] **7.3.3** Commit Phase 3 (VWAP Pullback)
- [ ] **7.3.4** Commit Phase 4 (ORB 15-min)
- [ ] **7.3.5** Commit Phase 5 (integration, remove old)
- [ ] **7.3.6** Final commit (cleanup)
  - **Acceptance:** Clean git history

---

## Strategy Rules Summary (ALL LONG ONLY)

### Gap and Go (LONG ONLY)
| Aspect | Rule |
|--------|------|
| **Direction** | **LONG ONLY** (gap ups only) |
| **Time Window** | 9:30-10:00 AM ET |
| **Entry** | Break of pre-market high with volume |
| **Stop** | Pre-market low or first candle low |
| **Target** | 2:1 R/R or new high of day |
| **Exit** | Target, stop, or 10:00 AM |

### VWAP Pullback (LONG ONLY)
| Aspect | Rule |
|--------|------|
| **Direction** | **LONG ONLY** (pullback from above VWAP) |
| **Time Window** | 10:00 AM - 2:00 PM ET |
| **Entry** | Price pulls back to VWAP from above, bounces |
| **Stop** | 0.3% below VWAP |
| **Target** | Prior high or 1.5:1 R/R |
| **Exit** | Target, stop, VWAP loss, or 2:00 PM |

### ORB 15-Minute (LONG ONLY)
| Aspect | Rule |
|--------|------|
| **Direction** | **LONG ONLY** (breakout above range) |
| **Time Window** | 9:45-11:00 AM ET |
| **Opening Range** | 9:30-9:45 AM high/low |
| **Entry** | 5-min candle CLOSES above range high |
| **Stop** | Range low or middle of range |
| **Target** | 100% of range from entry |
| **Exit** | Target, stop, failed breakout, or 11:00 AM |

---

## Account Allocation

| Strategy | Account | API Key | Direction |
|----------|---------|---------|-----------|
| Gap and Go | ORB Account | PKUWXI5L... | Long only |
| VWAP Pullback | WMA Account | PKEWDBHR... | Long only |
| ORB 15-min | HMA Account | PKTGRHXB... | Long only |

---

## Estimated Timeline

| Phase | Tasks | Est. Time |
|-------|-------|-----------|
| Phase 1 | Data Layer | 2-3 hours |
| Phase 2 | Gap and Go | 2-3 hours |
| Phase 3 | VWAP Pullback | 2-3 hours |
| Phase 4 | ORB 15-min | 2-3 hours |
| Phase 5 | Integration | 1-2 hours |
| Phase 6 | Testing | 2-4 hours |
| Phase 7 | Documentation | 1 hour |
| **Total** | | **12-19 hours** |

---

## Risk Considerations

1. **Gap and Go** - High volatility, fast moves. Position sizing critical.
2. **VWAP Pullback** - May not work in strong downtrends. Only trade when above VWAP.
3. **ORB 15-min** - False breakouts common. Wait for candle close.
4. **Long Only** - Miss short opportunities, but simpler execution and no margin issues.

---

## Success Criteria

- [ ] All 3 strategies run concurrently without errors
- [ ] Each strategy executes entries within its time window
- [ ] All positions are LONG only (no shorts)
- [ ] Exits trigger correctly (target/stop/time)
- [ ] No positions held overnight
- [ ] Trade journals record all activity
- [ ] Win rate >50% after 1 week of paper trading
