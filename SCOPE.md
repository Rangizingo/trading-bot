# Trading Bot - Project Scope & Development Checklist

## Overview

**Goal:** Autonomous paper trading bot optimized for highest statistical probability of profitable trades.

**Data Source:** VV7 API (localhost:5000) - 9,850 stocks, 158 endpoints, bulk data in <30 sec

**Execution:** Alpaca Paper Trading API

**Target Metrics:**
- Win Rate: >65%
- Profit Factor: >2.0
- Max Drawdown: <15%
- Sharpe Ratio: >2.0

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TRADING BOT                              │
├─────────────────────────────────────────────────────────────────┤
│  main.py                                                        │
│    └── Orchestrator (market hours, 5-min cycles)               │
├─────────────────────────────────────────────────────────────────┤
│  data/                                                          │
│    ├── vv7_client.py    → HTTP to VV7 API (:5000)              │
│    ├── cache.py         → SQLite bulk cache                     │
│    └── models.py        → Bar, Stock, Signal dataclasses       │
├─────────────────────────────────────────────────────────────────┤
│  core/                                                          │
│    ├── indicators.py    → RSI, MACD, BB, VWAP, Keltner         │
│    ├── position.py      → Capital tracking, position mgmt      │
│    └── risk.py          → Position sizing, drawdown limits     │
├─────────────────────────────────────────────────────────────────┤
│  strategies/                                                    │
│    ├── base.py          → Strategy interface                   │
│    ├── connors_rsi.py   → RSI(2) mean reversion                │
│    ├── cumulative_rsi.py→ Sum RSI(2) over N bars               │
│    ├── vwap_rsi.py      → VWAP + RSI filter                    │
│    ├── keltner_rsi.py   → Keltner Channel + RSI                │
│    └── bb_rsi.py        → Bollinger Band + RSI                 │
├─────────────────────────────────────────────────────────────────┤
│  execution/                                                     │
│    ├── alpaca.py        → Order execution, position tracking   │
│    └── paper.py         → Paper trading simulation             │
├─────────────────────────────────────────────────────────────────┤
│  backtest/                                                      │
│    ├── engine.py        → Backtest runner (FIXED logic)        │
│    ├── data_loader.py   → Load from alpaca_historical.db       │
│    └── metrics.py       → Win rate, PF, Sharpe, drawdown       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration

```python
# config.py
CAPITAL = 100_000
POSITION_SIZE_PCT = 10          # % of capital per trade
MAX_POSITIONS = 5               # Concurrent positions
RISK_PER_TRADE_PCT = 2          # Max loss per trade
DAILY_DRAWDOWN_LIMIT_PCT = 5    # Pause trading threshold
TOTAL_DRAWDOWN_LIMIT_PCT = 15   # Full stop threshold
KELLY_FRACTION = 0.5            # Half-Kelly sizing
```

---

## Development Phases

### Phase 1: Foundation (Core Infrastructure)

- [x] **1.1** Create project folder structure
- [x] **1.2** Create `config.py` with all parameters
- [x] **1.3** Create `data/models.py` - Bar, Stock, Signal, Position dataclasses
- [x] **1.4** Create `core/position.py` - PositionManager with capital tracking
  - [x] 1.4.1 `open_position()` - deduct capital
  - [x] 1.4.2 `close_position()` - return proceeds (not just PnL)
  - [x] 1.4.3 `get_available_capital()` - track what's actually free
  - [x] 1.4.4 `get_equity()` - capital + unrealized PnL
- [x] **1.5** Create `core/risk.py` - Risk management
  - [x] 1.5.1 Half-Kelly position sizing
  - [x] 1.5.2 Daily drawdown check
  - [x] 1.5.3 Total drawdown check
  - [x] 1.5.4 Max positions check
- [ ] **1.6** Unit tests for position and risk management

**Acceptance:** Can track capital through open/close cycles accurately

---

### Phase 2: Data Layer (VV7 API Integration)

- [x] **2.1** Create `data/vv7_client.py` - HTTP client
  - [x] 2.1.1 `get_bulk_ratings()` - all 9,850 stocks
  - [x] 2.1.2 `get_bulk_technicals()` - RSI, MACD, BB, etc.
  - [x] 2.1.3 `get_stock_history()` - historical bars
  - [x] 2.1.4 `get_market_timing()` - SPY regime filter
  - [x] 2.1.5 Error handling and retries
- [x] **2.2** Create `data/cache.py` - SQLite cache
  - [x] 2.2.1 `sync_ratings()` - bulk insert ratings
  - [x] 2.2.2 `sync_technicals()` - bulk insert technicals
  - [x] 2.2.3 `get_cached_data()` - query cache
  - [x] 2.2.4 `is_stale()` - check if refresh needed
