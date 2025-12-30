# Intraday Trading Bot - 3 Strategy Implementation Scope

## Overview

**Project Goal:** Replace the existing SAFE and CLASSIC RSI(2) swing trading strategies with 3 new high-win-rate intraday strategies, each running on a dedicated Alpaca paper trading account.

**Current State:** Dual-account RSI(2) mean reversion bot (swing trading, 2-5 day holds)
**Target State:** Triple-account intraday bot (same-day entry & exit)

---

## Strategy Specifications

| Strategy | Account | Win Rate | Entry Logic | Exit Logic | EOD Exit |
|----------|---------|----------|-------------|------------|----------|
| **ORB** | $91,680 | 89.4% | 60-min breakout + filters | Target/Stop/Time | 2:00 PM |
| **WMA20_HA** | $28,844 | 83% | WMA(20) cross + HA pattern | WMA cross / color | 3:45 PM |
| **HMA_HA** | $28,483 | 77% | HMA cross + HA confirm | HMA cross / color | 3:45 PM |

### Strategy 1: 60-Minute Opening Range Breakout (ORB)

```
ENTRY CONDITIONS (All Required):
├─ Time: After 10:30 AM ET (60-min range established)
├─ Price closes ABOVE 60-min opening range HIGH
├─ Volume > 1.5x relative volume (vs 20-day avg at same time)
├─ Price > VWAP
└─ 20 EMA slope is UP (current > previous bar)

EXIT CONDITIONS (First Triggered):
├─ TARGET: Range height projected from breakout point
├─ STOP: Few ticks inside range (below range high for longs)
├─ TIME: 2:00 PM ET forced exit (ORB works early in day)
└─ EOD: Any remaining positions closed

POSITION SIZING:
├─ Max 5 positions
├─ 10% of equity per position ($9,168)
└─ Risk 2% per trade ($1,834 max loss)
```

### Strategy 2: WMA(20) + Heikin Ashi

```
ENTRY CONDITIONS (All Required):
├─ Heikin Ashi close crosses ABOVE WMA(20)
├─ Two consecutive GREEN Heikin Ashi candles
└─ Both candles are "flat-bottomed" (no lower wick)

EXIT CONDITIONS (First Triggered):
├─ Heikin Ashi close crosses BELOW WMA(20)
├─ Color change (green → red Heikin Ashi)
├─ Lower wick appears on HA candle
└─ EOD: 3:45 PM ET forced exit

POSITION SIZING:
├─ Max 5 positions
├─ 10% of equity per position ($2,884)
└─ Risk 2% per trade ($577 max loss)
```

### Strategy 3: HMA + Heikin Ashi

```
ENTRY CONDITIONS (All Required):
├─ Heikin Ashi close crosses ABOVE Hull Moving Average
└─ Green Heikin Ashi candle confirmation

EXIT CONDITIONS (First Triggered):
├─ Heikin Ashi close crosses BELOW HMA
├─ Color change (green → red Heikin Ashi)
└─ EOD: 3:45 PM ET forced exit

POSITION SIZING:
├─ Max 5 positions
├─ 10% of equity per position ($2,848)
└─ Risk 2% per trade ($570 max loss)
```

---

## Account Configuration

| Account | API Key | Secret Key | Equity |
|---------|---------|------------|--------|
| ORB | `PKUWXI5LD5GMPQTLHTGZLJMHMA` | `9xjaaU9RLuS1TXZ3niVCKdKd14Xm7MVSatkkkUGsFvoH` | $91,680 |
| WMA20_HA | `PKEWDBHRFW7RMW2YXXRCAGE6ZJ` | `8dYkVbFmJdN3t53bf1dsGv6pZRhRCTffTLR5mLGG1bNn` | $28,844 |
| HMA_HA | `PKTGRHXB4LUKDH7T4PK3SOZIPX` | `9dCHV3gRciNXFduiQXdvxkV12cUKNmVgM8VGBRGyMEL5` | $28,483 |

---

## Data Source

**Database:** `%LOCALAPPDATA%\VV7SimpleBridge\intraday.db`

### Available Tables

