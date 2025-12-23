# ConnorsRSI (CRSI) Implementation Scope

## Overview

This document outlines the complete implementation of ConnorsRSI (CRSI) indicators in the VV7 trading system. ConnorsRSI is a composite momentum oscillator developed by Larry Connors that combines three components into a single value ranging from 0-100.

### Goals
1. Add 5 new ConnorsRSI datapoints to VV7SimpleBridge.cs
2. Update database schema with 5 new columns
3. Update trading bot to use CRSI for entry signals
4. Maintain all existing 40 indicators unchanged

### ConnorsRSI Formula
```
CRSI(3,2,100) = [RSI(3) + StreakRSI(2) + PercentRank(100)] / 3
```

### Three Components

| Component | Column Name | Description |
|-----------|-------------|-------------|
| RSI(3) | `crsi_rsi3` | 3-period RSI of closing prices |
| StreakRSI(2) | `crsi_streak_rsi` | 2-period RSI of up/down streak length |
| PercentRank(100) | `crsi_percent_rank` | Percentile rank of today's price change vs last 100 days |
| **Final CRSI** | `crsi` | Average of the three components |

### Supporting Column

| Column | Name | Description |
|--------|------|-------------|
| Streak | `crsi_streak` | Consecutive up/down day count (intermediate calculation) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     VV7SimpleBridge.cs                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  SyncIntradayIndicatorsSql()                            │    │
│  │    ├── StreamBarsToSqlite()     → bars_1min table       │    │
│  │    ├── CreateIntradaySchema()   → indicators table      │    │
│  │    └── CalculateAndUpdateIndicators()                   │    │
│  │          ├── UpdateSMAIndicators()                      │    │
│  │          ├── UpdateEMAIndicators()                      │    │
│  │          ├── UpdateRSI()           (existing RSI-14)    │    │
│  │          ├── ... (other indicators)                     │    │
│  │          ├── UpdateCRSI_RSI3()       ← NEW              │    │
│  │          ├── UpdateCRSI_Streak()     ← NEW              │    │
│  │          ├── UpdateCRSI_StreakRSI()  ← NEW              │    │
│  │          ├── UpdateCRSI_PercentRank()← NEW              │    │
│  │          └── UpdateCRSI()            ← NEW              │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     intraday.db                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  indicators table (45 columns after change)             │    │
│  │    - symbol, timestamp, open, high, low, close, volume  │    │
│  │    - rsi (RSI-14, unchanged)                            │    │
│  │    - sma5, sma200, etc. (unchanged)                     │    │
│  │    - crsi_rsi3       ← NEW                              │    │
│  │    - crsi_streak     ← NEW                              │    │
│  │    - crsi_streak_rsi ← NEW                              │    │
│  │    - crsi_percent_rank ← NEW                            │    │
│  │    - crsi            ← NEW                              │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Trading Bot                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  indicators_db.py                                       │    │
│  │    - get_entry_candidates(): WHERE crsi <= 10           │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  config.py                                              │    │
│  │    - ENTRY_CRSI = 10                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  connors_bot.py                                         │    │
│  │    - Uses CRSI for entry decisions                      │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Development Phases

### Phase 1: Database Schema (VV7SimpleBridge.cs)
Add 5 new columns to the indicators table schema.

### Phase 2: CRSI Calculations (VV7SimpleBridge.cs)
Implement 5 new SQL calculation functions.

### Phase 3: Sync Integration (VV7SimpleBridge.cs)
Call new functions from CalculateAndUpdateIndicators().

### Phase 4: Trading Bot Updates (Python)
Update bot to use CRSI instead of RSI for entries.

### Phase 5: Testing & Validation
Verify calculations and bot behavior.

---

## Task Checklist

### Phase 1: Database Schema

#### 1.1 Add CRSI Columns to CreateIntradaySchema()
- **File**: `C:\Users\User\Documents\AI\VV7\VV7SimpleBridge\VV7SimpleBridge.cs`
- **Location**: `CreateIntradaySchema()` method, line ~8654
- **Current Schema** (line 8654-8669):
```csharp
CREATE TABLE IF NOT EXISTS indicators (
    symbol TEXT PRIMARY KEY,
    timestamp INTEGER,
    open REAL, high REAL, low REAL, close REAL, volume INTEGER,
    rsi REAL, macd REAL, macd_signal REAL, macd_histogram REAL,
    // ... existing columns ...
    updated_at INTEGER
) WITHOUT ROWID;
```
- **Change**: Add 5 new columns after existing columns, before `updated_at`:
```csharp
    // ... existing columns ...
    vwap REAL,
    crsi_rsi3 REAL,
    crsi_streak INTEGER,
    crsi_streak_rsi REAL,
    crsi_percent_rank REAL,
    crsi REAL,
    updated_at INTEGER
```
- **Acceptance**: Schema creates without errors, new columns exist

