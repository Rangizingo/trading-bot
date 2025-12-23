# Bug Fix Scope - Connors RSI Trading Bot

## Overview

This document tracks all bugs and issues identified during code verification of the Connors RSI trading bot. Issues are categorized by severity and organized as a development checklist.

**Strategy Rules:**
- Entry: RSI(2) <= 5 AND Close > SMA200
- Exit: RSI(2) > 60 OR Close > SMA5 OR Stop Loss (3%)

---

## Critical Issues (Must Fix Before Trading)

### 1.1 Bracket Order Race Condition
- [ ] **File:** `execution/alpaca_client.py` - `submit_bracket_order()`
- **Problem:** Stop loss order submitted immediately after buy order, but buy may not be filled yet. Alpaca rejects stop orders for positions that don't exist.
- **Impact:** Stop loss orders fail silently, positions unprotected.
- **Fix:**
  1. Submit buy order
  2. Wait for fill (poll order status)
  3. Get actual fill price
  4. Submit stop order with correct quantity and stop price based on actual fill
- **Acceptance:** Buy fill confirmed before stop order submitted

### 1.2 TimeInForce Mismatch
- [ ] **File:** `execution/alpaca_client.py` - `submit_bracket_order()`
- **Problem:** Buy order uses `TimeInForce.DAY`, stop uses `TimeInForce.GTC`. If buy fills at EOD, stop persists to next day.
- **Impact:** Orphaned stop orders, unexpected executions.
- **Fix:** Use consistent TimeInForce (both DAY or both GTC based on strategy needs)
- **Acceptance:** Both orders use same TimeInForce

### 1.3 NULL Handling in SQL Queries
- [ ] **File:** `data/indicators_db.py` - `get_entry_candidates()`, `get_position_data()`
- **Problem:** SQL comparisons with NULL return NULL (falsy). Indicators may be NULL for recent bars.
- **Current Code:**
  ```sql
  WHERE rsi < ? AND close > sma200
  ```
- **Fix:** Add explicit NULL checks:
  ```sql
  WHERE rsi IS NOT NULL
    AND sma200 IS NOT NULL
    AND rsi <= ?
    AND close > sma200
  ```
- **Acceptance:** Queries explicitly exclude NULL indicator values

---

## Major Issues (Should Fix Before Live Use)

### 2.1 RSI Comparison Operator
- [ ] **File:** `data/indicators_db.py` - `get_entry_candidates()`
- **Problem:** Uses `rsi < 5` but strategy specifies `RSI <= 5`
- **Impact:** Misses valid entry signals when RSI exactly equals 5
- **Fix:** Change `<` to `<=`
- **Acceptance:** Entry candidates include RSI = 5.0

### 2.2 Missing SMA5 Exit in validate_positions()
- [ ] **File:** `connors_bot.py` - `validate_positions()`
- **Problem:** Validates stop loss and RSI exit, but not SMA5 exit condition
- **Current Checks:**
  - Stop loss hit
  - RSI > 60
  - Close < SMA200
- **Missing Check:**
  - Close > SMA5 (exit signal)
- **Fix:** Add SMA5 check to validation logic
- **Acceptance:** Positions with close > SMA5 flagged for exit on startup

### 2.3 Position Sizing Uses Total Equity
- [ ] **File:** `connors_bot.py` - `find_entries()`
- **Problem:** Position size calculated from total account equity, not available buying power
- **Impact:** May attempt to buy more than available cash, especially near max positions
- **Current Code:**
  ```python
  position_value = account.equity * Decimal(str(config.POSITION_SIZE_PCT))
  ```
- **Fix:** Use `account.buying_power` or `account.cash` with safety margin
- **Acceptance:** Position sizing respects available buying power

### 2.4 Exit Priority Order
- [ ] **File:** `connors_bot.py` - `check_exits()`
- **Problem:** Stop loss checked last. If price gaps down through stop AND RSI > 60, may exit at worse price.
- **Current Order:**
  1. RSI > 60
  2. Close > SMA5
  3. Stop loss