| Table | Contents | Rows |
|-------|----------|------|
| `bars_1min` | 1-minute OHLCV candles | 9.6M |
| `indicators` | Pre-computed indicators (snapshot) | ~9,800 |

### bars_1min Schema (PRIMARY DATA SOURCE)

```sql
CREATE TABLE bars_1min (
    symbol TEXT,
    timestamp INTEGER,  -- Unix timestamp
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER
);
```

### Required Calculations from bars_1min

| Indicator | Formula | Used By |
|-----------|---------|---------|
| **VWAP** | Cumulative(Price × Volume) / Cumulative(Volume) | ORB |
| **EMA(20)** | EMA formula with α = 2/(20+1) | ORB |
| **WMA(20)** | Σ(Price × Weight) / Σ(Weight), weight = position | WMA20_HA |
| **HMA** | WMA(2×WMA(n/2) - WMA(n), √n) | HMA_HA |
| **Heikin Ashi** | HA_Close = (O+H+L+C)/4, HA_Open = (prev_HA_O + prev_HA_C)/2 | WMA20_HA, HMA_HA |
| **Opening Range** | High/Low of first 60 minutes (9:30-10:30 AM) | ORB |
| **Relative Volume** | Current volume / Avg volume at same time of day | ORB |

---

## Architecture

### Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    IntradayBot (Orchestrator)               │
│  - 3 account management (ORB, WMA20_HA, HMA_HA)            │
│  - Cycle scheduling & market hours                          │
│  - EOD position closure                                     │
└───────────┬─────────────────────┬─────────────────┬─────────┘
            │                     │                 │
    ┌───────▼───────┐    ┌───────▼───────┐   ┌─────▼─────┐
    │  ORBStrategy  │    │ WMA20Strategy │   │HMAStrategy│
    │  (89.4% WR)   │    │  (83% WR)     │   │ (77% WR)  │
    └───────┬───────┘    └───────┬───────┘   └─────┬─────┘
            │                     │                 │
            └─────────────────────┼─────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │    IntradayIndicators     │
                    │  - VWAP, EMA, WMA, HMA    │
                    │  - Heikin Ashi            │
                    │  - Opening Range          │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │      bars_1min Table      │
                    │   (9.6M 1-min candles)    │
                    └───────────────────────────┘
```

### File Structure (Target)

```
trading_bot/
├── intraday_bot.py              # NEW: Main orchestrator (replaces connors_bot.py)
├── config.py                     # MODIFY: New strategy configs
├── requirements.txt              # MODIFY: Add numpy if needed
│
├── strategies/                   # NEW: Strategy implementations
│   ├── __init__.py
│   ├── base_strategy.py         # Abstract base class
│   ├── orb_strategy.py          # 60-min ORB
│   ├── wma_ha_strategy.py       # WMA(20) + Heikin Ashi
│   └── hma_ha_strategy.py       # HMA + Heikin Ashi
│
├── data/
│   ├── __init__.py
│   ├── indicators_db.py         # KEEP: Existing (for reference)
│   └── intraday_indicators.py   # NEW: bars_1min queries + calculations
│
├── execution/
│   ├── __init__.py
│   └── alpaca_client.py         # KEEP: No changes needed
│
└── logs/
    ├── trading_orb.log          # NEW
    ├── trading_wma20_ha.log     # NEW
    ├── trading_hma_ha.log       # NEW
    ├── trade_journal_orb.csv    # NEW
    ├── trade_journal_wma20_ha.csv # NEW
    └── trade_journal_hma_ha.csv # NEW
