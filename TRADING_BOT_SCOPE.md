# Connors RSI Paper Trading Bot - Project Scope

## STATUS: READY TO BUILD

---

## Overview

### Goal
A streamlined paper trading bot that reads pre-calculated technical indicators from a SQLite database and executes trades via Alpaca's paper trading API using the Connors RSI(2) mean-reversion strategy.

### Key Principles
1. **Simple** - No indicator calculations, no historical bars, no complex strategy plugins
2. **Read and Trade** - Query database for signals, execute via Alpaca
3. **Pre-calculated Data** - VV7 already computed all 47 indicators
4. **Single Strategy** - Connors RSI(2) only

### Data Source
- **Database:** `%LOCALAPPDATA%/VV7SimpleBridge/intraday.db`
- **Table:** `indicators` (9,847 symbols, 47 columns)
- **Updated by:** VV7 `intraday/main.py` running separately

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      connors_bot.py                         │
│                    (Main Orchestrator)                      │
│         - Market hours check                                │
│         - 5-minute trading cycles                           │
│         - Entry/exit logic                                  │
│         - Position tracking                                 │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌─────────────────────┐                 ┌─────────────────────┐
│  indicators_db.py   │                 │  alpaca_client.py   │
│    (Data Layer)     │                 │ (Execution Layer)   │
│  - Read indicators  │                 │  - Submit orders    │
│  - Find candidates  │                 │  - Get positions    │
│  - Check exits      │                 │  - Account info     │
└─────────────────────┘                 └─────────────────────┘
          │                                       │
          ▼                                       ▼