**Steps**:
- [ ] 1.1.1 Locate CreateIntradaySchema() in VV7SimpleBridge.cs (line ~8634)
- [ ] 1.1.2 Find the indicators table CREATE statement (line ~8654)
- [ ] 1.1.3 Add `crsi_rsi3 REAL,` after `vwap REAL,`
- [ ] 1.1.4 Add `crsi_streak INTEGER,` after `crsi_rsi3`
- [ ] 1.1.5 Add `crsi_streak_rsi REAL,` after `crsi_streak`
- [ ] 1.1.6 Add `crsi_percent_rank REAL,` after `crsi_streak_rsi`
- [ ] 1.1.7 Add `crsi REAL,` after `crsi_percent_rank`
- [ ] 1.1.8 Verify schema syntax is correct (commas, no trailing comma before closing paren)

---

### Phase 2: CRSI Calculation Functions

#### 2.1 Create UpdateCRSI_RSI3() Function
- **File**: `VV7SimpleBridge.cs`
- **Location**: After existing `UpdateADX()` function (line ~9290)
- **Purpose**: Calculate 3-period RSI of closing prices
- **Formula**: Standard RSI formula with 3-period lookback

**SQL Logic**:
```sql
UPDATE indicators SET crsi_rsi3 = (
    SELECT CASE
        WHEN avg_gain = 0 AND avg_loss = 0 THEN 50
        WHEN avg_loss = 0 THEN 100
        ELSE 100 - (100 / (1 + avg_gain / avg_loss))
    END
    FROM (
        SELECT
            AVG(CASE WHEN change > 0 THEN change ELSE 0 END) as avg_gain,
            AVG(CASE WHEN change < 0 THEN -change ELSE 0 END) as avg_loss
        FROM (
            SELECT close - LAG(close) OVER (ORDER BY timestamp) as change
            FROM bars_1min
            WHERE symbol = indicators.symbol
            AND timestamp >= (SELECT MAX(timestamp) - 24000 FROM bars_1min WHERE symbol = indicators.symbol)
            ORDER BY timestamp DESC LIMIT 4  -- 4 prices = 3 changes = RSI(3)
        )
        WHERE change IS NOT NULL
    )
)
```

**Steps**:
- [ ] 2.1.1 Create new function `private static void UpdateCRSI_RSI3(System.Data.SQLite.SQLiteConnection conn)`
- [ ] 2.1.2 Implement SQL with LIMIT 4 (for 3-period RSI)
- [ ] 2.1.3 Handle edge cases: avg_gain=0 AND avg_loss=0 → return 50
- [ ] 2.1.4 Handle edge case: avg_loss=0 → return 100
- [ ] 2.1.5 Add logging: `Log("UpdateCRSI_RSI3: Complete");`
- [ ] 2.1.6 Verify SQL syntax compiles

---

#### 2.2 Create UpdateCRSI_Streak() Function
- **File**: `VV7SimpleBridge.cs`
- **Location**: After `UpdateCRSI_RSI3()`
- **Purpose**: Calculate consecutive up/down day count
- **Logic**:
  - Count consecutive days where close > previous close (positive streak)
  - Count consecutive days where close < previous close (negative streak)
  - Reset to 0 if no change

