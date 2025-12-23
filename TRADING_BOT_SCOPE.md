# Connors RSI Paper Trading Bot - Project Scope

## STATUS: PHASE 4-5 IN PROGRESS (Robustness Improvements)

---

## Overview

### Goal
A streamlined paper trading bot that reads pre-calculated technical indicators from a SQLite database and executes trades via Alpaca's paper trading API using the Connors RSI(2) mean-reversion strategy.

### Key Principles
1. **Simple** - No indicator calculations, no historical bars, no complex strategy plugins
2. **Read and Trade** - Query database for signals, execute via Alpaca
3. **Pre-calculated Data** - VV7 already computed all 47 indicators
4. **Single Strategy** - Connors RSI(2) only
5. **Robust** - Handles restarts, gaps, and uses real-time stop protection

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
│         - Position validation on restart                    │
│         - Real-time stop protection via Alpaca              │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    indicators_db.py                         │
│                      (Data Layer)                           │
│  - Read indicators    - Find entry candidates               │
│  - Check exits        - Validate positions                  │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│    intraday.db (VV7 SQLite - 9,847 symbols, 47 indicators)  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    alpaca_client.py                         │
│                   (Execution Layer)                         │
│  - Bracket orders (buy + stop loss)                         │
│  - Real-time stop monitoring by Alpaca                      │
│  - Cancel orders    - Close positions                       │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│              Alpaca Paper Trading Account                   │
│         (Monitors stops 24/7, executes in real-time)        │
└─────────────────────────────────────────────────────────────┘
```

### File Structure
```
trading_bot/
├── config.py              # Configuration & constants
├── connors_bot.py         # Main bot orchestrator
├── data/
│   ├── __init__.py
│   └── indicators_db.py   # SQLite database reader
├── execution/
│   ├── __init__.py
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
| **Exit (Signal)** | RSI(2) > 60 |
| **Exit (Trend)** | close > SMA(5) |
| **Exit (Risk)** | Stop loss hit (3% below entry) |
| **Stop Loss** | 3% below entry price (enforced by Alpaca real-time) |
| **Position Size** | 10% of capital per trade |
| **Max Positions** | 5 concurrent |

### Why This Works
- RSI(2) < 5 = extremely oversold (short-term)
- Close > SMA(200) = long-term uptrend intact
- Mean reversion: oversold stocks in uptrends tend to bounce
- Historical win rate: 70-80% (Larry Connors research)

---

## Robustness Features

### Position Validation (On Restart)
When bot starts/restarts, it validates ALL existing positions:

| Check | Condition | Action |
|-------|-----------|--------|
| **Trend Broken** | close < SMA200 | Exit immediately |
| **Stop Hit** | close <= stop_loss | Exit immediately |
| **RSI Exit** | RSI > 60 | Exit immediately |
| **Valid** | All checks pass | Continue holding |

### Real-Time Stop Protection
- **Bracket Orders**: Entry submits buy + stop loss together
- **Alpaca Monitors 24/7**: Not dependent on bot polling
- **Instant Execution**: Stop triggers in real-time, even if bot is off
- **Order Tracking**: Stop order IDs tracked for cancellation

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
| `sma200` | REAL | **Trend filter + validation** |
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

### Phase 1: Configuration & Data Layer [COMPLETED]

#### 1.1 Create config.py
- [x] Define `INTRADAY_DB_PATH` with proper Windows path expansion
- [x] Define trading parameters (capital, position size, max positions)
- [x] Define Connors RSI thresholds (entry_rsi=5, exit_rsi=60)
- [x] Define market hours (9:30 AM - 4:00 PM ET)
- [x] Load Alpaca credentials from environment variables

#### 1.2 Create data/indicators_db.py - Class Setup
- [x] Create `IndicatorsDB` class
- [x] Implement `__init__` with path to intraday.db
- [x] Implement `_get_conn()` with busy timeout and row factory
- [x] Implement `is_available()` to check DB exists and has data

#### 1.3 Add get_entry_candidates() Method
- [x] Query: `SELECT * FROM indicators WHERE rsi < 5 AND close > sma200`
- [x] Add filters: `volume >= 100000`, `close >= 5.00`
- [x] Order by RSI ascending (most oversold first)
- [x] Limit to 20 candidates
- [x] Return list of dicts with symbol, close, rsi, sma200, atr