┌─────────────────────┐                 ┌─────────────────────┐
│    intraday.db      │                 │   Alpaca Paper      │
│  (VV7 SQLite)       │                 │     Account         │
└─────────────────────┘                 └─────────────────────┘
```

### File Structure
```
trading_bot/
├── config.py              # Configuration & constants
├── connors_bot.py         # Main bot orchestrator
├── data/
│   └── indicators_db.py   # SQLite database reader
├── execution/
│   └── alpaca_client.py   # Alpaca API wrapper
├── logs/
│   └── trading.log        # Trade logs
└── TRADING_BOT_SCOPE.md   # This document
```

---

## Trading Strategy

### Connors RSI(2) Mean Reversion

| Aspect | Rule |
|--------|------|
| **Entry** | RSI(2) < 5 AND close > SMA(200) |
| **Exit** | RSI(2) > 60 OR close > SMA(5) OR stop loss hit |
| **Stop Loss** | 3% below entry price |
| **Position Size** | 10% of capital per trade |
| **Max Positions** | 5 concurrent |

### Why This Works
- RSI(2) < 5 = extremely oversold (short-term)
- Close > SMA(200) = long-term uptrend intact
- Mean reversion: oversold stocks in uptrends tend to bounce
- Historical win rate: 70-80% (Larry Connors research)

---

## Database Schema

### Table: `indicators` (47 columns)

**Primary Key:** `symbol`, `timestamp`

| Column | Type | Used For |
|--------|------|----------|
| `symbol` | TEXT | Stock ticker |
| `timestamp` | INTEGER | Unix timestamp |
| `close` | REAL | Current price |
| `rsi` | REAL | **Entry/Exit signal** |
| `sma5` | REAL | **Exit signal** |
| `sma200` | REAL | **Trend filter** |
| `atr` | REAL | Stop loss calculation |
| `volume` | INTEGER | Liquidity filter |

*Plus 40 more indicators available if needed*

---

## Configuration

### Trading Parameters
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `CAPITAL` | $100,000 | Starting paper balance |
| `POSITION_SIZE_PCT` | 10% | Per-trade allocation |
| `MAX_POSITIONS` | 5 | Concurrent limit |
| `STOP_LOSS_PCT` | 3% | Risk per trade |
| `ENTRY_RSI` | 5 | RSI threshold for buy |
| `EXIT_RSI` | 60 | RSI threshold for sell |
| `MIN_VOLUME` | 100,000 | Liquidity filter |
| `MIN_PRICE` | 5.00 | Avoid penny stocks |

### Market Hours
| Parameter | Value |
|-----------|-------|
| `MARKET_OPEN` | 9:30 AM ET |
| `MARKET_CLOSE` | 4:00 PM ET |
| `CYCLE_INTERVAL` | 5 minutes |

### Paths
| Parameter | Value |
|-----------|-------|
| `INTRADAY_DB` | `%LOCALAPPDATA%/VV7SimpleBridge/intraday.db` |
| `LOG_FILE` | `logs/trading.log` |

---

## Development Phases

### Phase 1: Configuration & Data Layer

#### 1.1 Create config.py
- [ ] Define `INTRADAY_DB_PATH` with proper Windows path expansion
- [ ] Define trading parameters (capital, position size, max positions)
- [ ] Define Connors RSI thresholds (entry_rsi=5, exit_rsi=60)
- [ ] Define market hours (9:30 AM - 4:00 PM ET)
- [ ] Load Alpaca credentials from environment variables

**Acceptance:** Config imports without errors, paths resolve correctly

#### 1.2 Create data/indicators_db.py - Class Setup
- [ ] Create `IndicatorsDB` class
- [ ] Implement `__init__` with path to intraday.db
- [ ] Implement `_get_conn()` with busy timeout and row factory
- [ ] Implement `is_available()` to check DB exists and has data

**Acceptance:** Can connect to database, `is_available()` returns True

#### 1.3 Add get_entry_candidates() Method
- [ ] Query: `SELECT * FROM indicators WHERE rsi < 5 AND close > sma200`
- [ ] Add filters: `volume >= 100000`, `close >= 5.00`
- [ ] Order by RSI ascending (most oversold first)
- [ ] Limit to 20 candidates
- [ ] Return list of dicts with symbol, close, rsi, sma200, atr

**Acceptance:** Returns list of oversold stocks when RSI < 5 exist

#### 1.4 Add Helper Methods
- [ ] `get_position_data(symbols)` - batch lookup for open positions
- [ ] `get_indicator(symbol)` - single symbol lookup
- [ ] `get_stats()` - record count, latest timestamp

**Acceptance:** All methods return expected data types

---

### Phase 2: Execution Layer

#### 2.1 Create execution/alpaca_client.py - Class Setup
- [ ] Create `AlpacaClient` class
- [ ] Implement `__init__` loading credentials from environment
- [ ] Initialize `TradingClient` from alpaca-py
- [ ] Add paper trading flag

**Acceptance:** Client initializes without errors

#### 2.2 Add Account Methods
- [ ] `get_account()` - returns equity, cash, buying_power
- [ ] `get_positions()` - returns list of open positions
- [ ] `get_position(symbol)` - single position lookup
- [ ] `is_market_open()` - check market hours via Alpaca clock

**Acceptance:** Account data retrieves correctly, positions list works

#### 2.3 Add Order Methods
- [ ] `submit_buy(symbol, qty)` - market buy order
- [ ] `submit_sell(symbol, qty)` - market sell order
- [ ] `close_position(symbol)` - close entire position
- [ ] Add error handling and logging for all orders

**Acceptance:** Can submit paper orders, orders appear in Alpaca dashboard

---

### Phase 3: Bot Core

#### 3.1 Create connors_bot.py - Class Setup
- [ ] Create `ConnorsBot` class
- [ ] Implement `__init__` initializing IndicatorsDB and AlpacaClient
- [ ] Add `positions` dict to track open positions with entry prices
- [ ] Implement `startup_checks()` - verify DB and Alpaca connectivity

**Acceptance:** Bot initializes, startup checks pass

#### 3.2 Add Market Hours & Position Sync
- [ ] `is_market_hours()` - check if within 9:30 AM - 4:00 PM ET
- [ ] `sync_positions()` - load existing positions from Alpaca
- [ ] Track entry_price and stop_loss for each position

**Acceptance:** Market hours check works, positions sync from Alpaca

#### 3.3 Implement find_entries()
- [ ] Call `db.get_entry_candidates()`
- [ ] Filter out symbols we already own
- [ ] Check available slots (max_positions - current_positions)
- [ ] Calculate position size: `(capital * 0.10) / close`
- [ ] Calculate stop_loss: `entry_price * 0.97`
- [ ] Return list of entry signals

**Acceptance:** Returns valid entry signals when candidates exist

#### 3.4 Implement check_exits()
- [ ] Get current indicator data for open positions
- [ ] Check exit conditions for each:
  - RSI > 60 (signal exit)
  - Close > SMA5 (trend exit)
  - Close < stop_loss (risk exit)
- [ ] Return list of exit signals with reason

**Acceptance:** Correctly identifies positions that should exit

#### 3.5 Implement run_cycle()
- [ ] Sync positions from Alpaca
- [ ] Call `check_exits()` and execute sells
- [ ] Call `find_entries()` and execute buys
- [ ] Log cycle summary (equity, positions, signals)

**Acceptance:** Full cycle runs without errors, logs output

#### 3.6 Implement run() Main Loop
- [ ] Run startup checks
- [ ] Wait for market open if before hours
- [ ] Loop: run_cycle() every 5 minutes during market hours
- [ ] Handle Ctrl+C gracefully
- [ ] Log daily summary at market close

**Acceptance:** Bot runs continuously during market hours, stops cleanly

---

## Data Flow

### Entry Flow (Every 5 Minutes)
```
1. Query indicators table
   └── WHERE rsi < 5 AND close > sma200 AND volume >= 100000

