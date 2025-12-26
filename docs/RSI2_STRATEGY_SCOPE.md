# RSI(2) Intraday Trading Strategy

## Scope Document & Development Checklist

**Created:** 2025-12-26
**Status:** Planning
**Target:** Replace ConnorsRSI strategy with simple RSI(2) oversold/overbought strategy

---

## 1. Overview

### 1.1 Project Goals

Replace the current ConnorsRSI-based entry/exit logic with a simple RSI(2) mean reversion strategy:
- **Entry:** RSI(2) < 15 (oversold)
- **Exit:** RSI(2) > 70 (overbought)
- Based on Larry Connors' research showing 75-83% win rate on daily data

### 1.2 Current State

| Component | Current Implementation |
|-----------|----------------------|
| Entry Signal | CRSI <= 10 (ConnorsRSI composite) |
| Exit Signal | Close > SMA5 (price-based) |
| Win Rate | ~30% (CRSI designed for daily bars) |
| Data Source | VV7 `indicators.crsi` column |
| Accounts | Dual-mode: SAFE (with stops) + CLASSIC (no stops) |

### 1.3 Target State

| Component | New Implementation |
|-----------|-------------------|
| Entry Signal | RSI(2) < 15 (oversold) |
| Exit Signal | RSI(2) > 70 (overbought) |
| Expected Win Rate | TBD (testing on 5-min data) |
| Data Source | VV7 `indicators.rsi2` (NEW column) |
| Accounts | Unchanged (SAFE + CLASSIC) |

### 1.4 Key Changes

1. **VV7 Database:** Add RSI(2) calculation - currently only RSI(14) exists
2. **Entry Logic:** RSI(2) < 15 instead of CRSI <= 10
3. **Exit Logic:** RSI(2) > 70 instead of Close > SMA5
4. **Symmetry:** Both entry AND exit use the same indicator

### 1.5 Requirements

1. RSI(2) column must be added to VV7SimpleBridge
2. Bot must query `rsi2` instead of `crsi`
3. Dual-account mode (SAFE/CLASSIC) continues working
4. Trade journal logs RSI(2) values

---

## 2. Architecture

### 2.1 Data Flow

```
VV7 Sync (every 5 min)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  VV7SimpleBridge (C#)                               │
│  ├── Fetch 1-min bars from VectorVest               │
│  ├── Calculate indicators (47 existing)             │
│  └── Calculate RSI(2) (NEW)                         │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  SQLite Database (intraday.db)                      │
│  └── indicators table                               │
│       ├── rsi: 14-period RSI (existing)             │
│       ├── crsi: ConnorsRSI (existing, unused)       │
│       └── rsi2: 2-period RSI (NEW)                  │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Trading Bot (Python)                               │
│  ├── find_entries(): rsi2 < 15                      │
│  ├── check_exits(): rsi2 > 70                       │
│  └── execute trades via Alpaca API                  │
└─────────────────────────────────────────────────────┘
```

### 2.2 File Structure

```
VV7SimpleBridge/
└── VV7SimpleBridge.cs      # Add rsi2 column + UpdateRSI2() method

trading_bot/
├── config.py               # Add ENTRY_RSI2=15, EXIT_RSI2=70
├── connors_bot.py          # Update entry/exit logic
├── data/
│   └── indicators_db.py    # Add rsi2 query methods
└── logs/
    └── trade_journal_*.csv # Change crsi column to rsi2
```

### 2.3 RSI(2) vs RSI(14) Calculation

RSI(2) uses identical formula to RSI(14), just with period=2:

```
RSI = 100 - (100 / (1 + RS))
RS = Average Gain (2 periods) / Average Loss (2 periods)
```

**Why 2 periods?**
- More sensitive to short-term price changes
- Reaches extreme values (<15 or >70) more frequently
- Designed for mean reversion: oversold bounces, overbought pullbacks

---

## 3. Strategy Rules

### 3.1 Entry Conditions

```python
entry_signal = (
    rsi2 < ENTRY_RSI2 and      # RSI(2) < 15 (oversold)
    close > sma200 and          # Price above 200 MA (uptrend filter)
    volume >= MIN_VOLUME and    # Liquidity filter
    close >= MIN_PRICE          # No penny stocks
)
```

### 3.2 Exit Conditions

