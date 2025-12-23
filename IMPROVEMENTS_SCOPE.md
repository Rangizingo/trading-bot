# Connors RSI Trading Bot - Improvements Scope

## Overview

This document outlines improvements to the Connors RSI trading bot to enhance reliability, data quality, and operational visibility.

### Goals
1. Fix data quality issues (RSI calculation bug affecting 45% of symbols)
2. Filter out illiquid stocks to avoid positions like BBP
3. Add Discord notifications for real-time trade alerts
4. Clean up repository with proper .gitignore

### Current State
- Bot is operational and executing trades via Alpaca API
- File-based sync trigger working correctly
- Wash trade prevention implemented
- ENTRY_RSI set to 10 for balanced trade frequency

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   VV7 Bridge    │────▶│  intraday.db    │────▶│  Connors Bot    │
│  (C# DLL)       │     │  (SQLite)       │     │  (Python)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                               │
        ▼                                               ▼
┌─────────────────┐                           ┌─────────────────┐
│ sync_complete   │                           │   Alpaca API    │
│    .txt         │                           │   (Trading)     │
└─────────────────┘                           └─────────────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │    Discord      │
                                              │  (Notifications)│
                                              └─────────────────┘
```

---

## Development Phases

### Phase 1: Data Quality Fixes
Fix VV7 RSI calculation and add data quality filters.

### Phase 2: Discord Notifications
Set up webhook and integrate notifications into trading bot.

### Phase 3: Repository Cleanup
Add .gitignore and clean up generated files.

---

## Task Checklist

### Phase 1: Data Quality Fixes

#### 1.1 Fix VV7 RSI Calculation
- **File**: `C:\Users\User\Documents\AI\VV7\VV7SimpleBridge\VV7SimpleBridge.cs`
- **Issue**: RSI returns 0.0 when there's no price movement (avg_gain=0, avg_loss=0)
- **Fix**: Return 50.0 (neutral) instead of 0.0
- **Impact**: Currently affects 4,513 / 9,850 symbols (45.8%)
- **Acceptance**: After fix, symbols with no movement show RSI=50.0

**Steps**:
- [ ] 1.1.1 Find RSI calculation in VV7SimpleBridge.cs
- [ ] 1.1.2 Add check for avg_gain=0 AND avg_loss=0 case
- [ ] 1.1.3 Return 50.0 for no-movement scenario
- [ ] 1.1.4 Rebuild VV7 DLL
- [ ] 1.1.5 Run sync and verify RSI values improved

---

#### 1.2 Re-enable Volume Filter
- **File**: `config.py`
- **Current**: `MIN_VOLUME = 0` (disabled)
- **Change**: `MIN_VOLUME = 100000`
- **Reason**: Filter out illiquid stocks like BBP (99% zero volume bars)
- **Acceptance**: Bot only considers stocks with adequate daily volume

**Steps**:
- [ ] 1.2.1 Update MIN_VOLUME in config.py
- [ ] 1.2.2 Verify entry query uses volume filter
- [ ] 1.2.3 Test that illiquid stocks are excluded

---

### Phase 2: Discord Notifications

#### 2.1 Create Discord Webhook
- **Platform**: Discord server
- **Purpose**: Real-time trade notifications

**Steps**:
- [ ] 2.1.1 Create Discord server (or use existing)
- [ ] 2.1.2 Create #trading-alerts channel
- [ ] 2.1.3 Create webhook (Channel Settings → Integrations → Webhooks)
- [ ] 2.1.4 Copy webhook URL
- [ ] 2.1.5 Add DISCORD_WEBHOOK_URL to .env file

---

#### 2.2 Create Discord Notifier Module
- **File**: `notifications/discord_notifier.py`
- **Purpose**: Send formatted messages to Discord

**Steps**:
- [ ] 2.2.1 Create notifications/ directory
- [ ] 2.2.2 Create discord_notifier.py with DiscordNotifier class
- [ ] 2.2.3 Implement send_message() method
- [ ] 2.2.4 Implement send_entry_alert() with embed formatting
- [ ] 2.2.5 Implement send_exit_alert() with P&L display
- [ ] 2.2.6 Implement send_cycle_summary() for periodic updates
- [ ] 2.2.7 Add error handling for failed webhook calls
- [ ] 2.2.8 Test notifications independently

**Code Structure**:
```python
class DiscordNotifier:
    def __init__(self, webhook_url: str)
    def send_message(self, content: str) -> bool
    def send_entry_alert(self, symbol, shares, price, rsi, stop_loss) -> bool
    def send_exit_alert(self, symbol, shares, price, reason, pnl) -> bool
    def send_cycle_summary(self, equity, positions, entries, exits, pnl) -> bool
    def send_startup_message(self, config_summary) -> bool
    def send_shutdown_message(self, summary) -> bool
```

---

#### 2.3 Integrate Notifications into Bot
- **File**: `connors_bot.py`
- **Purpose**: Call notifier on trade events

**Steps**:
- [ ] 2.3.1 Import DiscordNotifier
- [ ] 2.3.2 Initialize notifier in ConnorsBot.__init__()
- [ ] 2.3.3 Add send_startup_message() in run()
- [ ] 2.3.4 Add send_entry_alert() after successful entry
- [ ] 2.3.5 Add send_exit_alert() after successful exit
- [ ] 2.3.6 Add send_cycle_summary() at end of each cycle
- [ ] 2.3.7 Add send_shutdown_message() on graceful shutdown
- [ ] 2.3.8 Handle notification failures gracefully (don't crash bot)

---

#### 2.4 Add Webhook URL to Config
- **File**: `config.py`
- **Purpose**: Load Discord webhook from environment

**Steps**:
- [ ] 2.4.1 Add DISCORD_WEBHOOK_URL to config.py
- [ ] 2.4.2 Make it optional (bot works without Discord)
- [ ] 2.4.3 Add to .env.example for documentation

---

### Phase 3: Repository Cleanup

#### 3.1 Add .gitignore
- **File**: `.gitignore`
- **Purpose**: Exclude generated files from version control

**Steps**:
- [ ] 3.1.1 Create .gitignore file
- [ ] 3.1.2 Add Python patterns (__pycache__, *.pyc, *.pyo)
- [ ] 3.1.3 Add logs directory (logs/)
- [ ] 3.1.4 Add environment files (.env)
- [ ] 3.1.5 Add investigation scripts (investigate_*.py, check_*.py)
- [ ] 3.1.6 Add IDE files (.vscode/, .idea/)
- [ ] 3.1.7 Remove tracked files that should be ignored

---

#### 3.2 Clean Up Investigation Files
- **Files**: `investigate_*.py`, `check_*.py`, `*_INVESTIGATION.md`
- **Purpose**: Remove temporary investigation scripts

**Steps**:
- [ ] 3.2.1 Delete investigate_bbp_data.py
- [ ] 3.2.2 Delete investigate_db.py
- [ ] 3.2.3 Delete check_schema.py
- [ ] 3.2.4 Delete check_single_candidate.py
- [ ] 3.2.5 Delete BBP_DATA_INVESTIGATION.md
- [ ] 3.2.6 Delete INVESTIGATION_REPORT.md

---

## Notification Message Formats

### Entry Alert
```
🟢 ENTRY: AAPL
━━━━━━━━━━━━━━━━
Shares: 50
Price: $185.42
RSI: 8.5
Stop Loss: $179.86 (3%)
Position Value: $9,271.00
```

### Exit Alert
```
🔴 EXIT: AAPL
━━━━━━━━━━━━━━━━
Shares: 50
Price: $188.50
Reason: SMA5 Exit
P&L: +$154.00 (+1.7%)
```

### Cycle Summary
```
📊 Cycle #15 Complete
━━━━━━━━━━━━━━━━
Equity: $96,542.18
Positions: 4/5
Entries: 1
Exits: 2
Cycle P&L: +$89.50
```

### Startup Message
```
🤖 Connors RSI Bot Started
━━━━━━━━━━━━━━━━
Strategy: Entry RSI ≤ 10, Exit Close > SMA5
Position Size: 10%
Max Positions: 5
Stop Loss: 3%
Mode: Paper Trading
```

---

## Dependencies

### New Python Package
```
pip install requests  # For Discord webhook (likely already installed)
```

### Environment Variables
```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## Testing Checklist

- [ ] RSI calculation returns 50.0 for no-movement stocks
- [ ] Volume filter excludes stocks with volume < 100,000
- [ ] Discord webhook receives test message
- [ ] Entry alerts appear in Discord with correct formatting
- [ ] Exit alerts appear in Discord with P&L
- [ ] Cycle summaries post to Discord
- [ ] Bot continues working if Discord webhook fails
- [ ] .gitignore properly excludes files

---

## Completion Criteria

All items checked = Ready for production monitoring

**Estimated Tasks**: 25 individual steps
**Phases**: 3

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