- **Better Order:**
  1. Stop loss (most urgent, protect capital)
  2. RSI > 60
  3. Close > SMA5
- **Fix:** Reorder exit condition checks
- **Acceptance:** Stop loss is first exit condition evaluated

### 2.5 Entry Price Tracking
- [ ] **File:** `connors_bot.py` - `find_entries()`
- **Problem:** Stores expected price, not actual Alpaca fill price
- **Impact:** Stop loss calculated from wrong base price
- **Fix:** After confirming fill (from 1.1 fix), use actual fill price
- **Acceptance:** `entry_price` in positions dict matches Alpaca fill price

---

## Minor Issues (Nice to Have)

### 3.1 No Market Holiday Handling
- [ ] **File:** `connors_bot.py` - `is_market_open()`
- **Problem:** Only checks weekdays, not NYSE holidays
- **Impact:** Bot may run/fail on holidays
- **Fix:** Add holiday calendar check (pandas_market_calendars or hardcoded list)
- **Acceptance:** Bot sleeps on NYSE holidays

### 3.2 Quantity Type Inconsistency
- [ ] **File:** `execution/alpaca_client.py`
- **Problem:** qty sometimes float, sometimes int. Alpaca prefers int for share quantities.
- **Fix:** Ensure `int(qty)` used consistently
- **Acceptance:** All order quantities are integers

### 3.3 Stop Loss Percentage Review
- [ ] **File:** `config.py` - `STOP_LOSS_PCT`
- **Problem:** 3% stop may be too tight for mean reversion strategy
- **Impact:** Premature stop-outs on volatility
- **Consideration:** Mean reversion typically uses wider stops (5-8%) or ATR-based stops
- **Action:** Review after paper trading, adjust if stop-out rate > 40%

### 3.4 Database Connection Handling
- [ ] **File:** `data/indicators_db.py`
- **Problem:** Opens new connection for each query
- **Fix:** Consider connection pooling or context manager for batch operations
- **Acceptance:** Single connection reused within run_cycle()

### 3.5 Logging Enhancement
- [ ] **File:** `connors_bot.py`
- **Problem:** Limited logging for debugging failed orders
- **Fix:** Add order IDs, fill details, rejection reasons to logs
- **Acceptance:** All order outcomes logged with details

---

## Implementation Order

**Phase 1: Critical Fixes** (Required for safe operation)
1. Fix NULL handling in SQL (1.3)
2. Fix bracket order race condition (1.1)
3. Fix TimeInForce mismatch (1.2)

**Phase 2: Major Fixes** (Required for correct strategy execution)
4. Fix RSI comparison operator (2.1)
5. Add SMA5 to validate_positions() (2.2)
6. Fix exit priority order (2.4)
7. Fix entry price tracking (2.5)
8. Fix position sizing (2.3)

**Phase 3: Minor Improvements** (Polish)
9. Add quantity type consistency (3.2)
10. Improve database connection handling (3.4)
11. Enhance logging (3.5)
12. Add holiday handling (3.1)
13. Review stop loss percentage after testing (3.3)

---

## Testing Checklist

After each fix:
- [ ] Code compiles without errors
- [ ] Unit test passes (if applicable)
- [ ] Manual verification in paper trading
- [ ] No regression in existing functionality

**Full Integration Test:**
- [ ] Bot starts with existing positions - validates correctly
- [ ] Bot finds entry candidates - bracket order works
- [ ] Stop loss executes on Alpaca - detected in sync
- [ ] RSI exit triggers - stop order cancelled first
- [ ] SMA5 exit triggers - stop order cancelled first
- [ ] Position sizing respects buying power

---

## Notes

- All fixes should preserve existing functionality
- Test in paper trading before any live use
- User handles testing; Claude writes code only
- Do not push to GitHub until user approves
