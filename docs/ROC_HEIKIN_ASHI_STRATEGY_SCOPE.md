# ROC + Heikin Ashi Intraday Trading Strategy

## Scope Document & Development Checklist

**Created:** 2025-12-26
**Status:** Planning
**Target:** Replace ConnorsRSI strategy with ROC + Heikin Ashi for higher win rate intraday trading

---

## 1. Overview

### 1.1 Project Goals

Replace the current ConnorsRSI-based entry/exit logic with a ROC (Rate of Change) + Heikin Ashi crossover strategy, which has demonstrated:
- **55% win rate** with **2.7 reward:risk ratio**
- Better performance on 5-minute intraday data
- Reduced false signals through Heikin Ashi smoothing

### 1.2 Current State

| Component | Current Implementation |
|-----------|----------------------|
| Entry Signal | CRSI <= 10 (oversold) |
| Exit Signal | Close > SMA5 (mean reversion) |
| Win Rate | ~30% (strategy designed for daily bars) |
| Data Source | VV7 `indicators` table (52 columns) |
| Accounts | Dual-mode: SAFE (with stops) + CLASSIC (no stops) |

### 1.3 Target State

| Component | New Implementation |
|-----------|-------------------|
| Entry Signal | ROC crosses above 0 on Heikin Ashi |
| Exit Signal | ROC crosses below 0 on Heikin Ashi |
| Expected Win Rate | ~55% with 2.7 R:R |
| Data Source | VV7 `indicators.roc` + calculated HA |
| Accounts | Unchanged (SAFE + CLASSIC) |

### 1.4 Requirements

1. **File-based persistence** for ROC state (survives bot crashes/restarts)
2. **No VV7 modifications** - use existing data
3. **Backward compatible** - option to switch back to CRSI if needed
4. **Dual-account support** - both SAFE and CLASSIC use same signals

---

## 2. Architecture

### 2.1 Data Flow

```
VV7 Sync (every 5 min)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  SQLite Database (intraday.db)                      │
│  ├── bars_1min: Raw 1-min OHLCV bars                │
│  └── indicators: 52 pre-computed indicators         │
│       └── roc: 10-period Rate of Change             │
│       └── open, high, low, close: For HA calc       │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  ROC State Manager (NEW)                            │
│  ├── Load previous ROC values from JSON             │
│  ├── Compare current vs previous ROC                │
│  ├── Detect crossovers (above/below 0)              │
│  └── Save current ROC values to JSON                │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Heikin Ashi Calculator (NEW)                       │
│  ├── Read OHLC from indicators table                │
│  ├── Calculate HA bars on-the-fly                   │
│  └── Return smoothed price data                     │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Trading Bot (MODIFIED)                             │
│  ├── find_entries(): ROC cross up + HA filter       │
│  ├── check_exits(): ROC cross down                  │
│  └── execute trades via Alpaca API                  │
└─────────────────────────────────────────────────────┘
```

### 2.2 File Structure

```
trading_bot/
├── config.py                    # Add ROC strategy parameters
├── connors_bot.py               # Modify entry/exit logic
├── data/
│   ├── indicators_db.py         # Add HA calculation methods
│   └── roc_state.py             # NEW: ROC state persistence
├── logs/
│   └── roc_state.json           # NEW: Persisted ROC values
└── docs/
    └── ROC_HEIKIN_ASHI_STRATEGY_SCOPE.md  # This document
```

### 2.3 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSON for ROC state | Human-readable, easy to debug, sufficient for ~10K symbols |
| Calculate HA on-the-fly | Avoids VV7 modifications, uses existing OHLC data |
| Keep CRSI code (disabled) | Allows quick rollback if needed |
| Single ROC state file | Both accounts share same signals |

---

## 3. Strategy Rules

### 3.1 Entry Conditions

```python
# Entry: ROC crosses above 0 (bullish momentum shift)
entry_signal = (
    current_roc > 0 and          # ROC is now positive
    previous_roc <= 0 and        # ROC was zero or negative
    ha_close > ha_open           # Heikin Ashi confirms bullish (optional filter)
)
```

### 3.2 Exit Conditions

```python
# Exit: ROC crosses below 0 (momentum reversal)
exit_signal = (
    current_roc < 0 and          # ROC is now negative
    previous_roc >= 0            # ROC was zero or positive
)
```

### 3.3 Heikin Ashi Calculation

```python
# Standard Heikin Ashi formulas
ha_close = (open + high + low + close) / 4
ha_open = (previous_ha_open + previous_ha_close) / 2
ha_high = max(high, ha_open, ha_close)
ha_low = min(low, ha_open, ha_close)

# For first bar (no previous HA):
ha_open = (open + close) / 2
```

### 3.4 ROC Reference