```python
# SAFE Mode
exit_signal = (
    rsi2 > EXIT_RSI2 or        # RSI(2) > 70 (overbought)
    current_price <= stop_loss  # 3% stop loss hit
)

# CLASSIC Mode (no stops)
exit_signal = (
    rsi2 > EXIT_RSI2           # RSI(2) > 70 (overbought)
)
```

### 3.3 Position Sizing

No change from current implementation:
- 10% of account equity per position
- Max 10 positions (SAFE) / 7 positions (CLASSIC)

---

## 4. Development Phases

### Phase 1: VV7SimpleBridge Updates (C#)

Add RSI(2) calculation to the database.

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 1.1 | Add `rsi2 REAL` column to indicators table schema | Column exists in schema definition |
| [ ] 1.2 | Create `UpdateRSI2()` method using Wilder's smoothing | Method calculates RSI with period=2 |
| [ ] 1.3 | Call `UpdateRSI2()` in Phase 5 indicator sequence | RSI2 updates each sync cycle |
| [ ] 1.4 | Rebuild VV7SimpleBridge DLL | DLL compiles without errors |
| [ ] 1.5 | Test RSI2 column populates correctly | Query shows rsi2 values 0-100 |

**File:** `C:/Users/User/Documents/AI/VV7/VV7SimpleBridge/VV7SimpleBridge.cs`

**Schema Change (line ~8668):**
```csharp
// Add after 'rsi REAL,'
rsi2 REAL,
```

**New Method:**
```csharp
private static void UpdateRSI2(System.Data.SQLite.SQLiteConnection conn)
{
    // Same algorithm as RSI(14) but with period=2
    // Uses Wilder's Smoothing: α = 1/period = 1/2 = 0.5
    string sql = @"
        WITH price_changes AS (
            SELECT symbol,
                   close - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp) as change
            FROM bars_1min
        ),
        gains_losses AS (
            SELECT symbol,
                   CASE WHEN change > 0 THEN change ELSE 0 END as gain,
                   CASE WHEN change < 0 THEN ABS(change) ELSE 0 END as loss
            FROM price_changes
            WHERE change IS NOT NULL
        ),
        -- Get last 2 periods
        recent AS (
            SELECT symbol, gain, loss,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY rowid DESC) as rn
            FROM gains_losses
        ),
        averages AS (
            SELECT symbol,
                   AVG(gain) as avg_gain,
                   AVG(loss) as avg_loss
            FROM recent
            WHERE rn <= 2
            GROUP BY symbol
            HAVING COUNT(*) = 2
        )
        UPDATE indicators
        SET rsi2 = CASE
            WHEN a.avg_loss = 0 THEN 100
            WHEN a.avg_gain = 0 THEN 0
            ELSE 100 - (100 / (1 + (a.avg_gain / a.avg_loss)))
        END
        FROM averages a
        WHERE indicators.symbol = a.symbol;
    ";
    conn.Execute(sql);
    Log("UpdateRSI2: Complete");
}
```

---

### Phase 2: Trading Bot Database Layer

Update Python code to query RSI(2).

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 2.1 | Add `ENTRY_RSI2=15` and `EXIT_RSI2=70` to config.py | Constants importable |
| [ ] 2.2 | Add `get_rsi2_entry_candidates()` to indicators_db.py | Returns symbols with rsi2 < threshold |
| [ ] 2.3 | Update `get_position_data()` to include rsi2 | Position data includes rsi2 value |

**File:** `config.py`

```python
# RSI(2) strategy parameters
ENTRY_RSI2 = 15   # Enter when RSI(2) < 15 (oversold)
EXIT_RSI2 = 70    # Exit when RSI(2) > 70 (overbought)
```

**File:** `data/indicators_db.py`

```python
def get_rsi2_entry_candidates(
    self,
    max_rsi2: float = 15,
    min_volume: int = MIN_VOLUME,
    min_price: float = MIN_PRICE,
    limit: int = 20
) -> List[Dict]:
    """Find stocks with RSI(2) < threshold (oversold)."""
    query = """
        SELECT symbol, close, rsi2, sma5, sma200, atr, volume
        FROM indicators
        WHERE rsi2 IS NOT NULL
          AND rsi2 > 0
          AND rsi2 <= ?
          AND volume >= ?
          AND close >= ?
          AND close > sma200
        ORDER BY rsi2 ASC
        LIMIT ?
    """
    # ... implementation
```

---

### Phase 3: Trading Bot Entry/Exit Logic

