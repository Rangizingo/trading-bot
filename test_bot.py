"""Test trading bot without executing trades."""
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')

from main_v2 import TradingBot
from data.intraday_bridge import IntradayBridge

print("=" * 50)
print("TRADING BOT TEST")
print("=" * 50)

# 1. Check cache stats
print("\n[1] Cache Stats:")
bridge = IntradayBridge()
if bridge.is_cache_available():
    stats = bridge.get_cache_stats()
    print(f"    Records: {stats['total_records']:,}")
    print(f"    Symbols: {stats['symbol_count']:,}")
    print(f"    Latest:  {stats['latest_timestamp']}")
    print(f"    Earliest: {stats['earliest_timestamp']}")
else:
    print("    Cache NOT available!")
    sys.exit(1)

# 2. Initialize bot
print("\n[2] Initialize Bot:")
bot = TradingBot(paper=True)
print(f"    Strategies: {len(bot.strategies)}")
for s in bot.strategies:
    print(f"      - {s.config.name}")

# 3. Startup checks
print("\n[3] Startup Checks:")
if not bot.startup_checks():
    print("    FAILED!")
    sys.exit(1)

# 4. Get candidates
print("\n[4] Get Candidates:")
candidates = bot.get_candidates()
print(f"    Found: {len(candidates)} candidates")
if candidates:
    print(f"    Sample: {candidates[:10]}")

# 5. Generate signals (on first 20 candidates)
print("\n[5] Generate Signals:")
if candidates:
    signals = bot.generate_signals(candidates[:20])
    print(f"    Generated: {len(signals)} signals")

    buy_signals = [s for s in signals if s.action.value == 'buy']
    sell_signals = [s for s in signals if s.action.value == 'sell']
    print(f"    BUY: {len(buy_signals)}, SELL: {len(sell_signals)}")

    if buy_signals:
        print("\n    Top BUY signals:")
        for s in sorted(buy_signals, key=lambda x: x.strength, reverse=True)[:5]:
            print(f"      {s.symbol:6} | Strength: {s.strength:.2f} | {s.strategy} | {s.reason}")
else:
    print("    No candidates to evaluate")

# 6. Check existing positions
print("\n[6] Current Positions:")
positions = bot.alpaca.get_positions()
if positions:
    for p in positions:
        print(f"    {p.symbol}: {p.qty} shares @ ${p.avg_entry_price:.2f} (P&L: ${p.unrealized_pl:.2f})")
else:
    print("    No open positions")

# 7. Account status
print("\n[7] Account Status:")
account = bot.alpaca.get_account()
print(f"    Equity: ${account.equity:,.2f}")
print(f"    Cash: ${account.cash:,.2f}")
print(f"    Buying Power: ${account.buying_power:,.2f}")

print("\n" + "=" * 50)
print("TEST COMPLETE - No trades executed")
print("=" * 50)