#### 1.4 Add Helper Methods
- [x] `get_position_data(symbols)` - batch lookup for open positions
- [x] `get_indicator(symbol)` - single symbol lookup
- [x] `get_stats()` - record count, latest timestamp

---

### Phase 2: Execution Layer [COMPLETED]

#### 2.1 Create execution/alpaca_client.py - Class Setup
- [x] Create `AlpacaClient` class
- [x] Implement `__init__` loading credentials from environment
- [x] Initialize `TradingClient` from alpaca-py
- [x] Add paper trading flag

#### 2.2 Add Account Methods
- [x] `get_account()` - returns equity, cash, buying_power
- [x] `get_positions()` - returns list of open positions
- [x] `get_position(symbol)` - single position lookup
- [x] `is_market_open()` - check market hours via Alpaca clock

#### 2.3 Add Order Methods
- [x] `submit_buy(symbol, qty)` - market buy order
- [x] `submit_sell(symbol, qty)` - market sell order
- [x] `close_position(symbol)` - close entire position
- [x] Add error handling and logging for all orders

---

### Phase 3: Bot Core [COMPLETED]

#### 3.1 Create connors_bot.py - Class Setup
- [x] Create `ConnorsBot` class
- [x] Implement `__init__` initializing IndicatorsDB and AlpacaClient
- [x] Add `positions` dict to track open positions with entry prices
- [x] Implement `startup_checks()` - verify DB and Alpaca connectivity

#### 3.2 Add Market Hours & Position Sync
- [x] `is_market_hours()` - check if within 9:30 AM - 4:00 PM ET
- [x] `sync_positions()` - load existing positions from Alpaca
- [x] Track entry_price and stop_loss for each position

#### 3.3 Implement find_entries()
- [x] Call `db.get_entry_candidates()`
- [x] Filter out symbols we already own
- [x] Check available slots (max_positions - current_positions)
- [x] Calculate position size: `(capital * 0.10) / close`
- [x] Calculate stop_loss: `entry_price * 0.97`
- [x] Return list of entry signals

#### 3.4 Implement check_exits()
- [x] Get current indicator data for open positions
- [x] Check exit conditions for each:
  - RSI > 60 (signal exit)
  - Close > SMA5 (trend exit)
  - Close < stop_loss (risk exit)
- [x] Return list of exit signals with reason

#### 3.5 Implement run_cycle()
- [x] Sync positions from Alpaca
- [x] Call `check_exits()` and execute sells
- [x] Call `find_entries()` and execute buys
- [x] Log cycle summary (equity, positions, signals)

#### 3.6 Implement run() Main Loop
- [x] Run startup checks
- [x] Wait for market open if before hours
- [x] Loop: run_cycle() every 5 minutes during market hours
- [x] Handle Ctrl+C gracefully
- [x] Log daily summary at market close

---

### Phase 4: Position Validation (Robustness) [IN PROGRESS]

#### 4.1 Add validate_positions() Method
- [ ] Create `validate_positions()` method in ConnorsBot
- [ ] Get current indicator data for all positions from DB
- [ ] Return list of positions that should be exited with reason

**Acceptance:** Method returns list of invalid positions

#### 4.2 Check Trend Broken (SMA200)
- [ ] For each position, check if `close < sma200`
- [ ] If true, mark for exit with reason "trend_broken"
- [ ] Log: "Position {symbol} below SMA200 - trend broken"

**Acceptance:** Positions below SMA200 flagged for exit

#### 4.3 Check Stop Loss Hit
- [ ] For each position, check if `close <= stop_loss`
- [ ] If true, mark for exit with reason "stop_hit"
- [ ] Log: "Position {symbol} at ${close} hit stop ${stop_loss}"

**Acceptance:** Positions at/below stop flagged for exit

#### 4.4 Check RSI Exit Triggered
- [ ] For each position, check if `rsi > EXIT_RSI` (60)
- [ ] If true, mark for exit with reason "rsi_exit"
- [ ] Log: "Position {symbol} RSI={rsi} triggered exit"

**Acceptance:** Positions with RSI > 60 flagged for exit

#### 4.5 Integrate Validation into Startup
- [ ] Call `sync_positions()` in startup after health checks
- [ ] Call `validate_positions()` after sync
- [ ] Auto-exit all invalid positions before first cycle
- [ ] Log validation summary: "X positions valid, Y positions exited"

**Acceptance:** Invalid positions closed before trading begins

#### 4.6 Add Clear Logging for Validation
- [ ] Log header: "VALIDATING EXISTING POSITIONS"
- [ ] Log each position check result
- [ ] Log summary of exits performed
- [ ] Log final position count after validation