The VV7 database already computes ROC with a 10-period lookback:
```python
roc = ((close - close_10_periods_ago) / close_10_periods_ago) * 100
```

---

## 4. Development Phases

### Phase 1: ROC State Persistence Module

Create file-based storage for ROC values to enable crossover detection across cycles.

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 1.1 | Create `data/roc_state.py` module | File exists with proper docstring |
| [ ] 1.2 | Implement `ROCStateManager` class | Class initializes with file path |
| [ ] 1.3 | Implement `load()` method | Returns dict of `{symbol: roc_value}` from JSON |
| [ ] 1.4 | Implement `save()` method | Writes current ROC values to JSON with timestamp |
| [ ] 1.5 | Implement `get_crossovers()` method | Returns list of symbols with ROC cross up/down |
| [ ] 1.6 | Add automatic backup/rotation | Keep last 3 state files for safety |

**File:** `data/roc_state.py`

```python
# Target structure
class ROCStateManager:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.previous_roc: Dict[str, float] = {}

    def load(self) -> Dict[str, float]:
        """Load previous ROC values from JSON file."""
        ...

    def save(self, current_roc: Dict[str, float]) -> None:
        """Save current ROC values to JSON file."""
        ...

    def get_crossovers(self, current_roc: Dict[str, float]) -> Tuple[List[str], List[str]]:
        """Return (cross_up_symbols, cross_down_symbols)."""
        ...
```

---

### Phase 2: Heikin Ashi Calculator

Add Heikin Ashi calculation to the database layer.

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 2.1 | Add `calculate_heikin_ashi()` function | Returns HA OHLC from regular OHLC |
| [ ] 2.2 | Add `get_ha_data()` method to IndicatorsDB | Returns HA values for symbol list |
| [ ] 2.3 | Add HA state tracking for continuity | Track previous HA values for accurate calculation |

**File:** `data/indicators_db.py`

```python
# Target additions
def calculate_heikin_ashi(open: float, high: float, low: float, close: float,
                          prev_ha_open: float = None, prev_ha_close: float = None) -> dict:
    """Calculate Heikin Ashi bar from OHLC data."""
    ...

def get_ha_data(self, symbols: List[str]) -> Dict[str, dict]:
    """Get Heikin Ashi data for multiple symbols."""
    ...
```

---

### Phase 3: Entry/Exit Logic Updates

Modify the trading bot to use ROC + HA signals.

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 3.1 | Add ROC strategy config to `config.py` | New constants: `STRATEGY_TYPE`, `ROC_CROSS_THRESHOLD` |
| [ ] 3.2 | Create `get_roc_entry_candidates()` in IndicatorsDB | Returns symbols with ROC cross up |
| [ ] 3.3 | Create `get_roc_exit_signals()` in IndicatorsDB | Returns symbols with ROC cross down |
| [ ] 3.4 | Update `find_entries()` in connors_bot.py | Use ROC crossover instead of CRSI |
| [ ] 3.5 | Update `check_exits()` in connors_bot.py | Use ROC crossover instead of SMA5 |
| [ ] 3.6 | Integrate ROCStateManager in bot cycle | Load at start, save after each cycle |

**File:** `config.py`

```python
# Target additions
class StrategyType(Enum):
    CRSI = "crsi"           # Original ConnorsRSI strategy
    ROC_HA = "roc_ha"       # ROC + Heikin Ashi strategy

STRATEGY_TYPE = StrategyType.ROC_HA  # Active strategy
ROC_CROSS_THRESHOLD = 0.0            # Cross above/below this value
```

---

### Phase 4: Integration & Testing

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 4.1 | Update log messages for ROC strategy | Logs show ROC values, crossover direction |
| [ ] 4.2 | Update trade journal CSV columns | Include ROC value instead of CRSI |
| [ ] 4.3 | Verify dual-account mode works | Both SAFE and CLASSIC execute same signals |
| [ ] 4.4 | Add strategy type to cycle summary | Display shows "ROC+HA" or "CRSI" |
| [ ] 4.5 | Test bot startup with empty state file | Bot handles missing/corrupt state gracefully |
| [ ] 4.6 | Test bot crash recovery | State persists, resumes correctly |

---

### Phase 5: Documentation & Cleanup

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| [ ] 5.1 | Update CLAUDE.md with ROC+HA strategy info | Strategy rules documented |
| [ ] 5.2 | Remove or comment out unused CRSI code | Clean codebase, but reversible |
| [ ] 5.3 | Git commit with detailed message | All changes committed |

---

## 5. Detailed Task Specifications

### Task 1.1: Create roc_state.py Module

**File:** `data/roc_state.py`

**Purpose:** Manage file-based persistence of ROC values for crossover detection.

**Implementation:**