**SQL Logic**:
```sql
UPDATE indicators SET crsi_streak = (
    SELECT
        CASE
            WHEN streak_direction = 1 THEN streak_length
            WHEN streak_direction = -1 THEN -streak_length
            ELSE 0
        END
    FROM (
        SELECT
            CASE
                WHEN close > prev_close THEN 1
                WHEN close < prev_close THEN -1
                ELSE 0
            END as streak_direction,
            -- Count consecutive same-direction moves
            (SELECT COUNT(*) FROM (
                SELECT
                    close,
                    LAG(close) OVER (ORDER BY timestamp) as pc,
                    ROW_NUMBER() OVER (ORDER BY timestamp DESC) as rn
                FROM bars_1min
                WHERE symbol = indicators.symbol
                AND timestamp >= (SELECT MAX(timestamp) - 24000 FROM bars_1min WHERE symbol = indicators.symbol)
            ) sub
            WHERE rn <= 20  -- Look back up to 20 bars
            AND (
                (close > pc AND (SELECT close FROM bars_1min b WHERE b.symbol = indicators.symbol ORDER BY timestamp DESC LIMIT 1) >
                 (SELECT close FROM bars_1min b WHERE b.symbol = indicators.symbol ORDER BY timestamp DESC LIMIT 1 OFFSET 1))
                OR
                (close < pc AND (SELECT close FROM bars_1min b WHERE b.symbol = indicators.symbol ORDER BY timestamp DESC LIMIT 1) <
                 (SELECT close FROM bars_1min b WHERE b.symbol = indicators.symbol ORDER BY timestamp DESC LIMIT 1 OFFSET 1))
            )
            ) as streak_length
        FROM (
            SELECT
                close,
                LAG(close) OVER (ORDER BY timestamp) as prev_close
            FROM bars_1min
            WHERE symbol = indicators.symbol
            ORDER BY timestamp DESC LIMIT 2
        )
        WHERE prev_close IS NOT NULL
        LIMIT 1
    )
)
```

**Simplified Approach** (recommended):
```sql
-- Calculate streak by iterating through recent bars
UPDATE indicators SET crsi_streak = (
    WITH recent_bars AS (
        SELECT
            close,
            LAG(close) OVER (ORDER BY timestamp) as prev_close,
            ROW_NUMBER() OVER (ORDER BY timestamp DESC) as rn
        FROM bars_1min
        WHERE symbol = indicators.symbol
        AND timestamp >= (SELECT MAX(timestamp) - 24000 FROM bars_1min WHERE symbol = indicators.symbol)
    ),
    directions AS (
        SELECT
            rn,
            CASE
                WHEN close > prev_close THEN 1
                WHEN close < prev_close THEN -1
                ELSE 0
            END as dir
        FROM recent_bars
        WHERE prev_close IS NOT NULL
    ),
    first_dir AS (
        SELECT dir FROM directions WHERE rn = 1
    )
    SELECT
        CASE
            WHEN (SELECT dir FROM first_dir) = 0 THEN 0
            ELSE (SELECT dir FROM first_dir) * (
                SELECT COUNT(*) FROM directions d
                WHERE d.rn <= (
                    SELECT COALESCE(MIN(rn) - 1, 20) FROM directions
                    WHERE dir != (SELECT dir FROM first_dir) OR dir = 0
                )
            )
        END
)
```

**Steps**:
- [ ] 2.2.1 Create function `private static void UpdateCRSI_Streak(System.Data.SQLite.SQLiteConnection conn)`
- [ ] 2.2.2 Implement logic to detect current direction (up/down/flat)
- [ ] 2.2.3 Count consecutive bars in same direction
- [ ] 2.2.4 Return positive count for up streaks, negative for down streaks
- [ ] 2.2.5 Handle edge case: no change = streak of 0
- [ ] 2.2.6 Add logging: `Log("UpdateCRSI_Streak: Complete");`

---

#### 2.3 Create UpdateCRSI_StreakRSI() Function
- **File**: `VV7SimpleBridge.cs`
- **Location**: After `UpdateCRSI_Streak()`
- **Purpose**: Calculate 2-period RSI of the streak values
- **Dependency**: Requires `crsi_streak` to be calculated first
- **Note**: This is complex because we need historical streak values

**Implementation Challenge**:
The StreakRSI requires RSI calculation on streak values over time. Since we only store the current streak, we need to:
1. Calculate streak for the last N bars
2. Apply RSI(2) formula to those streak values

