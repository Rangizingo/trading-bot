# Trading Bot Development Scope

## STATUS: IN DEVELOPMENT

**Goal:** Modular paper trading bot using VV7 intraday data + Alpaca execution

**Data Source:** `intraday/main.py` provides 40 real-time indicators every 5 min

---

## Overview

Build a modular trading bot that:
1. Reads indicator data from VV7 intraday SQLite database
2. Applies pluggable trading strategies (add/remove without breaking bot)
3. Executes paper trades via Alpaca API
4. Logs all trades for analysis

**Key Principle:** Strategies are interchangeable plugins. The bot framework handles execution, position management, and logging. Strategies only define entry/exit signals.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        trading_bot/                              │
├─────────────────────────────────────────────────────────────────┤
│  main.py              │ Entry point, scheduler                   │
│  config.py            │ Settings, API keys, parameters           │
├─────────────────────────────────────────────────────────────────┤
│  CORE MODULES                                                    │
│  ├── data_provider.py │ Read indicators from intraday.db         │
│  ├── signal.py        │ Signal dataclass (BUY/SELL/HOLD)         │
│  ├── position_manager.py │ Track positions, P&L                  │
│  ├── order_executor.py│ Submit orders to Alpaca                  │
│  └── trade_journal.py │ Log trades to SQLite                     │
├─────────────────────────────────────────────────────────────────┤
│  STRATEGIES (Pluggable)                                          │
│  └── strategies/                                                 │
│      ├── base_strategy.py     │ Abstract base class              │
│      ├── connors_rsi2.py      │ RSI(2) < 5 entry                 │
│      ├── keltner_rsi.py       │ Keltner + RSI                    │
│      ├── vwap_rsi.py          │ VWAP + RSI                       │
│      ├── bb_rsi_extreme.py    │ Bollinger + RSI                  │
│      └── ... (13 total)                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
intraday.db (40 indicators, 9,847 symbols)
    │
    ▼
DataProvider.get_indicators(symbol) → dict of 40 values
    │
    ▼
Strategy.analyze(indicators) → Signal(BUY/SELL/HOLD, confidence)
    │
    ▼
PositionManager.process_signal(signal)
    │
    ├── If BUY: Check max positions, calculate size
    ├── If SELL: Check if position exists
    └── If HOLD: Do nothing
    │
    ▼
OrderExecutor.execute(order) → Alpaca API
    │
    ▼