- [ ] **2.3** Integration test with live VV7 API

**Acceptance:** Can fetch all 9,850 stocks in <30 sec, cache persists

---

### Phase 3: Strategy Engine (Indicators & Strategies)

- [x] **3.1** Create `core/indicators.py` - CORRECT implementations
  - [x] 3.1.1 `rsi(closes, period)` - Wilder's smoothing
  - [x] 3.1.2 `ema(values, period)` - Exponential MA
  - [x] 3.1.3 `sma(values, period)` - Simple MA
  - [x] 3.1.4 `macd(closes, fast, slow, signal)` - **EMA signal line**
  - [x] 3.1.5 `bollinger_bands(closes, period, std)` - Upper/Middle/Lower
  - [x] 3.1.6 `keltner_channels(closes, highs, lows, period, mult)` - EMA ± ATR
  - [x] 3.1.7 `atr(highs, lows, closes, period)` - True Range
  - [x] 3.1.8 `vwap(highs, lows, closes, volumes)` - Volume weighted
  - [x] 3.1.9 `adx(highs, lows, closes, period)` - **Smoothed DX**
- [ ] **3.2** Unit tests for all indicators against known values
- [x] **3.3** Create `strategies/base.py` - Strategy interface
  - [x] 3.3.1 `on_bar()` → Optional[Signal]
  - [x] 3.3.2 `reset()` - clear state between symbols
  - [x] 3.3.3 Symbol-isolated state (no contamination)
- [ ] **3.4** Create `strategies/connors_rsi.py`
  - [ ] 3.4.1 Entry: RSI(2) < 5, Close > 200 MA
  - [ ] 3.4.2 Exit: RSI(2) > 60 **OR** Close > 5 MA
  - [ ] 3.4.3 Stop: 3%
- [ ] **3.5** Create `strategies/cumulative_rsi.py`
  - [ ] 3.5.1 Entry: Sum of RSI(2) over 2 bars < 10
  - [ ] 3.5.2 Exit: Cumulative RSI > 65
  - [ ] 3.5.3 Stop: 3%
  - [ ] 3.5.4 **Fix:** Recalculate fresh each bar, no state
- [ ] **3.6** Create `strategies/vwap_rsi.py`
  - [ ] 3.6.1 Entry: Price < VWAP, RSI < 35
  - [ ] 3.6.2 Exit: Price > VWAP **OR** RSI > 55
  - [ ] 3.6.3 Stop: 1.5%
  - [ ] 3.6.4 **Fix:** Reset VWAP daily
- [ ] **3.7** Create `strategies/keltner_rsi.py`
  - [ ] 3.7.1 Entry: Price < Lower KC, RSI < 30
  - [ ] 3.7.2 Exit: Price > Middle KC **OR** RSI > 50
  - [ ] 3.7.3 Stop: 2%
- [ ] **3.8** Create `strategies/bb_rsi.py`
  - [ ] 3.8.1 Entry: Price < Lower BB, RSI < 30
  - [ ] 3.8.2 Exit: Price > Middle BB **OR** RSI > 50
  - [ ] 3.8.3 Stop: 2%
  - [ ] 3.8.4 **Fix:** Simple percentage stop, no complex calculation
- [ ] **3.9** Unit tests for each strategy

**Acceptance:** All strategies produce signals, no state contamination

---

### Phase 4: Backtest Engine (FIXED)

- [ ] **4.1** Create `backtest/engine.py` - Corrected implementation
  - [ ] 4.1.1 **Fix:** Deduct capital on entry, return proceeds on exit
  - [ ] 4.1.2 **Fix:** Gap handling - exit at bar.open if gap through stop/TP
  - [ ] 4.1.3 **Fix:** Same-bar SL/TP - check which hit first based on bar.open
  - [ ] 4.1.4 Track equity at every bar (including unrealized)
- [ ] **4.2** Create `backtest/data_loader.py`
  - [ ] 4.2.1 Load from `alpaca_historical.db` (116M bars)
  - [ ] 4.2.2 Filter by symbol, date range
  - [ ] 4.2.3 Load SPY for market regime filter
- [ ] **4.3** Create `backtest/metrics.py`
  - [ ] 4.3.1 Win rate
  - [ ] 4.3.2 Profit factor
  - [ ] 4.3.3 Sharpe ratio (annualized)
  - [ ] 4.3.4 Max drawdown (bar-by-bar)
  - [ ] 4.3.5 Average win/loss
- [ ] **4.4** Run backtest on all 5 strategies
- [ ] **4.5** Compare results to previous (inflated) numbers

**Acceptance:** Backtest results are realistic, capital tracked correctly

---

### Phase 5: Execution Layer (Alpaca Integration)

