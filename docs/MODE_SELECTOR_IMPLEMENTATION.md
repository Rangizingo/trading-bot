# Trading Mode Selector Implementation

## Phase 3.2-3.4 Complete

This document describes the implementation of the interactive trading mode selector UI.

## Implementation Details

### Files Modified

#### `connors_bot.py`

Added two new functions immediately after the NYSE_HOLIDAYS definition:

1. **`render_mode_menu(term: Terminal, selected_index: int) -> None`**
   - Renders the formatted selection box with both trading modes
   - Highlights the selected mode with `>` prefix and green/bold terminal colors
   - Uses Unicode box-drawing characters for clean UI borders
   - Displays all features for each mode with proper indentation

2. **`select_trading_mode() -> TradingMode`**
   - Main interactive selector function
   - Uses `blessed.Terminal` for cross-platform terminal control
   - Keyboard controls:
     - UP/DOWN arrows: Navigate between modes
     - ENTER: Confirm selection and return selected mode
     - ESC: Exit program cleanly with `sys.exit(0)`
   - Defaults to SAFE mode (index 0)

### Imports Added

```python
from blessed import Terminal
from config import TradingMode, MODE_INFO
```

### Dependencies

- `blessed>=1.25.0` - Already in requirements.txt
- No additional dependencies needed

## UI Output Example

```
======================================================================
                    SELECT TRADING MODE
======================================================================

  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │   > SAFE MODE (Recommended for beginners)                       │
  │     ├─ Entry: Bracket order (BUY + STOP)                        │
  │     ├─ Stop Loss: 3% below entry                                │
  │     ├─ Exit: Price > SMA5 OR stop triggered                     │
  │     ├─ Max Loss: 3% per position                                │
  │     └─ Risk: Lower (capped losses)                              │
  │                                                                 │
  │     CLASSIC MODE (Larry Connors original)                       │
  │     ├─ Entry: Simple BUY order                                  │
  │     ├─ Stop Loss: None                                          │
  │     ├─ Exit: Price > SMA5 only                                  │
  │     ├─ Max Loss: Unlimited (ride the dip)                       │
  │     └─ Risk: Higher (but 75% win rate historically)             │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘

        ↑/↓ to select    ENTER to confirm    ESC to quit

======================================================================
```

## Testing

A test script has been created: `test_mode_selector.py`

Run it to test the UI without starting the full bot:

```bash
python test_mode_selector.py
```

## Features

- **Visual Highlighting**: Selected mode shown in bold green with `>` indicator
- **Clean Box Drawing**: Uses Unicode box-drawing characters for professional appearance
- **Cross-Platform**: Works on Windows, Linux, and macOS via `blessed` library
- **Type-Safe**: Returns `TradingMode` enum for type checking
- **Graceful Exit**: ESC key cleanly exits with proper cleanup

## Next Steps

This completes Phase 3.2-3.4 of the trading mode selector implementation.

Remaining phases:
- **Phase 4**: Integrate mode into ConnorsBot class
  - Modify `__init__()` to accept mode parameter
  - Update entry logic to branch on mode
  - Modify exit logic for classic mode
  - Call selector from `main()`
- **Phase 5**: Testing & polish

## Technical Notes

### Padding Calculation

The implementation carefully handles ANSI color escape sequences, which don't contribute to visible text width. When applying colors, we:

1. Calculate the plain text length
2. Compute padding needed to fill the box width (65 chars)
3. Apply color to text, then add padding separately

This ensures the box borders align correctly even when text is colored.

### Default Mode

The selector defaults to SAFE mode (index 0), which is recommended for beginners and matches the current bot behavior.