TradeJournal.log(trade)
```

---

## Phase 1: Core Framework

### 1.1 Configuration
- [ ] Create `config.py` with settings dataclass
  - Alpaca API credentials (from .env)
  - Max positions (default: 5)
  - Position size % (default: 10%)
  - Stop loss % (default: 2%)
  - Take profit % (default: 5%)
  - Intraday DB path
  - Enabled strategies list

### 1.2 Data Provider
- [ ] Create `data_provider.py`
  - `get_all_symbols()` → List[str]
  - `get_indicators(symbol)` → Dict[str, float] (40 indicators)
  - `get_latest_bar(symbol)` → OHLCV
  - Cache connection to intraday.db

### 1.3 Signal Model
- [ ] Create `signal.py`
  - `SignalType` enum: BUY, SELL, HOLD
  - `Signal` dataclass: symbol, signal_type, strategy_name, confidence, timestamp, metadata

### 1.4 Trade Journal
- [ ] Create `trade_journal.py`
  - SQLite database for trade history
  - `log_trade(trade)` → insert record
  - `get_trades(symbol=None, strategy=None)` → List[Trade]
  - `get_daily_pnl()` → float
  - `get_strategy_stats()` → Dict per strategy

---

## Phase 2: Strategy Framework

### 2.1 Base Strategy
- [ ] Create `strategies/base_strategy.py`
  - Abstract class with:
    - `name: str` property
    - `required_indicators: List[str]` property
    - `analyze(indicators: Dict) -> Signal` abstract method
    - `should_exit(indicators: Dict, entry_price: float) -> bool`
  - Common helper methods

### 2.2 Strategy Registry
- [ ] Create `strategies/__init__.py`
  - Auto-discover strategies in folder
  - `get_strategy(name)` → Strategy instance
  - `get_all_strategies()` → List[Strategy]
  - `get_enabled_strategies(config)` → List[Strategy]

### 2.3 Implement 5 Initial Strategies
- [ ] `connors_rsi2.py` - RSI(2) < 5, exit RSI > 70
- [ ] `keltner_rsi.py` - Price < Lower Keltner + RSI < 30
- [ ] `vwap_rsi.py` - Price < VWAP + RSI < 30
- [ ] `bb_rsi_extreme.py` - Price < Lower BB + RSI < 20
- [ ] `triple_ema_macd.py` - EMA alignment + MACD cross

---

## Phase 3: Execution Layer

### 3.1 Alpaca Client
- [ ] Create `alpaca_client.py`
  - Initialize with paper trading credentials
  - `get_account()` → Account info, buying power
  - `get_positions()` → List[Position]
  - `submit_order(symbol, qty, side, type)` → Order
  - `get_order_status(order_id)` → Order status
  - `cancel_order(order_id)`
  - `is_market_open()` → bool

### 3.2 Position Manager
- [ ] Create `position_manager.py`
  - Track current positions (sync with Alpaca)
  - Calculate position size based on config
  - Check max position limit
  - Calculate unrealized P&L
  - Apply stop loss / take profit rules
  - `sync_positions()` - load from Alpaca
  - `can_open_position()` → bool
  - `get_position(symbol)` → Position or None
  - `calculate_size(symbol, price)` → int shares

### 3.3 Order Executor
- [ ] Create `order_executor.py`
  - Convert Signal to Order
  - Execute via AlpacaClient
  - Handle order failures gracefully
  - Log all orders to journal
  - `execute_signal(signal)` → Order result
  - `execute_exit(symbol, reason)` → Order result

---

## Phase 4: Main Loop

### 4.1 Bot Runner
- [ ] Create `main.py`
  - Load config
  - Initialize all components
  - Market hours check (9:30 AM - 4:00 PM ET)
  - Main loop:
    1. Wait for next 5-min interval
    2. Refresh indicators from DB
    3. For each enabled strategy:
       - Scan all symbols for signals
       - Rank signals by confidence
    4. Execute top N buy signals (up to max positions)
    5. Check exits for current positions
    6. Log stats
  - Graceful shutdown on Ctrl+C

### 4.2 CLI Interface
- [ ] Add argparse options
  - `--dry-run` - log signals but don't trade
  - `--live` - execute real paper trades
  - `--strategies` - comma-separated list
  - `--max-positions` - override config
  - `--verbose` - detailed logging

---

## Phase 5: Risk Management

### 5.1 Stop Loss / Take Profit
- [ ] Implement in `position_manager.py`
  - Check price vs entry price each cycle
  - Auto-exit if stop loss hit
  - Auto-exit if take profit hit
  - Log reason for exit

### 5.2 Daily Limits
- [ ] Add circuit breakers
  - Max daily loss $ (stop trading for day)
  - Max trades per day
  - Min time between trades (cool down)

### 5.3 Position Limits
- [ ] Sector/correlation limits
  - Max 2 positions in same sector
  - Avoid highly correlated stocks

---

## Phase 6: Remaining Strategies

### 6.1 Add 8 More Strategies
- [ ] `cumulative_rsi.py`
- [ ] `volume_filtered_rsi2.py`
- [ ] `same_day_rsi2.py`
- [ ] `rsi25_scaling.py`
- [ ] `stoch_rsi_cross.py`
- [ ] `orb_vwap.py`
- [ ] `cumulative_rsi_market_regime.py`
- [ ] `keltner_rsi_adx.py`

---

## Phase 7: Monitoring & Reporting

### 7.1 Console Dashboard
- [ ] Real-time display during trading
  - Current positions + P&L
  - Signals generated this cycle
  - Daily stats

### 7.2 Daily Report
- [ ] End-of-day summary
  - Trades executed
  - Win/loss ratio
  - P&L by strategy
  - Best/worst trades

---

## File Checklist

### Core Files
- [ ] `trading_bot/__init__.py`
- [ ] `trading_bot/config.py`
- [ ] `trading_bot/data_provider.py`
- [ ] `trading_bot/signal.py`
- [ ] `trading_bot/trade_journal.py`
- [ ] `trading_bot/alpaca_client.py`
- [ ] `trading_bot/position_manager.py`
- [ ] `trading_bot/order_executor.py`
- [ ] `trading_bot/main.py`

### Strategy Files
- [ ] `trading_bot/strategies/__init__.py`
- [ ] `trading_bot/strategies/base_strategy.py`
- [ ] `trading_bot/strategies/connors_rsi2.py`
- [ ] `trading_bot/strategies/keltner_rsi.py`
- [ ] `trading_bot/strategies/vwap_rsi.py`
- [ ] `trading_bot/strategies/bb_rsi_extreme.py`
- [ ] `trading_bot/strategies/triple_ema_macd.py`
- [ ] (Phase 6: 8 more strategies)

### Database
- [ ] `trading_bot/trading_bot.db` - SQLite trade journal

---

## Dependencies

```
alpaca-trade-api>=3.0.0
python-dotenv>=1.0.0
```

---

## Environment Variables

```bash
# .env file (already exists)
ALPACA_API_KEY=<paper-trading-key>
ALPACA_SECRET_KEY=<paper-trading-secret>
```

---

## Commands

```bash
# Dry run (log signals, no trades)
python trading_bot/main.py --dry-run

# Live paper trading
python trading_bot/main.py --live

# Specific strategies only
python trading_bot/main.py --live --strategies connors_rsi2,keltner_rsi

# Verbose logging
python trading_bot/main.py --live -v
```

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Bot runs continuously during market hours | ✓ |
| Executes paper trades on Alpaca | ✓ |
| Strategies are plug-and-play | ✓ |
| All trades logged to SQLite | ✓ |
| Stop loss / take profit working | ✓ |
| Win rate tracking per strategy | ✓ |

---

## Next Step

Start with **Phase 1.1: Configuration** - create the config module.