**SQL Logic** (simplified approach using recent price changes):
```sql
UPDATE indicators SET crsi_streak_rsi = (
    WITH streak_values AS (
        SELECT
            timestamp,
            -- Calculate streak at each point (simplified: use sign of price change as proxy)
            CASE
                WHEN close > LAG(close) OVER (ORDER BY timestamp) THEN 1
                WHEN close < LAG(close) OVER (ORDER BY timestamp) THEN -1
                ELSE 0
            END as streak_val
        FROM bars_1min
        WHERE symbol = indicators.symbol
        AND timestamp >= (SELECT MAX(timestamp) - 24000 FROM bars_1min WHERE symbol = indicators.symbol)
        ORDER BY timestamp DESC
        LIMIT 4  -- Need 4 values for 3 changes for RSI(2) calculation
    ),
    streak_changes AS (
        SELECT streak_val - LAG(streak_val) OVER (ORDER BY timestamp) as change
        FROM streak_values
    )
    SELECT CASE
        WHEN avg_gain = 0 AND avg_loss = 0 THEN 50
        WHEN avg_loss = 0 THEN 100
        ELSE 100 - (100 / (1 + avg_gain / avg_loss))
    END
    FROM (
        SELECT
            AVG(CASE WHEN change > 0 THEN change ELSE 0 END) as avg_gain,
            AVG(CASE WHEN change < 0 THEN -change ELSE 0 END) as avg_loss
        FROM streak_changes
        WHERE change IS NOT NULL
    )
)
```

**Steps**:
- [ ] 2.3.1 Create function `private static void UpdateCRSI_StreakRSI(System.Data.SQLite.SQLiteConnection conn)`
- [ ] 2.3.2 Calculate streak values for recent bars
- [ ] 2.3.3 Apply RSI(2) formula to streak changes
- [ ] 2.3.4 Handle edge cases (no movement = 50)
- [ ] 2.3.5 Add logging: `Log("UpdateCRSI_StreakRSI: Complete");`

---

#### 2.4 Create UpdateCRSI_PercentRank() Function
- **File**: `VV7SimpleBridge.cs`
- **Location**: After `UpdateCRSI_StreakRSI()`
- **Purpose**: Calculate percentile rank of today's price change vs last 100 periods
- **Formula**: (Count of values below current) / Total values * 100

**SQL Logic**:
```sql
UPDATE indicators SET crsi_percent_rank = (
    WITH price_changes AS (
        SELECT
            (close - LAG(close) OVER (ORDER BY timestamp)) / LAG(close) OVER (ORDER BY timestamp) * 100 as pct_change,
            ROW_NUMBER() OVER (ORDER BY timestamp DESC) as rn
        FROM bars_1min
        WHERE symbol = indicators.symbol
        AND timestamp >= (SELECT MAX(timestamp) - 72000 FROM bars_1min WHERE symbol = indicators.symbol)
    ),
    current_change AS (
        SELECT pct_change FROM price_changes WHERE rn = 1
    ),
    historical_changes AS (
        SELECT pct_change FROM price_changes WHERE rn BETWEEN 2 AND 101 AND pct_change IS NOT NULL
    )
    SELECT
        CAST(
            (SELECT COUNT(*) FROM historical_changes WHERE pct_change < (SELECT pct_change FROM current_change))
            AS REAL
        ) /
        CAST(
            (SELECT COUNT(*) FROM historical_changes)
            AS REAL
        ) * 100
)
```

**Steps**:
- [ ] 2.4.1 Create function `private static void UpdateCRSI_PercentRank(System.Data.SQLite.SQLiteConnection conn)`
- [ ] 2.4.2 Calculate current bar's percentage price change
- [ ] 2.4.3 Get last 100 bars' percentage price changes
- [ ] 2.4.4 Count how many historical changes are less than current
- [ ] 2.4.5 Calculate percentile: (count below / total) * 100
- [ ] 2.4.6 Handle edge case: no historical data = 50
- [ ] 2.4.7 Add logging: `Log("UpdateCRSI_PercentRank: Complete");`

---

#### 2.5 Create UpdateCRSI() Function
- **File**: `VV7SimpleBridge.cs`
- **Location**: After `UpdateCRSI_PercentRank()`
- **Purpose**: Calculate final CRSI as average of three components
- **Dependency**: Requires crsi_rsi3, crsi_streak_rsi, crsi_percent_rank

**SQL Logic**:
```sql
UPDATE indicators SET crsi = (
    SELECT (COALESCE(crsi_rsi3, 50) + COALESCE(crsi_streak_rsi, 50) + COALESCE(crsi_percent_rank, 50)) / 3.0
)
WHERE crsi_rsi3 IS NOT NULL
   OR crsi_streak_rsi IS NOT NULL
   OR crsi_percent_rank IS NOT NULL
```

**Steps**:
- [ ] 2.5.1 Create function `private static void UpdateCRSI(System.Data.SQLite.SQLiteConnection conn)`
- [ ] 2.5.2 Calculate average of three components
- [ ] 2.5.3 Use COALESCE to handle NULL values (default to 50)
- [ ] 2.5.4 Add logging: `Log("UpdateCRSI: Complete");`

