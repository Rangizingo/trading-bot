# Trading Mode Selector - Project Scope

## Overview

Add an interactive startup prompt to `connors_bot.py` that allows users to select between two trading modes using arrow key navigation.

### Goals
- Provide easy switching between safe (stops) and classic (no stops) strategies
- Display clear differences between modes before selection
- Maintain backwards compatibility with existing functionality

### Trading Modes

| Feature | Safe Mode | Classic Mode |
|---------|-----------|--------------|
| Entry Order | Bracket (BUY + STOP) | Simple BUY |
| Stop Loss | 3% below entry | None |
| Exit Trigger | Price > SMA5 OR stop | Price > SMA5 only |
| Max Loss | 3% per position | Unlimited |
| Risk Level | Lower | Higher |
| Based On | Current bot behavior | Larry Connors original |

---

## Architecture

```
connors_bot.py
    │
    ├── select_trading_mode()      # NEW: Interactive selector
    │   ├── render_mode_menu()     # NEW: Display formatted box
    │   └── handle_keypress()      # NEW: Arrow key navigation
    │
    ├── ConnorsBot.__init__(mode)  # MODIFY: Accept mode parameter
    │
    ├── execute_entries()          # MODIFY: Branch on mode
    │   ├── Safe: submit_bracket_order()
    │   └── Classic: submit_simple_order()  # NEW method
    │
    └── check_exits()              # MODIFY: Skip stop logic in classic
```

### Dependencies
- `blessed` library (cross-platform terminal UI, better than `keyboard`)
- No other new dependencies

---

## Development Phases

### Phase 1: Foundation
Configuration and constants setup.

### Phase 2: Alpaca Client
Add simple order method for classic mode.

### Phase 3: Mode Selector UI
Interactive arrow-key menu with formatted display.

### Phase 4: Bot Logic Integration
Wire mode through entry/exit logic.

### Phase 5: Testing & Polish
Verify both modes work correctly.

---

## Task Checklist

### Phase 1: Foundation

- [ ] **1.1** Add `TradingMode` enum to `config.py`
  ```python
  from enum import Enum
  class TradingMode(Enum):
      SAFE = "safe"
      CLASSIC = "classic"
  ```
  - Acceptance: Enum importable, has two values

- [ ] **1.2** Add mode descriptions to `config.py`
  ```python
  MODE_INFO = {
      TradingMode.SAFE: {
          "name": "SAFE MODE",
          "subtitle": "Recommended for beginners",
          "features": [...]
      },
      ...
  }
  ```
  - Acceptance: Dict contains all display info for both modes

---

### Phase 2: Alpaca Client

- [ ] **2.1** Add `submit_simple_order()` to `execution/alpaca_client.py`
  ```python
  def submit_simple_order(self, symbol: str, qty: int) -> dict:
      """Submit market buy order without stop loss."""
  ```
  - Acceptance: Returns order_id on success, None on failure
  - Dependencies: None

- [ ] **2.2** Add `get_open_orders()` helper if not exists
  - Acceptance: Returns list of open orders for monitoring
  - Dependencies: 2.1

---

### Phase 3: Mode Selector UI

- [ ] **3.1** Install `blessed` library
  ```bash
  pip install blessed
  ```
  - Acceptance: `from blessed import Terminal` works
  - Add to requirements.txt

- [ ] **3.2** Create `select_trading_mode()` function in `connors_bot.py`
  ```python
  def select_trading_mode() -> TradingMode:
      """Interactive mode selector with arrow keys."""
  ```
  - Acceptance: Returns selected TradingMode enum
  - Dependencies: 1.1, 1.2, 3.1

- [ ] **3.3** Implement `render_mode_menu()` helper
  ```python
  def render_mode_menu(term, selected_index: int) -> None:
      """Render the mode selection box with highlighting."""
  ```
  - Display formatted box with both modes
  - Highlight selected mode with `>`
  - Show feature comparison
  - Acceptance: Renders correctly in terminal
  - Dependencies: 3.1