2. Filter candidates
   └── Remove already-owned symbols
   └── Limit to available slots

3. For each candidate:
   └── Calculate shares: (capital × 10%) / price
   └── Calculate stop: price × 0.97
   └── Submit buy order to Alpaca
   └── Track position locally
```

### Exit Flow (Every 5 Minutes)
```
1. Get indicator data for open positions

2. For each position, check:
   └── RSI > 60? → Exit (signal)
   └── Close > SMA5? → Exit (trend)
   └── Close < stop_loss? → Exit (risk)

3. If exit triggered:
   └── Submit sell order to Alpaca
   └── Remove from local tracking
   └── Log P&L
```

---

## Risk Management

| Control | Implementation |
|---------|----------------|
| **Position Limit** | Max 5 concurrent positions |
| **Position Size** | 10% of capital per trade |
| **Stop Loss** | 3% below entry price |
| **Liquidity Filter** | Min 100K volume |
| **Price Filter** | Min $5.00 (no penny stocks) |

---

## Logging

### Log Format
```
2024-01-15 10:35:00 INFO  Cycle 12 | Equity: $100,234 | Positions: 3/5
2024-01-15 10:35:01 INFO  ENTRY AAPL | RSI: 4.2 | Price: $182.50 | Shares: 54
2024-01-15 10:40:00 INFO  EXIT  MSFT | RSI: 62.1 | P&L: +$127.50 | Reason: signal
```

### Daily Summary
```
================== DAILY SUMMARY ==================
Date: 2024-01-15
Trades: 8 (6 wins, 2 losses)
Win Rate: 75%
Daily P&L: +$342.50
Final Equity: $100,342.50
===================================================
```

---

## Dependencies

```
alpaca-py>=0.13.0      # Paper trading API
python-dotenv>=1.0.0   # Environment variables
```

### Environment Variables
```bash
ALPACA_API_KEY=<paper-trading-key>
ALPACA_SECRET_KEY=<paper-trading-secret>
```

---

## Commands

```bash
# Run the bot
python connors_bot.py

# Check logs
tail -f logs/trading.log
```

---

## Task Checklist

### Phase 1: Configuration & Data Layer
- [ ] 1.1 Create config.py with paths and parameters
- [ ] 1.2 Create data/indicators_db.py with connection setup
- [ ] 1.3 Add get_entry_candidates() method
- [ ] 1.4 Add helper methods (get_position_data, get_indicator)

### Phase 2: Execution Layer
- [ ] 2.1 Create execution/alpaca_client.py class setup
- [ ] 2.2 Add account methods (get_account, get_positions, is_market_open)
- [ ] 2.3 Add order methods (submit_buy, submit_sell, close_position)

### Phase 3: Bot Core
- [ ] 3.1 Create connors_bot.py with __init__ and startup_checks
- [ ] 3.2 Add is_market_hours() and sync_positions()
- [ ] 3.3 Implement find_entries()
- [ ] 3.4 Implement check_exits()
- [ ] 3.5 Implement run_cycle()
- [ ] 3.6 Implement run() main loop

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Bot runs during market hours | Yes |
| Reads from indicators table | Yes |
| Executes paper trades on Alpaca | Yes |
| Respects position limits | Max 5 |
| Stop losses tracked | 3% |
| Logs all trades | Yes |
| Graceful shutdown | Ctrl+C |

---

## Next Step

**Start with Task 1.1:** Create `config.py` with database path and trading parameters.