---

### Phase 3: Sync Integration

#### 3.1 Add CRSI Phase to CalculateAndUpdateIndicators()
- **File**: `VV7SimpleBridge.cs`
- **Location**: `CalculateAndUpdateIndicators()` method, line ~8803
- **Current End** (line ~8880):
```csharp
// PHASE 5: ADX
Log($"[INDICATORS] Phase 5: ADX...");
UpdateADX(conn);

Log($"CalculateAndUpdateIndicators: All 40 indicators calculated for {updated} symbols");
return updated;
```
- **Change**: Add Phase 6 for CRSI after ADX

**Steps**:
- [ ] 3.1.1 Locate CalculateAndUpdateIndicators() function (line ~8803)
- [ ] 3.1.2 Find end of Phase 5 (UpdateADX call, line ~8880)
- [ ] 3.1.3 Add new Phase 6 comment: `// PHASE 6: ConnorsRSI (CRSI)`
- [ ] 3.1.4 Add log statement: `Log($"[INDICATORS] Phase 6: ConnorsRSI...");`
- [ ] 3.1.5 Add call to `UpdateCRSI_RSI3(conn);`
- [ ] 3.1.6 Add call to `UpdateCRSI_Streak(conn);`
- [ ] 3.1.7 Add call to `UpdateCRSI_StreakRSI(conn);`
- [ ] 3.1.8 Add call to `UpdateCRSI_PercentRank(conn);`
- [ ] 3.1.9 Add call to `UpdateCRSI(conn);`
- [ ] 3.1.10 Update log message: `"All 45 indicators calculated"` (was 40)

---

### Phase 4: Trading Bot Updates

#### 4.1 Update config.py
- **File**: `C:\Users\User\Documents\AI\trading_bot\config.py`
- **Current** (line ~57):
```python
ENTRY_RSI = 10  # Enter when RSI drops below this level
```
- **Change**: Add new CRSI constant (keep RSI for reference)

**Steps**:
- [ ] 4.1.1 Add `ENTRY_CRSI = 10` after ENTRY_RSI line
- [ ] 4.1.2 Update comment to explain CRSI usage
- [ ] 4.1.3 Keep ENTRY_RSI for backwards compatibility

---

#### 4.2 Update indicators_db.py - get_entry_candidates()
- **File**: `C:\Users\User\Documents\AI\trading_bot\data\indicators_db.py`
- **Location**: `get_entry_candidates()` method, line ~154
- **Current Query** (line ~187-212):
```python
query = """
    SELECT symbol, close, rsi, sma5, sma200, atr, volume
    FROM indicators
    WHERE
        rsi IS NOT NULL
        ...
        AND rsi > 0
        AND rsi <= ?
        ...
"""
```
- **Change**: Replace `rsi` with `crsi` in entry logic

**Steps**:
- [ ] 4.2.1 Locate get_entry_candidates() method (line ~154)
- [ ] 4.2.2 Update SELECT to include `crsi` column
- [ ] 4.2.3 Change `rsi IS NOT NULL` to `crsi IS NOT NULL`
- [ ] 4.2.4 Change `rsi > 0` to `crsi > 0`
- [ ] 4.2.5 Change `rsi <= ?` to `crsi <= ?`
- [ ] 4.2.6 Update docstring to mention CRSI instead of RSI
- [ ] 4.2.7 Update parameter name: `max_rsi` to `max_crsi`
- [ ] 4.2.8 Update log message to say "CRSI" instead of "RSI"

---

#### 4.3 Update connors_bot.py
- **File**: `C:\Users\User\Documents\AI\trading_bot\connors_bot.py`
- **Purpose**: Update entry logic to use CRSI

**Steps**:
- [ ] 4.3.1 Import ENTRY_CRSI from config (or update existing import)
- [ ] 4.3.2 Update find_entries() to pass ENTRY_CRSI to get_entry_candidates()
- [ ] 4.3.3 Update log messages to say "CRSI" instead of "RSI"
- [ ] 4.3.4 Update any entry signal dictionaries to use 'crsi' key

---

### Phase 5: Testing & Validation

#### 5.1 Build and Deploy VV7
- **Steps**:
- [ ] 5.1.1 Build VV7SimpleBridge.dll (Release mode)
- [ ] 5.1.2 Run start_vv7_robust.ps1 to deploy
- [ ] 5.1.3 Verify no build errors

---