```python
"""
ROC State Manager - File-based persistence for ROC crossover detection.

Stores previous cycle's ROC values in JSON format to enable detection of
ROC crossing above/below zero between trading cycles.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from config import ET, LOG_DIR

logger = logging.getLogger(__name__)


class ROCStateManager:
    """Manages ROC state persistence for crossover detection."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or LOG_DIR / "roc_state.json"
        self.previous_roc: Dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        """Load previous ROC values from JSON file."""
        ...

    def save(self, current_roc: Dict[str, float]) -> None:
        """Save current ROC values and update previous state."""
        ...

    def get_cross_up(self, current_roc: Dict[str, float]) -> List[str]:
        """Return symbols where ROC just crossed above 0."""
        ...

    def get_cross_down(self, current_roc: Dict[str, float]) -> List[str]:
        """Return symbols where ROC just crossed below 0."""
        ...
```

**Acceptance Criteria:**
- [ ] File created at `data/roc_state.py`
- [ ] Class loads existing state on init
- [ ] `save()` writes JSON with timestamp
- [ ] `get_cross_up()` returns correct symbols
- [ ] `get_cross_down()` returns correct symbols
- [ ] Handles missing/corrupt state file gracefully

---

### Task 1.2-1.6: ROCStateManager Methods

**JSON State Format:**

```json
{
    "timestamp": "2025-12-26T11:35:00-05:00",
    "cycle": 15,
    "roc_values": {
        "AAPL": 0.523,
        "MSFT": -0.217,
        "GOOGL": 0.089,
        ...
    }
}
```

**Crossover Logic:**

```python
def get_cross_up(self, current_roc: Dict[str, float]) -> List[str]:
    """Return symbols where ROC just crossed above 0."""
    cross_up = []
    for symbol, current in current_roc.items():
        previous = self.previous_roc.get(symbol, 0.0)
        if current > 0 and previous <= 0:
            cross_up.append(symbol)
    return cross_up

def get_cross_down(self, current_roc: Dict[str, float]) -> List[str]:
    """Return symbols where ROC just crossed below 0."""
    cross_down = []
    for symbol, current in current_roc.items():
        previous = self.previous_roc.get(symbol, 0.0)
        if current < 0 and previous >= 0:
            cross_down.append(symbol)
    return cross_down
```

---

### Task 2.1: Heikin Ashi Calculation

**File:** `data/indicators_db.py`

**Function:**

```python
def calculate_heikin_ashi(
    open_price: float,
    high: float,
    low: float,
    close: float,
    prev_ha_open: Optional[float] = None,
    prev_ha_close: Optional[float] = None
) -> Dict[str, float]:
    """
    Calculate Heikin Ashi bar from regular OHLC data.

    Args:
        open_price: Regular open price
        high: Regular high price
        low: Regular low price
        close: Regular close price
        prev_ha_open: Previous HA open (None for first bar)
        prev_ha_close: Previous HA close (None for first bar)

    Returns:
        Dict with ha_open, ha_high, ha_low, ha_close
    """
    ha_close = (open_price + high + low + close) / 4

    if prev_ha_open is not None and prev_ha_close is not None:
        ha_open = (prev_ha_open + prev_ha_close) / 2
    else:
        ha_open = (open_price + close) / 2

    ha_high = max(high, ha_open, ha_close)
    ha_low = min(low, ha_open, ha_close)

    return {
        'ha_open': ha_open,
        'ha_high': ha_high,
        'ha_low': ha_low,
        'ha_close': ha_close
    }
```

---

### Task 3.1: Config Updates

**File:** `config.py`

**Additions:**

```python
from enum import Enum

class StrategyType(Enum):
    """Trading strategy selection."""
    CRSI = "crsi"       # Original ConnorsRSI (daily timeframe)
    ROC_HA = "roc_ha"   # ROC + Heikin Ashi (intraday)

# =============================================================================
# Strategy Configuration
# =============================================================================

# Active strategy
STRATEGY_TYPE = StrategyType.ROC_HA

# ROC + Heikin Ashi parameters
ROC_CROSS_THRESHOLD = 0.0    # Enter when ROC crosses above this
ROC_PERIOD = 10              # Already computed in VV7 (10-period)

# Legacy CRSI parameters (kept for reference/rollback)
ENTRY_CRSI = 10              # Enter when CRSI <= 10 (if using CRSI strategy)
```

---

### Task 3.4-3.5: Bot Entry/Exit Logic

**File:** `connors_bot.py`

**Modified find_entries():**