**Acceptance:** Clear visibility into what validation found

---

### Phase 5: Alpaca Real-Time Stop Protection [PENDING]

#### 5.1 Add submit_bracket_order() to AlpacaClient
- [ ] Create method: `submit_bracket_order(symbol, qty, stop_price)`
- [ ] Use Alpaca's bracket order API
- [ ] Submit buy order + stop loss order together
- [ ] Return dict with `order_id` and `stop_order_id`

**Acceptance:** Bracket orders appear in Alpaca dashboard

#### 5.2 Add cancel_order() Method
- [ ] Create method: `cancel_order(order_id)`
- [ ] Cancel pending/open order by ID
- [ ] Return True on success, False on failure
- [ ] Handle "order not found" gracefully

**Acceptance:** Can cancel stop orders before manual exit

#### 5.3 Add get_open_orders() Method
- [ ] Create method: `get_open_orders(symbol=None)`
- [ ] Return list of open/pending orders
- [ ] Filter by symbol if provided
- [ ] Include order type, side, qty, stop_price

**Acceptance:** Can find existing stop orders

#### 5.4 Track stop_order_id in Positions
- [ ] Add `stop_order_id` field to position tracking dict
- [ ] Store stop order ID when bracket order submitted
- [ ] Clear stop order ID when position closed

**Acceptance:** Position dict includes stop_order_id

#### 5.5 Update find_entries() for Bracket Orders
- [ ] Replace `submit_buy()` with `submit_bracket_order()`
- [ ] Calculate stop_price: `entry_price * (1 - STOP_LOSS_PCT)`
- [ ] Store returned `stop_order_id` in positions dict
- [ ] Log: "ENTRY {symbol} with stop @ ${stop_price}"

**Acceptance:** New entries create real-time stops

#### 5.6 Update check_exits() to Cancel Stops
- [ ] Before closing position, get `stop_order_id` from dict
- [ ] Call `cancel_order(stop_order_id)` first
- [ ] Then call `close_position(symbol)`
- [ ] Log: "Cancelled stop order {id} before exit"

**Acceptance:** No orphan stop orders after manual exit

#### 5.7 Update sync_positions() for Alpaca-Executed Stops
- [ ] When position disappears from Alpaca, check why
- [ ] Check if stop order was filled
- [ ] Log: "Stop loss executed by Alpaca for {symbol}"
- [ ] Calculate and log P&L for Alpaca-executed stops

**Acceptance:** Bot knows when Alpaca executed a stop

---

## Data Flow

### Entry Flow (With Bracket Orders)
```
1. Query indicators table
   └── WHERE rsi < 5 AND close > sma200 AND volume >= 100000

2. Filter candidates
   └── Remove already-owned symbols
   └── Limit to available slots

3. For each candidate:
   └── Calculate shares: (equity × 10%) / price
   └── Calculate stop: price × 0.97
   └── Submit BRACKET ORDER to Alpaca:
       ├── BUY {shares} {symbol} @ market
       └── STOP SELL {shares} {symbol} @ {stop_price}
   └── Track position + stop_order_id locally
```

### Exit Flow (Strategy Signal)
```
1. Get indicator data for open positions

2. For each position, check:
   └── RSI > 60? → Exit (signal)
   └── Close > SMA5? → Exit (trend)

3. If exit triggered:
   └── Cancel stop order first (by stop_order_id)
   └── Close position via Alpaca
   └── Remove from local tracking
   └── Log P&L
```

### Exit Flow (Alpaca Stop Triggered)
```
1. Alpaca monitors price 24/7

2. Price hits stop_price:
   └── Alpaca executes sell automatically
   └── Stop order marked as "filled"

3. Next sync_positions() cycle:
   └── Bot sees position gone
   └── Checks stop order status: "filled"
   └── Logs: "Stop executed by Alpaca"
   └── Removes from tracking
```

### Startup Flow (With Validation)
```
1. startup_checks()
   └── Verify DB available
   └── Verify Alpaca connected

2. sync_positions()
   └── Load all positions from Alpaca
   └── Use avg_entry_price for stop calc

3. validate_positions()
   └── Check each position:
       ├── close < sma200? → Invalid (trend broken)
       ├── close <= stop_loss? → Invalid (stop hit)
       └── rsi > 60? → Invalid (exit signal)
   └── Return list of invalid positions

4. Auto-exit invalid positions
   └── Cancel any existing stop orders
   └── Close positions
   └── Log results

5. Start trading cycles
```