#### 5.2 Verify Database Schema
- **Steps**:
- [ ] 5.2.1 Run a sync to create new schema
- [ ] 5.2.2 Query: `PRAGMA table_info(indicators);`
- [ ] 5.2.3 Verify 5 new columns exist: crsi_rsi3, crsi_streak, crsi_streak_rsi, crsi_percent_rank, crsi
- [ ] 5.2.4 Verify column types are correct (REAL for all except crsi_streak INTEGER)

---

#### 5.3 Verify CRSI Calculations
- **Steps**:
- [ ] 5.3.1 Run full sync: `/api/intraday/sync` with fullSync=true
- [ ] 5.3.2 Query sample data: `SELECT symbol, crsi_rsi3, crsi_streak, crsi_streak_rsi, crsi_percent_rank, crsi FROM indicators LIMIT 10;`
- [ ] 5.3.3 Verify crsi_rsi3 values are in range 0-100
- [ ] 5.3.4 Verify crsi_streak values are integers (positive, negative, or zero)
- [ ] 5.3.5 Verify crsi_streak_rsi values are in range 0-100
- [ ] 5.3.6 Verify crsi_percent_rank values are in range 0-100
- [ ] 5.3.7 Verify crsi is approximately average of three components
- [ ] 5.3.8 Spot check: Manual calculation for 1-2 symbols

---

#### 5.4 Verify Trading Bot
- **Steps**:
- [ ] 5.4.1 Run connors_bot.py
- [ ] 5.4.2 Verify it queries for CRSI candidates
- [ ] 5.4.3 Verify log messages show "CRSI" not "RSI"
- [ ] 5.4.4 Verify entry candidates are found (if any meet criteria)

---

#### 5.5 Verify Existing Indicators Unchanged
- **Steps**:
- [ ] 5.5.1 Query existing RSI: `SELECT symbol, rsi FROM indicators WHERE rsi IS NOT NULL LIMIT 5;`
- [ ] 5.5.2 Verify RSI values are still RSI(14), not changed
- [ ] 5.5.3 Verify SMA5, SMA200 values are unchanged
- [ ] 5.5.4 Verify all 40 original indicators still populate

---

## File Change Summary

| File | Changes |
|------|---------|
| `VV7SimpleBridge.cs` | Add 5 columns to schema, add 5 UpdateCRSI_*() functions, add Phase 6 to sync |
| `config.py` | Add ENTRY_CRSI constant |
| `indicators_db.py` | Update get_entry_candidates() to use crsi |
| `connors_bot.py` | Update imports and log messages |

---

## SQL Function Reference

### UpdateCRSI_RSI3
- **Period**: 3
- **Input**: Last 4 closing prices (3 changes)
- **Output**: RSI value 0-100 (50 if no movement)

### UpdateCRSI_Streak
- **Input**: Recent closing prices
- **Output**: Integer (-N to +N, 0 if flat)
- **Logic**: Count consecutive up/down days

### UpdateCRSI_StreakRSI
- **Period**: 2
- **Input**: Recent streak values
- **Output**: RSI value 0-100 (50 if no movement)

### UpdateCRSI_PercentRank
- **Lookback**: 100 periods
- **Input**: Current price change vs historical changes
- **Output**: Percentile 0-100

### UpdateCRSI
- **Input**: crsi_rsi3, crsi_streak_rsi, crsi_percent_rank
- **Output**: Average of three components

---

## Completion Criteria

All items checked = Ready for production

**Total Tasks**: 47 individual steps
**Phases**: 5

---

## Workflow

```
1. Complete task 1.1.1
2. Test if applicable
3. Mark 1.1.1 complete
4. Move to 1.1.2
5. Repeat until all tasks complete
6. Run /pushy to commit and push
```

---

## Risk Mitigation

1. **Existing indicators unchanged**: All new code is additive only
2. **Backwards compatible**: RSI(14) still available, bot just uses new CRSI
3. **Graceful degradation**: If CRSI is NULL, bot falls back to not entering
4. **No endpoint changes**: Same sync API, just more calculations

---

## References

- [StockCharts - ConnorsRSI](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/connorsrsi)
- [Larry Connors - Short-Term Trading Strategies That Work](https://www.amazon.com/Short-Term-Trading-Strategies-That/dp/0981923909)
- Original CRSI Formula: CRSI(3,2,100) = [RSI(3) + RSI(Streak,2) + PercentRank(100)] / 3