- [ ] **3.4** Implement keyboard handling loop
  ```python
  # Arrow up/down to navigate
  # Enter to confirm
  # ESC to quit
  ```
  - Acceptance: Arrow keys move selection, Enter confirms
  - Dependencies: 3.2, 3.3

---

### Phase 4: Bot Logic Integration

- [ ] **4.1** Modify `ConnorsBot.__init__()` to accept mode
  ```python
  def __init__(self, paper: bool = True, mode: TradingMode = TradingMode.SAFE):
      self.mode = mode
  ```
  - Acceptance: Mode stored as instance variable
  - Dependencies: 1.1

- [ ] **4.2** Update startup banner to display selected mode
  ```python
  self.logger.info(f"Mode: {self.mode.value.upper()}")
  ```
  - Acceptance: Mode visible in startup logs
  - Dependencies: 4.1

- [ ] **4.3** Modify entry execution to branch on mode
  ```python
  if self.mode == TradingMode.SAFE:
      result = self.alpaca.submit_bracket_order(...)
  else:
      result = self.alpaca.submit_simple_order(...)
  ```
  - Acceptance: Safe mode uses brackets, Classic uses simple orders
  - Dependencies: 2.1, 4.1

- [ ] **4.4** Modify position tracking for classic mode
  - Classic mode: No stop_order_id to track
  - Safe mode: Unchanged (track stop_order_id)
  - Acceptance: Positions dict handles both cases
  - Dependencies: 4.3

- [ ] **4.5** Modify exit logic for classic mode
  - Classic: Only check Price > SMA5
  - Safe: Check Price > SMA5 OR stop triggered (unchanged)
  - Acceptance: Classic mode never references stop orders
  - Dependencies: 4.4

- [ ] **4.6** Update `main()` to call mode selector
  ```python
  if __name__ == "__main__":
      mode = select_trading_mode()
      bot = ConnorsBot(paper=True, mode=mode)
      bot.run()
  ```
  - Acceptance: Mode selector appears on startup
  - Dependencies: 3.4, 4.1

---

### Phase 5: Testing & Polish

- [ ] **5.1** Test Safe Mode (regression)
  - Start bot, select Safe Mode
  - Verify bracket orders placed
  - Verify stops tracked
  - Acceptance: Behaves same as before

- [ ] **5.2** Test Classic Mode
  - Start bot, select Classic Mode
  - Verify simple buy orders placed
  - Verify no stops created
  - Verify exit only on SMA5
  - Acceptance: No stop orders in Alpaca

- [ ] **5.3** Test ESC to quit
  - Press ESC at mode selector
  - Acceptance: Bot exits cleanly

- [ ] **5.4** Update README or docs
  - Document the two modes
  - Acceptance: Users understand the tradeoffs

---

## File Changes Summary

| File | Changes |
|------|---------|
| `config.py` | Add TradingMode enum, MODE_INFO dict |
| `execution/alpaca_client.py` | Add submit_simple_order() |
| `connors_bot.py` | Add selector UI, modify init/entry/exit |
| `requirements.txt` | Add blessed |

---

## Estimated Effort

| Phase | Tasks | Complexity |
|-------|-------|------------|
| Phase 1 | 2 | Low |
| Phase 2 | 2 | Low |
| Phase 3 | 4 | Medium |
| Phase 4 | 6 | Medium |
| Phase 5 | 4 | Low |
| **Total** | **18** | **~1-2 hours** |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| `blessed` not working on Windows | Test early, fallback to simple input() |
| Classic mode big losses | Clear warning in UI, user acknowledges |
| Breaking existing behavior | Safe mode is default, regression test |

---

## Success Criteria

1. Bot starts with interactive mode selector
2. Arrow keys navigate, Enter confirms, ESC quits
3. Safe mode behaves identically to current bot
4. Classic mode places no stop orders
5. Selected mode displayed in startup banner