Update connors_bot.py to use RSI(2) signals.

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 3.1 | Update `find_entries()` to use RSI(2) logic | Entries trigger on rsi2 < 15 |
| [ ] 3.2 | Update `check_exits()` to use RSI(2) > 70 exit | Exits trigger on rsi2 > 70 |
| [ ] 3.3 | Update `execute_entry()` logging for RSI(2) | Logs show RSI2 values |
| [ ] 3.4 | Update trade journal CSV for rsi2 column | CSV has rsi2 instead of crsi |

**File:** `connors_bot.py`

**find_entries() change:**
```python
# OLD:
candidates = self.db.get_entry_candidates(max_crsi=ENTRY_CRSI, ...)

# NEW:
candidates = self.db.get_rsi2_entry_candidates(max_rsi2=ENTRY_RSI2, ...)
```

**check_exits() change:**
```python
# OLD (CLASSIC mode):
if current_price > sma5:
    exit_reason = "sma5_exit"

# NEW (CLASSIC mode):
if rsi2 > EXIT_RSI2:
    exit_reason = "rsi2_exit"
```

---

### Phase 4: Integration & Cleanup

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 4.1 | Update startup message and cycle summary | Shows "RSI(2) < 15 / > 70" |
| [ ] 4.2 | Remove unused CRSI code and imports | No references to ENTRY_CRSI |

**Startup message change:**
```python
# OLD:
f"Strategy: Entry CRSI <= {ENTRY_CRSI}, Exit Close > SMA5"

# NEW:
f"Strategy: Entry RSI(2) < {ENTRY_RSI2}, Exit RSI(2) > {EXIT_RSI2}"
```

---

### Phase 5: Documentation & Commit

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 5.1 | Update CLAUDE.md documentation | Strategy section reflects RSI(2) |
| [ ] 5.2 | Commit all changes with detailed message | Clean commit history |

---

## 5. Checklist Summary

### Phase 1: VV7SimpleBridge (C#)
- [ ] 1.1 Add `rsi2 REAL` column to indicators table schema
- [ ] 1.2 Create `UpdateRSI2()` method
- [ ] 1.3 Call `UpdateRSI2()` in Phase 5 indicator sequence
- [ ] 1.4 Rebuild VV7SimpleBridge DLL
- [ ] 1.5 Test RSI2 column populates correctly

### Phase 2: Trading Bot Database Layer
- [ ] 2.1 Add `ENTRY_RSI2=15` and `EXIT_RSI2=70` to config.py
- [ ] 2.2 Add `get_rsi2_entry_candidates()` to indicators_db.py
- [ ] 2.3 Update `get_position_data()` to include rsi2

### Phase 3: Trading Bot Entry/Exit Logic
- [ ] 3.1 Update `find_entries()` to use RSI(2) logic
- [ ] 3.2 Update `check_exits()` to use RSI(2) > 70 exit
- [ ] 3.3 Update `execute_entry()` logging for RSI(2)
- [ ] 3.4 Update trade journal CSV for rsi2 column

### Phase 4: Integration & Cleanup
- [ ] 4.1 Update startup message and cycle summary
- [ ] 4.2 Remove unused CRSI code and imports

### Phase 5: Documentation & Commit
- [ ] 5.1 Update CLAUDE.md documentation
- [ ] 5.2 Commit all changes with detailed message

---

## 6. Rollback Plan

If RSI(2) strategy underperforms:

1. The `crsi` column remains in the database (not deleted)
2. Revert bot code to use CRSI logic
3. Update config to use `ENTRY_CRSI` instead of `ENTRY_RSI2`

No database schema changes needed for rollback.

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Win Rate | >50% | Trade journal analysis |
| Profit Factor | >1.5 | Total wins / Total losses |
| Trades per Day | 5-20 | Cycle logs |
| Bot Uptime | >99% | No crashes during market hours |

---

## 8. Comparison: RSI(2) vs CRSI vs ROC+HA

| Aspect | RSI(2) | CRSI (current) | ROC+HA (rejected) |
|--------|--------|----------------|-------------------|
| Entry Logic | RSI(2) < 15 | CRSI < 10 | ROC cross up |
| Exit Logic | RSI(2) > 70 | Close > SMA5 | ROC cross down |
| Complexity | Simple | Medium | Complex |
| State Required | None | None | File persistence |
| VV7 Changes | Add 1 column | None | None |
| Daily Win Rate | 75-83% | 65-75% | 55% |
| Intraday Win Rate | TBD | ~30% | TBD |

---

*Document generated by Claude Code - 2025-12-26*