- [x] **5.1** Create `execution/alpaca.py`
  - [x] 5.1.1 Initialize with API keys from .env
  - [x] 5.1.2 `get_account()` - balance, buying power
  - [x] 5.1.3 `get_positions()` - current holdings
  - [x] 5.1.4 `submit_order()` - market order with SL/TP
  - [x] 5.1.5 `close_position()` - market sell
  - [x] 5.1.6 Error handling
- [ ] **5.2** Create `execution/paper.py` - Paper trading wrapper
  - [ ] 5.2.1 Log all orders
  - [ ] 5.2.2 Track P&L
- [ ] **5.3** Integration test with Alpaca paper account

**Acceptance:** Can place and close orders on Alpaca paper

---

### Phase 6: Orchestration (Main Loop)

- [ ] **6.1** Create `main.py` - Trading loop
  - [ ] 6.1.1 Market hours detection (9:30 AM - 4:00 PM ET)
  - [ ] 6.1.2 Pre-market startup (9:15 AM) - verify systems
  - [ ] 6.1.3 5-minute cycle loop
  - [ ] 6.1.4 Fetch bulk data from VV7
  - [ ] 6.1.5 Run all strategies on all stocks
  - [ ] 6.1.6 Rank signals by strength
  - [ ] 6.1.7 Execute top N signals (within limits)
  - [ ] 6.1.8 Check exits for open positions
  - [ ] 6.1.9 Log activity
  - [ ] 6.1.10 Graceful shutdown at market close
- [ ] **6.2** Create logging system
  - [ ] 6.2.1 File logging (logs/trading.log)
  - [ ] 6.2.2 Structured JSON for future dashboard
- [ ] **6.3** Add auto-restart on crash
- [ ] **6.4** Full integration test

**Acceptance:** Bot runs autonomously during market hours

---

### Phase 7: Monitoring & Alerts (Future)

- [ ] **7.1** Discord webhook notifications
- [ ] **7.2** Daily P&L summary email
- [ ] **7.3** Web dashboard (FastAPI + React)

---

## Key Fixes from Original Codebase

| Original Bug | Fix Location | Solution |
|--------------|--------------|----------|
| Capital not deducted | `core/position.py` | Deduct on open, return proceeds on close |
| Gap handling wrong | `backtest/engine.py` | Exit at bar.open if gap through level |
| MACD signal = SMA | `core/indicators.py` | Use EMA for signal line |
| State contamination | `strategies/base.py` | Reset state between symbols |
| ADX returns DX | `core/indicators.py` | Smooth DX to get ADX |
| VWAP not reset | `strategies/vwap_rsi.py` | Reset at each new day |
| BB stop negative | `strategies/bb_rsi.py` | Simple percentage stop |

---

## Success Criteria

Before going live:
- [ ] All 5 strategies backtested on 200+ symbols
- [ ] Win rate > 60% on at least 3 strategies
- [ ] Profit factor > 1.5 on at least 3 strategies
- [ ] Max drawdown < 20% on all strategies
- [ ] 1 week paper trading without errors
- [ ] Capital tracking verified against Alpaca account

---

## File Checklist

```
C:\Users\User\Documents\AI\trading_bot\
├── [x] SCOPE.md              ← This document
├── [ ] README.md
├── [x] requirements.txt
├── [x] config.py
├── [ ] main.py
├── data/
│   ├── [x] __init__.py
│   ├── [x] models.py
│   ├── [x] vv7_client.py
│   └── [x] cache.py
├── core/
│   ├── [x] __init__.py
│   ├── [x] indicators.py
│   ├── [x] position.py
│   └── [x] risk.py
├── strategies/
│   ├── [x] __init__.py
│   ├── [x] base.py
│   ├── [ ] connors_rsi.py
│   ├── [ ] cumulative_rsi.py
│   ├── [ ] vwap_rsi.py
│   ├── [ ] keltner_rsi.py
│   └── [ ] bb_rsi.py
├── execution/
│   ├── [x] __init__.py
│   ├── [x] alpaca.py
│   └── [ ] paper.py
├── backtest/
│   ├── [x] __init__.py
│   ├── [ ] engine.py
│   ├── [ ] data_loader.py
│   └── [ ] metrics.py
├── tests/
│   ├── [x] __init__.py
│   ├── [ ] test_indicators.py
│   ├── [ ] test_position.py
│   ├── [ ] test_strategies.py
│   └── [ ] test_backtest.py
└── logs/
    └── [x] .gitkeep
```

---

## Development Workflow

1. Pick next unchecked task
2. Implement
3. Write/run tests
4. Mark complete in this doc
5. Commit with task number
6. Repeat

**Start:** Task 1.1 - Create project folder structure