```

---

## Development Phases

### Phase 1: Data Layer (Indicator Calculations)
Build the foundation for calculating all required indicators from bars_1min.

### Phase 2: Strategy Layer (Entry/Exit Logic)
Implement each strategy with clear entry/exit rules.

### Phase 3: Orchestration Layer (Bot Logic)
Build the main bot that coordinates all 3 strategies.

### Phase 4: Integration & Testing
Connect all layers, test with paper accounts.

### Phase 5: Deployment & Monitoring
Final configuration, logging, and go-live.

---

## Task Checklist

### Phase 1: Data Layer - Indicator Calculations

#### 1.1 Create intraday_indicators.py module
- [ ] **1.1.1** Create `data/intraday_indicators.py` file with class `IntradayIndicators`
- [ ] **1.1.2** Add `__init__(db_path)` with SQLite connection to intraday.db
- [ ] **1.1.3** Add `get_bars(symbol, start_ts, end_ts)` - fetch 1-min bars for symbol
- [ ] **1.1.4** Add `get_all_symbols()` - list unique symbols in bars_1min
- [ ] **1.1.5** Add `get_latest_timestamp()` - most recent bar timestamp

**Acceptance:** Can connect to DB and fetch bars for any symbol

#### 1.2 Implement VWAP calculation
- [ ] **1.2.1** Add `calculate_vwap(bars)` - Volume Weighted Average Price
  ```python
  # VWAP = Cumulative(Typical_Price × Volume) / Cumulative(Volume)
  # Typical_Price = (High + Low + Close) / 3
  # Resets at market open each day
  ```
- [ ] **1.2.2** Add `get_current_vwap(symbol)` - returns current VWAP for symbol
- [ ] **1.2.3** Test VWAP calculation against known values

**Acceptance:** VWAP matches TradingView/broker VWAP for same symbol

#### 1.3 Implement Moving Averages
- [ ] **1.3.1** Add `calculate_ema(prices, period)` - Exponential Moving Average
  ```python
  # EMA = Price × α + Previous_EMA × (1 - α)
  # α = 2 / (period + 1)
  ```
- [ ] **1.3.2** Add `calculate_wma(prices, period)` - Weighted Moving Average
  ```python
  # WMA = Σ(Price_i × i) / Σ(i) for i = 1 to period
  ```
- [ ] **1.3.3** Add `calculate_hma(prices, period)` - Hull Moving Average
  ```python
  # HMA = WMA(2 × WMA(n/2) - WMA(n), √n)
  # Default period = 9
  ```
- [ ] **1.3.4** Add `get_ema20(symbol)` - current EMA(20) for symbol
- [ ] **1.3.5** Add `get_wma20(symbol)` - current WMA(20) for symbol
- [ ] **1.3.6** Add `get_hma(symbol)` - current HMA for symbol
- [ ] **1.3.7** Test all MAs against reference calculations

**Acceptance:** MAs match TradingView values within 0.01%

#### 1.4 Implement Heikin Ashi candles
- [ ] **1.4.1** Add `calculate_heikin_ashi(bars)` - convert OHLC to HA
  ```python
  # HA_Close = (Open + High + Low + Close) / 4
  # HA_Open = (Previous_HA_Open + Previous_HA_Close) / 2
  # HA_High = max(High, HA_Open, HA_Close)
  # HA_Low = min(Low, HA_Open, HA_Close)
  ```
- [ ] **1.4.2** Add `is_green_ha(ha_candle)` - returns True if HA_Close > HA_Open
- [ ] **1.4.3** Add `is_flat_bottom_ha(ha_candle)` - returns True if no lower wick
  ```python
  # Flat bottom = HA_Low == min(HA_Open, HA_Close)
  ```
- [ ] **1.4.4** Add `get_ha_candles(symbol, count)` - last N HA candles
- [ ] **1.4.5** Test HA candles against TradingView HA chart

**Acceptance:** HA candles visually match TradingView HA chart

#### 1.5 Implement Opening Range calculation
- [ ] **1.5.1** Add `get_opening_range(symbol, date)` - returns {high, low, range_size}
  ```python
  # Opening range = High/Low of first 60 minutes (9:30-10:30 AM ET)
  # Range size = High - Low
  ```
- [ ] **1.5.2** Add `is_breakout_above(symbol, current_price)` - True if price > OR high
- [ ] **1.5.3** Add `get_breakout_target(symbol, entry_price)` - target = entry + range_size
- [ ] **1.5.4** Add `get_breakout_stop(symbol)` - stop = just inside range high
- [ ] **1.5.5** Test opening range on known symbols

**Acceptance:** Opening range matches visual inspection of 9:30-10:30 bars

#### 1.6 Implement Relative Volume
- [ ] **1.6.1** Add `calculate_relative_volume(symbol)` - current vs historical avg
  ```python
  # Relative Volume = Current volume / Avg volume at same time of day
  # Use 20-day lookback for average
  ```
- [ ] **1.6.2** Add `get_relative_volume(symbol)` - returns float (1.5 = 150% of avg)
- [ ] **1.6.3** Test relative volume calculation

**Acceptance:** Relative volume > 1.0 indicates above-average activity

#### 1.7 Bulk screening queries
- [ ] **1.7.1** Add `get_orb_candidates()` - symbols meeting ORB entry criteria
- [ ] **1.7.2** Add `get_wma_ha_candidates()` - symbols meeting WMA+HA entry criteria
- [ ] **1.7.3** Add `get_hma_ha_candidates()` - symbols meeting HMA+HA entry criteria
- [ ] **1.7.4** Optimize queries with proper indexing

**Acceptance:** Screening returns candidates in < 5 seconds for all ~9,800 symbols

---

### Phase 2: Strategy Layer - Entry/Exit Logic

#### 2.1 Create base strategy class
- [ ] **2.1.1** Create `strategies/base_strategy.py` with abstract `BaseStrategy`
- [ ] **2.1.2** Define abstract method `check_entry(symbol) -> bool`
- [ ] **2.1.3** Define abstract method `check_exit(symbol, position) -> dict`
- [ ] **2.1.4** Define abstract method `get_candidates() -> List[dict]`
- [ ] **2.1.5** Add common properties: `name`, `max_positions`, `position_size_pct`, `eod_exit_time`

**Acceptance:** Base class defines clear interface for all strategies

#### 2.2 Implement ORB Strategy
- [ ] **2.2.1** Create `strategies/orb_strategy.py` with class `ORBStrategy(BaseStrategy)`
- [ ] **2.2.2** Implement `__init__()` with ORB-specific config
  ```python
  self.name = "ORB"
  self.max_positions = 5
  self.position_size_pct = 0.10
  self.eod_exit_time = "14:00"  # 2:00 PM ET
  self.min_relative_volume = 1.5
  ```
- [ ] **2.2.3** Implement `check_entry(symbol)` - all ORB entry conditions
  ```python
  # Returns True if:
  # - Time > 10:30 AM (range established)
  # - Price > Opening range high
  # - Volume > 1.5x relative
  # - Price > VWAP
  # - EMA(20) slope > 0
  ```
- [ ] **2.2.4** Implement `check_exit(symbol, position)` - ORB exit conditions
  ```python
  # Returns exit signal if:
  # - Price >= target (entry + range_size)
  # - Price <= stop (inside range)
  # - Time >= 2:00 PM ET
  ```
- [ ] **2.2.5** Implement `get_candidates()` - screen all symbols for ORB entries
- [ ] **2.2.6** Add `calculate_position_size(equity)` - returns shares to buy
- [ ] **2.2.7** Test ORB strategy logic with sample data

**Acceptance:** ORB correctly identifies breakouts and exits at target/stop/time

#### 2.3 Implement WMA20+HA Strategy
- [ ] **2.3.1** Create `strategies/wma_ha_strategy.py` with class `WMAHAStrategy(BaseStrategy)`
- [ ] **2.3.2** Implement `__init__()` with WMA+HA-specific config
  ```python
  self.name = "WMA20_HA"
  self.max_positions = 5
  self.position_size_pct = 0.10
  self.eod_exit_time = "15:45"  # 3:45 PM ET
  self.wma_period = 20
  ```
- [ ] **2.3.3** Implement `check_entry(symbol)` - WMA+HA entry conditions
  ```python
  # Returns True if:
  # - HA close crossed above WMA(20)
  # - Last 2 HA candles are green
  # - Last 2 HA candles are flat-bottomed (no lower wick)
  ```
- [ ] **2.3.4** Implement `check_exit(symbol, position)` - WMA+HA exit conditions
  ```python
  # Returns exit signal if:
  # - HA close < WMA(20)
  # - HA color changed to red
  # - Lower wick appeared
  # - Time >= 3:45 PM ET
  ```
- [ ] **2.3.5** Implement `get_candidates()` - screen for WMA+HA entries
- [ ] **2.3.6** Test WMA+HA strategy logic with sample data

**Acceptance:** WMA+HA correctly identifies trend entries and reversals

#### 2.4 Implement HMA+HA Strategy
- [ ] **2.4.1** Create `strategies/hma_ha_strategy.py` with class `HMAHAStrategy(BaseStrategy)`
- [ ] **2.4.2** Implement `__init__()` with HMA+HA-specific config
  ```python
  self.name = "HMA_HA"
  self.max_positions = 5
  self.position_size_pct = 0.10
  self.eod_exit_time = "15:45"  # 3:45 PM ET
  self.hma_period = 9
  ```
- [ ] **2.4.3** Implement `check_entry(symbol)` - HMA+HA entry conditions
  ```python
  # Returns True if:
  # - HA close crossed above HMA
  # - Current HA candle is green
  ```
- [ ] **2.4.4** Implement `check_exit(symbol, position)` - HMA+HA exit conditions
  ```python
  # Returns exit signal if:
  # - HA close < HMA
  # - HA color changed to red
  # - Time >= 3:45 PM ET
  ```
- [ ] **2.4.5** Implement `get_candidates()` - screen for HMA+HA entries
- [ ] **2.4.6** Test HMA+HA strategy logic with sample data

**Acceptance:** HMA+HA correctly identifies momentum entries and exits

---

### Phase 3: Orchestration Layer - Bot Logic

#### 3.1 Update config.py
- [ ] **3.1.1** Remove old SAFE/CLASSIC account configs
- [ ] **3.1.2** Add ORB account credentials
  ```python
  ALPACA_ORB_API_KEY = os.environ.get("ALPACA_ORB_API_KEY", "")
  ALPACA_ORB_SECRET_KEY = os.environ.get("ALPACA_ORB_SECRET_KEY", "")
  ```
- [ ] **3.1.3** Add WMA20_HA account credentials
- [ ] **3.1.4** Add HMA_HA account credentials
- [ ] **3.1.5** Add strategy-specific configs (max positions, position size, EOD times)
- [ ] **3.1.6** Update .env file with new API keys
- [ ] **3.1.7** Add validation for all 3 account credentials

**Acceptance:** Config loads all 3 accounts without errors

#### 3.2 Create intraday_bot.py
- [ ] **3.2.1** Create `intraday_bot.py` with class `IntradayBot`
- [ ] **3.2.2** Implement `__init__(paper=True)` - initialize 3 Alpaca clients
  ```python
  self.orb_client = AlpacaClient(paper, ORB_API_KEY, ORB_SECRET_KEY, "ORB")
  self.wma_client = AlpacaClient(paper, WMA_API_KEY, WMA_SECRET_KEY, "WMA20_HA")
  self.hma_client = AlpacaClient(paper, HMA_API_KEY, HMA_SECRET_KEY, "HMA_HA")
  ```
- [ ] **3.2.3** Initialize all 3 strategies
- [ ] **3.2.4** Initialize IntradayIndicators data layer
- [ ] **3.2.5** Set up position tracking dicts for each account
- [ ] **3.2.6** Set up loggers for each account

**Acceptance:** Bot initializes with 3 clients, 3 strategies, shared data layer

#### 3.3 Implement startup checks
- [ ] **3.3.1** Add `startup_checks()` - verify DB, all 3 accounts
- [ ] **3.3.2** Add `check_database()` - verify bars_1min has recent data
- [ ] **3.3.3** Add `check_account(client, name)` - verify account accessible
- [ ] **3.3.4** Log startup status for all components

**Acceptance:** Startup validates all dependencies before trading

#### 3.4 Implement position sync
- [ ] **3.4.1** Add `sync_positions(account)` - sync Alpaca positions to internal tracking
- [ ] **3.4.2** Add `sync_all_positions()` - sync all 3 accounts
- [ ] **3.4.3** Handle position discrepancies (log warnings)

**Acceptance:** Internal position tracking matches Alpaca

#### 3.5 Implement trading cycle
- [ ] **3.5.1** Add `run_cycle()` - execute one trading cycle for all strategies
- [ ] **3.5.2** Add `check_eod_exits()` - force close positions at EOD time per strategy
- [ ] **3.5.3** Add `check_strategy_exits(strategy, client, positions)` - check exit signals
- [ ] **3.5.4** Add `find_strategy_entries(strategy, positions)` - find entry candidates
- [ ] **3.5.5** Add `execute_entry(client, strategy, candidate)` - place buy order
- [ ] **3.5.6** Add `execute_exit(client, strategy, signal)` - close position
- [ ] **3.5.7** Add `log_cycle_summary()` - report cycle results for all 3 accounts

**Acceptance:** Cycle processes exits then entries for all 3 strategies

#### 3.6 Implement main loop
- [ ] **3.6.1** Add `run()` - main loop waiting for market hours and sync file
- [ ] **3.6.2** Add `wait_for_market_open()` - block until 9:30 AM ET
- [ ] **3.6.3** Add `watch_sync_file()` - trigger cycle when sync_complete.txt updated
- [ ] **3.6.4** Add `is_market_hours()` - check if within trading window
- [ ] **3.6.5** Add graceful shutdown handling (Ctrl+C)

**Acceptance:** Bot runs continuously during market hours, cycles on sync

#### 3.7 Implement trade journaling
- [ ] **3.7.1** Add `log_trade(account, symbol, action, shares, price, pnl, strategy_data)`
- [ ] **3.7.2** Create separate CSV journals per account
- [ ] **3.7.3** Add `calculate_session_pnl(account)` - sum today's closed P&L
- [ ] **3.7.4** Add `log_end_of_day_summary()` - final daily report

**Acceptance:** Trade journals capture all entries/exits with P&L

---

### Phase 4: Integration & Testing

#### 4.1 Unit tests for indicators
- [ ] **4.1.1** Test VWAP calculation accuracy
- [ ] **4.1.2** Test EMA(20) calculation accuracy
- [ ] **4.1.3** Test WMA(20) calculation accuracy
- [ ] **4.1.4** Test HMA calculation accuracy
- [ ] **4.1.5** Test Heikin Ashi conversion
- [ ] **4.1.6** Test Opening Range detection
- [ ] **4.1.7** Test Relative Volume calculation

**Acceptance:** All indicator tests pass

#### 4.2 Unit tests for strategies
- [ ] **4.2.1** Test ORB entry detection with mock data
- [ ] **4.2.2** Test ORB exit detection (target/stop/time)
- [ ] **4.2.3** Test WMA+HA entry detection
- [ ] **4.2.4** Test WMA+HA exit detection
- [ ] **4.2.5** Test HMA+HA entry detection
- [ ] **4.2.6** Test HMA+HA exit detection

**Acceptance:** All strategy tests pass

#### 4.3 Integration tests
- [ ] **4.3.1** Test full cycle with paper accounts (no real trades)
- [ ] **4.3.2** Test position sync accuracy
- [ ] **4.3.3** Test EOD forced exit timing
- [ ] **4.3.4** Test trade journal logging
- [ ] **4.3.5** Test cycle summary output

**Acceptance:** Full integration works end-to-end

#### 4.4 Paper trading validation
- [ ] **4.4.1** Run bot for full trading day (paper mode)
- [ ] **4.4.2** Verify entries match expected signals
- [ ] **4.4.3** Verify exits trigger correctly
- [ ] **4.4.4** Verify EOD positions are closed
- [ ] **4.4.5** Review trade journals for accuracy
- [ ] **4.4.6** Check P&L calculations

**Acceptance:** Paper trading matches expected behavior

---

### Phase 5: Deployment & Monitoring

#### 5.1 Configuration finalization
- [ ] **5.1.1** Verify all API keys in .env
- [ ] **5.1.2** Set paper=True for initial deployment
- [ ] **5.1.3** Configure logging levels
- [ ] **5.1.4** Test startup with fresh state

**Acceptance:** Clean startup with no errors

#### 5.2 Documentation
- [ ] **5.2.1** Update CLAUDE.md with new bot instructions
- [ ] **5.2.2** Document strategy parameters
- [ ] **5.2.3** Document troubleshooting steps
- [ ] **5.2.4** Archive old connors_bot.py documentation

**Acceptance:** Documentation reflects new 3-strategy system

#### 5.3 Monitoring setup
- [ ] **5.3.1** Add cycle performance logging (duration, candidates found)
- [ ] **5.3.2** Add daily P&L summary email/notification (optional)
- [ ] **5.3.3** Add error alerting for critical failures
- [ ] **5.3.4** Test log rotation (if needed)

**Acceptance:** Monitoring captures all critical events

#### 5.4 Go-live
- [ ] **5.4.1** Run final paper trading test
- [ ] **5.4.2** Review all positions closed at EOD
- [ ] **5.4.3** Verify no overnight positions
- [ ] **5.4.4** Confirm P&L tracking accurate
- [ ] **5.4.5** Mark deployment complete

**Acceptance:** Bot ready for continuous paper trading

---

## Risk Considerations

### Technical Risks
| Risk | Mitigation |
|------|------------|
| Database lock during sync | Use WAL mode, retry logic |
| API rate limits | Add exponential backoff |
| Partial fills | Handle in AlpacaClient (already implemented) |
| Network failures | Graceful reconnection, log errors |

### Strategy Risks
| Risk | Mitigation |
|------|------------|
| False breakouts (ORB) | Volume + VWAP + EMA filters |
| Whipsaws (MA strategies) | Heikin Ashi smoothing |
| Slippage on exits | Market orders, liquid stocks only |
| EOD forced exits at loss | Accept as cost of intraday discipline |

### Operational Risks
| Risk | Mitigation |
|------|------------|
| Bot crash mid-day | Startup resync, position reconciliation |
| Missing sync file updates | Fallback to time-based cycles |
| Account API issues | Independent account handling, log per account |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| ORB Win Rate | > 85% | Trades closed at target / total trades |
| WMA+HA Win Rate | > 80% | Green exits / total exits |
| HMA+HA Win Rate | > 75% | Green exits / total exits |
| Daily Positions | 5-15 total | Sum across all accounts |
| EOD Closure | 100% | No overnight positions |
| System Uptime | > 99% | Trading hours without crash |

---

## Timeline Estimate

| Phase | Tasks | Dependencies |
|-------|-------|--------------|
| Phase 1 | 1.1 - 1.7 | None |
| Phase 2 | 2.1 - 2.4 | Phase 1 complete |
| Phase 3 | 3.1 - 3.7 | Phase 2 complete |
| Phase 4 | 4.1 - 4.4 | Phase 3 complete |
| Phase 5 | 5.1 - 5.4 | Phase 4 complete |

---

## Appendix: Indicator Formulas

### VWAP (Volume Weighted Average Price)
```python
typical_price = (high + low + close) / 3
cumulative_tp_volume = sum(typical_price * volume)  # Since market open
cumulative_volume = sum(volume)  # Since market open
vwap = cumulative_tp_volume / cumulative_volume
```

### EMA (Exponential Moving Average)
```python
alpha = 2 / (period + 1)
ema[0] = close[0]  # First value = first close
ema[i] = close[i] * alpha + ema[i-1] * (1 - alpha)
```

### WMA (Weighted Moving Average)
```python
weights = [1, 2, 3, ..., period]
wma = sum(close[i] * weights[i]) / sum(weights)
```

### HMA (Hull Moving Average)
```python
half_period = period // 2
sqrt_period = int(sqrt(period))
wma_half = WMA(close, half_period)
wma_full = WMA(close, period)
raw_hma = 2 * wma_half - wma_full
hma = WMA(raw_hma, sqrt_period)
```

### Heikin Ashi
```python
ha_close = (open + high + low + close) / 4
ha_open = (prev_ha_open + prev_ha_close) / 2  # First bar: (open + close) / 2
ha_high = max(high, ha_open, ha_close)
ha_low = min(low, ha_open, ha_close)
```

### Opening Range (60-minute)
```python
market_open = 9:30 AM ET
range_end = 10:30 AM ET
bars_in_range = get_bars(symbol, market_open, range_end)
or_high = max(bar.high for bar in bars_in_range)
or_low = min(bar.low for bar in bars_in_range)
or_size = or_high - or_low
```

### Relative Volume
```python
current_volume = sum(volume since market open)
current_time = now()
historical_avg = avg(volume at same time of day over 20 days)
relative_volume = current_volume / historical_avg
```