---

## Risk Management

| Control | Implementation |
|---------|----------------|
| **Position Limit** | Max 5 concurrent positions |
| **Position Size** | 10% of capital per trade |
| **Stop Loss** | 3% below entry (real-time via Alpaca) |
| **Trend Filter** | Only buy if close > SMA200 |
| **Validation** | Exit if trend breaks (close < SMA200) |
| **Liquidity Filter** | Min 100K volume |
| **Price Filter** | Min $5.00 (no penny stocks) |

---

## Logging

### Log Format
```
2024-01-15 10:30:00 INFO  STARTUP CHECKS
2024-01-15 10:30:01 INFO  Database check: PASSED
2024-01-15 10:30:02 INFO  Alpaca check: PASSED - Equity: $100,000.00
2024-01-15 10:30:03 INFO  VALIDATING EXISTING POSITIONS
2024-01-15 10:30:04 INFO  Position AAPL: VALID (RSI=45, above SMA200)
2024-01-15 10:30:05 INFO  Position MSFT: INVALID - stop hit ($280 <= $282)
2024-01-15 10:30:06 INFO  Exiting MSFT - stop loss hit while offline
2024-01-15 10:30:07 INFO  Validation complete: 1 valid, 1 exited
2024-01-15 10:35:00 INFO  CYCLE #1 - Entry: TSLA x 41 @ $241.00 (stop @ $233.77)
2024-01-15 10:40:00 INFO  CYCLE #2 - Exit: AAPL (RSI=62, reason=signal, P&L=+$127)
```

### Daily Summary
```
================== DAILY SUMMARY ==================
Date: 2024-01-15
Cycles: 78
Trades: 8 (6 wins, 2 losses)
Win Rate: 75%
Stops Executed by Alpaca: 1
Daily P&L: +$342.50
Final Equity: $100,342.50
Open Positions: 2
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

### Phase 1: Configuration & Data Layer [COMPLETED]
- [x] 1.1 Create config.py with paths and parameters
- [x] 1.2 Create data/indicators_db.py with connection setup
- [x] 1.3 Add get_entry_candidates() method
- [x] 1.4 Add helper methods (get_position_data, get_indicator)

### Phase 2: Execution Layer [COMPLETED]
- [x] 2.1 Create execution/alpaca_client.py class setup
- [x] 2.2 Add account methods (get_account, get_positions, is_market_open)
- [x] 2.3 Add order methods (submit_buy, submit_sell, close_position)

### Phase 3: Bot Core [COMPLETED]
- [x] 3.1 Create connors_bot.py with __init__ and startup_checks
- [x] 3.2 Add is_market_hours() and sync_positions()
- [x] 3.3 Implement find_entries()
- [x] 3.4 Implement check_exits()
- [x] 3.5 Implement run_cycle()
- [x] 3.6 Implement run() main loop

### Phase 4: Position Validation [IN PROGRESS]
- [ ] 4.1 Add validate_positions() method
- [ ] 4.2 Check trend broken (close < SMA200)
- [ ] 4.3 Check stop loss hit
- [ ] 4.4 Check RSI exit triggered
- [ ] 4.5 Integrate validation into startup
- [ ] 4.6 Add clear logging for validation

### Phase 5: Alpaca Real-Time Stop Protection [PENDING]
- [ ] 5.1 Add submit_bracket_order() to AlpacaClient
- [ ] 5.2 Add cancel_order() method
- [ ] 5.3 Add get_open_orders() method
- [ ] 5.4 Track stop_order_id in positions dict
- [ ] 5.5 Update find_entries() for bracket orders
- [ ] 5.6 Update check_exits() to cancel stops
- [ ] 5.7 Update sync_positions() for Alpaca-executed stops

---

## Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| Bot runs during market hours | Yes | Done |
| Reads from indicators table | Yes | Done |
| Executes paper trades on Alpaca | Yes | Done |
| Respects position limits | Max 5 | Done |
| Logs all trades | Yes | Done |
| Graceful shutdown | Ctrl+C | Done |
| Validates positions on restart | Yes | Pending |
| Auto-exits invalid positions | Yes | Pending |
| Real-time stop protection | Yes | Pending |
| Handles Alpaca-executed stops | Yes | Pending |

---

## Next Step

**Start with Task 4.1:** Add `validate_positions()` method to ConnorsBot.