```python
def find_entries(self) -> List[Dict]:
    """Find entry candidates based on active strategy."""
    if STRATEGY_TYPE == StrategyType.ROC_HA:
        # Get current ROC values for all symbols
        current_roc = self.db.get_all_roc_values()

        # Find symbols where ROC just crossed above 0
        cross_up_symbols = self.roc_state.get_cross_up(current_roc)

        # Filter by existing criteria (volume, price, not already owned)
        candidates = self.db.get_symbols_data(cross_up_symbols)
        candidates = [c for c in candidates
                      if c['volume'] >= MIN_VOLUME
                      and c['close'] >= MIN_PRICE
                      and c['symbol'] not in self.safe_positions
                      and c['symbol'] not in self.classic_positions]

        return candidates[:max_slots]
    else:
        # Original CRSI logic
        return self.db.get_entry_candidates(max_crsi=ENTRY_CRSI, ...)
```

**Modified check_exits():**

```python
def check_exits(self, account: str) -> List[Dict]:
    """Check for exit signals based on active strategy."""
    positions = self.safe_positions if account == "SAFE" else self.classic_positions

    if STRATEGY_TYPE == StrategyType.ROC_HA:
        # Get current ROC for held positions
        symbols = list(positions.keys())
        current_roc = self.db.get_roc_for_symbols(symbols)

        # Find symbols where ROC crossed below 0
        cross_down = self.roc_state.get_cross_down(current_roc)

        exit_signals = []
        for symbol in cross_down:
            if symbol in positions:
                pos = positions[symbol]
                current_price = self.db.get_current_price(symbol)
                pnl = (current_price - pos['entry_price']) * pos['shares']
                exit_signals.append({
                    'symbol': symbol,
                    'shares': pos['shares'],
                    'current_price': current_price,
                    'reason': 'roc_cross_down',
                    'pnl': pnl
                })
        return exit_signals
    else:
        # Original SMA5 exit logic
        ...
```

---

## 6. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| State file corruption | Keep backup of last 3 state files |
| Missing ROC data | Default to 0.0 (no crossover detected) |
| VV7 sync delay | Bot waits for sync_complete.txt before cycle |
| Strategy underperformance | Keep CRSI code for quick rollback |
| Dual-account desync | Single ROC state shared by both accounts |

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Win Rate | >50% | Trade journal analysis |
| Profit Factor | >1.5 | Total wins / Total losses |
| Max Drawdown | <10% | Account equity tracking |
| Trades per Day | 5-20 | Cycle logs |
| Bot Uptime | >99% | Crash recovery testing |

---

## 8. Rollback Plan

If ROC+HA strategy underperforms:

1. Set `STRATEGY_TYPE = StrategyType.CRSI` in config.py
2. Restart bot
3. Original CRSI logic activates immediately
4. No code changes required

---

## 9. Timeline Estimate

| Phase | Tasks | Estimate |
|-------|-------|----------|
| Phase 1 | ROC State Persistence | 6 tasks |
| Phase 2 | Heikin Ashi Calculator | 3 tasks |
| Phase 3 | Entry/Exit Logic | 6 tasks |
| Phase 4 | Integration & Testing | 6 tasks |
| Phase 5 | Documentation | 3 tasks |
| **Total** | | **24 tasks** |

---

## 10. Checklist Summary

### Phase 1: ROC State Persistence
- [ ] 1.1 Create `data/roc_state.py` module
- [ ] 1.2 Implement `ROCStateManager` class
- [ ] 1.3 Implement `load()` method
- [ ] 1.4 Implement `save()` method
- [ ] 1.5 Implement `get_cross_up()` and `get_cross_down()` methods
- [ ] 1.6 Add automatic backup/rotation

### Phase 2: Heikin Ashi Calculator
- [ ] 2.1 Add `calculate_heikin_ashi()` function
- [ ] 2.2 Add `get_ha_data()` method to IndicatorsDB
- [ ] 2.3 Add HA state tracking for continuity

### Phase 3: Entry/Exit Logic
- [ ] 3.1 Add ROC strategy config to `config.py`
- [ ] 3.2 Create `get_roc_entry_candidates()` in IndicatorsDB
- [ ] 3.3 Create `get_roc_exit_signals()` in IndicatorsDB
- [ ] 3.4 Update `find_entries()` in connors_bot.py
- [ ] 3.5 Update `check_exits()` in connors_bot.py
- [ ] 3.6 Integrate ROCStateManager in bot cycle

### Phase 4: Integration & Testing
- [ ] 4.1 Update log messages for ROC strategy
- [ ] 4.2 Update trade journal CSV columns
- [ ] 4.3 Verify dual-account mode works
- [ ] 4.4 Add strategy type to cycle summary
- [ ] 4.5 Test bot startup with empty state file
- [ ] 4.6 Test bot crash recovery

### Phase 5: Documentation & Cleanup
- [ ] 5.1 Update CLAUDE.md with ROC+HA strategy info
- [ ] 5.2 Remove or comment out unused CRSI code
- [ ] 5.3 Git commit with detailed message

---

*Document generated by Claude Code - 2025-12-26*
