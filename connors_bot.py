"""
Connors RSI Trading Bot - Dual Account Mode

This module implements the main trading bot that coordinates all components:
- Database access for indicator screening
- Alpaca API for trade execution on TWO accounts (SAFE and CLASSIC)
- Position tracking and risk management per account
- Market hours scheduling

The bot runs both strategies simultaneously:
- SAFE: Bracket orders with 3%% stop loss
- CLASSIC: Simple orders without stops (original Connors strategy)
"""

import logging
import time
import sys
import csv
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from config import (
    CAPITAL,
    POSITION_SIZE_PCT,
    MAX_POSITIONS_SAFE,
    MAX_POSITIONS_CLASSIC,
    STOP_LOSS_PCT,
    ENTRY_RSI,
    ENTRY_CRSI,
    MIN_VOLUME,
    MIN_PRICE,
    MARKET_OPEN,
    MARKET_CLOSE,
    CYCLE_INTERVAL_MINUTES,
    ET,
    LOG_DIR,
    SYNC_COMPLETE_FILE,
    TradingMode,
    MODE_INFO,
    ALPACA_SAFE_API_KEY,
    ALPACA_SAFE_SECRET_KEY,
    ALPACA_CLASSIC_API_KEY,
    ALPACA_CLASSIC_SECRET_KEY,
)
from data.indicators_db import IndicatorsDB
from execution.alpaca_client import AlpacaClient

# NYSE Market Holidays for 2024-2025
NYSE_HOLIDAYS_2024_2025 = {
    datetime(2024, 1, 1).date(), datetime(2024, 1, 15).date(), datetime(2024, 2, 19).date(),
    datetime(2024, 3, 29).date(), datetime(2024, 5, 27).date(), datetime(2024, 6, 19).date(),
    datetime(2024, 7, 4).date(), datetime(2024, 9, 2).date(), datetime(2024, 11, 28).date(),
    datetime(2024, 12, 25).date(), datetime(2025, 1, 1).date(), datetime(2025, 1, 20).date(),
    datetime(2025, 2, 17).date(), datetime(2025, 4, 18).date(), datetime(2025, 5, 26).date(),
    datetime(2025, 6, 19).date(), datetime(2025, 7, 4).date(), datetime(2025, 9, 1).date(),
    datetime(2025, 11, 27).date(), datetime(2025, 12, 25).date(),
}


def log_trade(account: str, action: str, symbol: str, shares: int, price: float, 
              pnl: float = 0.0, crsi: float = 0.0, hold_minutes: int = 0) -> None:
    """Log trade details to account-specific CSV journal."""
    try:
        journal_file = LOG_DIR / f"trade_journal_{account.lower()}.csv"
        file_exists = journal_file.exists()
        with open(journal_file, mode='a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['timestamp', 'symbol', 'action', 'shares', 'price', 'pnl', 'crsi', 'hold_minutes'])
            timestamp = datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S')
            writer.writerow([timestamp, symbol, action, shares, f'{price:.2f}', f'{pnl:.2f}', f'{crsi:.2f}', hold_minutes])
    except Exception as e:
        logging.getLogger("ConnorsBot").warning(f"Failed to log trade: {e}")




def get_session_pnl(account: str) -> float:
    """Get cumulative P&L from today's trades in the CSV journal."""
    try:
        journal_file = LOG_DIR / f"trade_journal_{account.lower()}.csv"
        if not journal_file.exists():
            return 0.0
        today = datetime.now(ET).strftime('%Y-%m-%d')
        total_pnl = 0.0
        with open(journal_file, mode='r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['timestamp'].startswith(today) and row['action'] == 'EXIT':
                    total_pnl += float(row['pnl'])
        return total_pnl
    except Exception:
        return 0.0

class ConnorsBot:
    """Main trading bot - DUAL ACCOUNT MODE. Runs SAFE and CLASSIC simultaneously."""

    def __init__(self, paper: bool = True) -> None:
        self.db = IndicatorsDB()
        self.safe_client = AlpacaClient(paper=paper, api_key=ALPACA_SAFE_API_KEY, 
                                        secret_key=ALPACA_SAFE_SECRET_KEY, name="SAFE")
        self.classic_client = AlpacaClient(paper=paper, api_key=ALPACA_CLASSIC_API_KEY,
                                           secret_key=ALPACA_CLASSIC_SECRET_KEY, name="CLASSIC")
        self.safe_positions: Dict[str, Dict] = {}
        self.classic_positions: Dict[str, Dict] = {}
        self.max_positions_safe = MAX_POSITIONS_SAFE
        self.max_positions_classic = MAX_POSITIONS_CLASSIC
        self.cycle_count = 0
        self.running = False
        self.console_logger = self._setup_console_logging()
        self.safe_logger = self._setup_file_logging("SAFE")
        self.classic_logger = self._setup_file_logging("CLASSIC")
        self.console_logger.info("ConnorsBot initialized in DUAL MODE")

    def _setup_console_logging(self) -> logging.Logger:
        logger = logging.getLogger("ConnorsBot")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(ch)
        return logger

    def _setup_file_logging(self, account: str) -> logging.Logger:
        logger = logging.getLogger(f"ConnorsBot.{account}")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.propagate = False  # Prevent duplicate logs to parent
        fh = logging.FileHandler(LOG_DIR / f"trading_{account.lower()}.log", mode='w')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(fh)
        return logger

    def log(self, account: str, level: str, message: str) -> None:
        prefixed = f"[{account}] {message}"
        file_logger = self.safe_logger if account == "SAFE" else self.classic_logger
        if level == "info":
            self.console_logger.info(prefixed)
            file_logger.info(message)
        elif level == "warning":
            self.console_logger.warning(prefixed)
            file_logger.warning(message)
        elif level == "error":
            self.console_logger.error(prefixed)
            file_logger.error(message)
        elif level == "debug":
            self.console_logger.debug(prefixed)
            file_logger.debug(message)


    def startup_checks(self) -> bool:
        self.console_logger.info("=" * 70)
        self.console_logger.info("STARTUP CHECKS")
        self.console_logger.info("=" * 70)
        self.console_logger.info("Checking database...")
        if not self.db.is_available():
            self.console_logger.error("Database not available")
            return False
        self.console_logger.info("Database: PASSED")
        self.console_logger.info("Checking SAFE account...")
        try:
            sa = self.safe_client.get_account()
            self.log("SAFE", "info", f"PASSED - Equity: ${sa['equity']:,.2f}")
        except Exception as e:
            self.console_logger.error(f"[SAFE] Failed: {e}")
            return False
        self.console_logger.info("Checking CLASSIC account...")
        try:
            ca = self.classic_client.get_account()
            self.log("CLASSIC", "info", f"PASSED - Equity: ${ca['equity']:,.2f}")
        except Exception as e:
            self.console_logger.error(f"[CLASSIC] Failed: {e}")
            return False
        self.console_logger.info("=" * 70)
        self.console_logger.info("All checks PASSED")
        self.console_logger.info("=" * 70)
        return True

    def is_market_hours(self) -> bool:
        now = datetime.now(ET)
        if now.weekday() >= 5:
            return False
        if now.date() in NYSE_HOLIDAYS_2024_2025:
            return False
        return MARKET_OPEN <= now.time() <= MARKET_CLOSE

    def sync_positions(self, account: str) -> None:
        client = self.safe_client if account == "SAFE" else self.classic_client
        positions = self.safe_positions if account == "SAFE" else self.classic_positions
        try:
            alpaca_positions = client.get_positions()
            found = set()
            for pos in alpaca_positions:
                symbol = pos['symbol']
                found.add(symbol)
                if symbol not in positions:
                    positions[symbol] = {
                        'entry_price': pos['avg_entry_price'],
                        'stop_loss': pos['avg_entry_price'] * (1 - STOP_LOSS_PCT),
                        'shares': int(pos['qty']),
                        'stop_order_id': None,
                        'entry_time': datetime.now(ET)
                    }
                    self.log(account, "info", f"Added position: {symbol} - {positions[symbol]['shares']} @ ${positions[symbol]['entry_price']:.2f}")
                else:
                    positions[symbol]['shares'] = int(pos['qty'])
            for symbol in set(positions.keys()) - found:
                self.log(account, "info", f"Removed closed position: {symbol}")
                del positions[symbol]
            self.log(account, "info", f"Sync complete: {len(positions)} positions")
        except Exception as e:
            self.log(account, "error", f"Sync error: {e}")


    def reconcile_positions(self, account: str) -> None:
        client = self.safe_client if account == "SAFE" else self.classic_client
        positions = self.safe_positions if account == "SAFE" else self.classic_positions
        self.log(account, "info", "Reconciling positions...")
        for symbol, pos_data in positions.items():
            orders = client.get_open_orders(symbol)
            has_stop = any(o['type'] == 'stop' and o['side'] == 'sell' for o in orders)
            if account == "SAFE":
                if has_stop:
                    self.log(account, "info", f"{symbol}: Stop exists - OK")
                    if pos_data.get('stop_order_id') is None:
                        for o in orders:
                            if o['type'] == 'stop' and o['side'] == 'sell':
                                pos_data['stop_order_id'] = o['id']
                                pos_data['stop_loss'] = o['stop_price']
                                break
                else:
                    stop_price = pos_data['stop_loss']
                    self.log(account, "info", f"{symbol}: Creating stop @ ${stop_price:.2f}")
                    stop_id = client.submit_stop_order(symbol, pos_data['shares'], stop_price)
                    if stop_id:
                        pos_data['stop_order_id'] = stop_id
            else:
                if has_stop:
                    self.log(account, "info", f"{symbol}: Cancelling stop (classic mode)")
                    client.cancel_orders_for_symbol(symbol)
                pos_data['stop_order_id'] = None
        self.log(account, "info", "Reconciliation complete")

    def check_exits(self, account: str) -> List[Dict]:
        positions = self.safe_positions if account == "SAFE" else self.classic_positions
        if not positions:
            return []
        symbols = list(positions.keys())
        position_data = self.db.get_position_data(symbols)
        exit_signals = []
        for symbol, pos_info in positions.items():
            if symbol not in position_data:
                continue
            data = position_data[symbol]
            current_price = data['close']
            sma5 = data['sma5']
            entry_price = pos_info['entry_price']
            stop_loss = pos_info['stop_loss']
            shares = pos_info['shares']
            pnl = (current_price - entry_price) * shares
            exit_reason = None
            if account == "SAFE":
                if current_price <= stop_loss:
                    exit_reason = "stop_hit"
                    self.log(account, "info", f"Exit (stop): {symbol} ${current_price:.2f} <= ${stop_loss:.2f}")
                elif current_price > sma5:
                    exit_reason = "sma5_exit"
                    self.log(account, "info", f"Exit (SMA5): {symbol} ${current_price:.2f} > ${sma5:.2f}")
            else:
                if current_price > sma5:
                    exit_reason = "sma5_exit"
                    self.log(account, "info", f"Exit (SMA5): {symbol} ${current_price:.2f} > ${sma5:.2f}")
            if exit_reason:
                exit_signals.append({'symbol': symbol, 'shares': shares, 'current_price': current_price, 'reason': exit_reason, 'pnl': pnl})
        return exit_signals


    def find_entries(self) -> List[Dict]:
        safe_slots = self.max_positions_safe - len(self.safe_positions)
        classic_slots = self.max_positions_classic - len(self.classic_positions)
        if safe_slots <= 0 and classic_slots <= 0:
            self.console_logger.info("No slots available in either account")
            return []
        max_needed = max(safe_slots, classic_slots) * 2
        candidates = self.db.get_entry_candidates(max_crsi=ENTRY_CRSI, min_volume=MIN_VOLUME, min_price=MIN_PRICE, limit=max_needed)
        if not candidates:
            self.console_logger.info("No entry candidates found")
            return []
        owned = set(self.safe_positions.keys()) | set(self.classic_positions.keys())
        candidates = [c for c in candidates if c['symbol'] not in owned]
        if not candidates:
            self.console_logger.info("All candidates already in positions")
            return []
        slots = min(safe_slots, classic_slots) if safe_slots > 0 and classic_slots > 0 else max(safe_slots, classic_slots)
        candidates = candidates[:slots]
        self.console_logger.info(f"Found {len(candidates)} entry candidates")
        return candidates

    def execute_entry(self, account: str, candidate: Dict) -> bool:
        client = self.safe_client if account == "SAFE" else self.classic_client
        positions = self.safe_positions if account == "SAFE" else self.classic_positions
        max_pos = self.max_positions_safe if account == "SAFE" else self.max_positions_classic
        if len(positions) >= max_pos:
            return False
        symbol = candidate['symbol']
        close_price = candidate['close']
        crsi = candidate['crsi']
        try:
            acct = client.get_account()
            bp = acct['buying_power'] * 0.95
            eq_size = acct['equity'] * POSITION_SIZE_PCT
            pos_value = min(bp, eq_size)
        except Exception as e:
            self.log(account, "error", f"Account info failed: {e}")
            return False
        shares = int(pos_value / close_price)
        if shares == 0:
            return False
        self.log(account, "info", f"ENTRY: {symbol} x {shares} @ ~${close_price:.2f} (CRSI={crsi:.2f})")
        client.cancel_orders_for_symbol(symbol)
        if account == "SAFE":
            result = client.submit_bracket_order(symbol, shares, STOP_LOSS_PCT)
        else:
            result = client.submit_simple_order(symbol, shares)
        if result:
            fill_price = result.get('fill_price', close_price)
            if account == "SAFE":
                positions[symbol] = {
                    'entry_price': fill_price,
                    'stop_loss': result.get('stop_price', fill_price * (1 - STOP_LOSS_PCT)),
                    'shares': shares,
                    'stop_order_id': result.get('stop_order_id'),
                    'entry_time': datetime.now(ET)
                }
                self.log(account, "info", f"SUCCESS: {symbol} x {shares} @ ${fill_price:.2f}, stop @ ${positions[symbol]['stop_loss']:.2f}")
            else:
                positions[symbol] = {
                    'entry_price': fill_price,
                    'stop_loss': fill_price * (1 - STOP_LOSS_PCT),
                    'shares': shares,
                    'stop_order_id': None,
                    'entry_time': datetime.now(ET)
                }
                self.log(account, "info", f"SUCCESS: {symbol} x {shares} @ ${fill_price:.2f}, no stop")
            log_trade(account, 'ENTRY', symbol, shares, fill_price, crsi=crsi)
            return True
        self.log(account, "error", f"ENTRY FAILED: {symbol}")
        return False


    def execute_exit(self, account: str, exit_signal: Dict) -> bool:
        client = self.safe_client if account == "SAFE" else self.classic_client
        positions = self.safe_positions if account == "SAFE" else self.classic_positions
        symbol = exit_signal['symbol']
        shares = exit_signal['shares']
        price = exit_signal['current_price']
        reason = exit_signal['reason']
        pnl = exit_signal['pnl']
        self.log(account, "info", f"EXIT: {symbol} x {shares} @ ${price:.2f} ({reason}, P&L=${pnl:+.2f})")
        if client.close_position(symbol):
            hold_min = 0
            if symbol in positions and 'entry_time' in positions[symbol]:
                hold_min = int((datetime.now(ET) - positions[symbol]['entry_time']).total_seconds() / 60)
            log_trade(account, 'EXIT', symbol, shares, price, pnl=pnl, hold_minutes=hold_min)
            if symbol in positions:
                del positions[symbol]
            self.log(account, "info", f"EXIT SUCCESS: {symbol}, P&L=${pnl:+.2f}")
            return True
        self.log(account, "error", f"EXIT FAILED: {symbol}")
        return False

    def run_cycle(self) -> None:
        self.cycle_count += 1
        cycle_start = time.time()
        self.console_logger.info("")
        self.console_logger.info("=" * 70)
        self.console_logger.info(f"CYCLE #{self.cycle_count} - {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.console_logger.info("=" * 70)
        self.sync_positions("SAFE")
        self.sync_positions("CLASSIC")
        safe_exits, safe_entries, safe_pnl = 0, 0, 0.0
        classic_exits, classic_entries, classic_pnl = 0, 0, 0.0
        for es in self.check_exits("SAFE"):
            if self.execute_exit("SAFE", es):
                safe_exits += 1
                safe_pnl += es['pnl']
        for es in self.check_exits("CLASSIC"):
            if self.execute_exit("CLASSIC", es):
                classic_exits += 1
                classic_pnl += es['pnl']
        for cand in self.find_entries():
            if len(self.safe_positions) < self.max_positions_safe:
                if self.execute_entry("SAFE", cand):
                    safe_entries += 1
            if len(self.classic_positions) < self.max_positions_classic:
                if self.execute_entry("CLASSIC", cand):
                    classic_entries += 1
        try:
            safe_eq = self.safe_client.get_account()['equity']
        except:
            safe_eq = 0
        try:
            classic_eq = self.classic_client.get_account()['equity']
        except:
            classic_eq = 0
        dur = time.time() - cycle_start
        safe_session_pnl = get_session_pnl("SAFE")
        classic_session_pnl = get_session_pnl("CLASSIC")
        self.console_logger.info("")
        self.console_logger.info("-" * 70)
        self.console_logger.info("CYCLE SUMMARY")
        self.console_logger.info("-" * 70)
        self.console_logger.info(f"{'Account':<12} {'Equity':>12} {'Positions':>12} {'Entries':>10} {'Exits':>10} {'P&L':>12}")
        self.console_logger.info(f"{'-'*12} {'-'*12} {'-'*12} {'-'*10} {'-'*10} {'-'*12}")
        self.console_logger.info(f"{'SAFE':<12} ${safe_eq:>10,.2f} {len(self.safe_positions):>10}/{self.max_positions_safe} {safe_entries:>10} {safe_exits:>10} ${safe_pnl:>+10,.2f}")
        self.console_logger.info(f"{'CLASSIC':<12} ${classic_eq:>10,.2f} {len(self.classic_positions):>10}/{self.max_positions_classic} {classic_entries:>10} {classic_exits:>10} ${classic_pnl:>+10,.2f}")
        self.console_logger.info("-" * 70)
        self.console_logger.info(f"SESSION P&L:  SAFE ${safe_session_pnl:>+10,.2f}  |  CLASSIC ${classic_session_pnl:>+10,.2f}")
        self.console_logger.info("-" * 70)
        self.console_logger.info(f"Cycle Duration: {dur:.2f}s")
        self.safe_logger.info(f"Cycle #{self.cycle_count}: Eq=${safe_eq:,.2f}, Pos={len(self.safe_positions)}, E={safe_entries}, X={safe_exits}, P&L=${safe_pnl:+,.2f}")
        self.classic_logger.info(f"Cycle #{self.cycle_count}: Eq=${classic_eq:,.2f}, Pos={len(self.classic_positions)}, E={classic_entries}, X={classic_exits}, P&L=${classic_pnl:+,.2f}")


    def run(self) -> None:
        self.console_logger.info("")
        self.console_logger.info("=" * 70)
        self.console_logger.info("CONNORS RSI TRADING BOT - DUAL MODE")
        self.console_logger.info("=" * 70)
        self.console_logger.info(f"Started: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.console_logger.info(f"Strategy: Entry CRSI <= {ENTRY_CRSI}, Exit Close > SMA5")
        self.console_logger.info(f"Position Size: {POSITION_SIZE_PCT*100:.0f}% per position")
        self.console_logger.info("")
        self.console_logger.info("SAFE Account:")
        self.console_logger.info(f"  Max Positions: {self.max_positions_safe}")
        self.console_logger.info(f"  Stop Loss: {STOP_LOSS_PCT*100:.0f}% (bracket orders)")
        self.console_logger.info("")
        self.console_logger.info("CLASSIC Account:")
        self.console_logger.info(f"  Max Positions: {self.max_positions_classic}")
        self.console_logger.info(f"  Stop Loss: None (original Connors)")
        self.console_logger.info("")
        self.console_logger.info(f"Cycle Interval: {CYCLE_INTERVAL_MINUTES} minutes")
        self.console_logger.info("=" * 70)
        if not self.startup_checks():
            self.console_logger.error("Startup checks failed. Exiting.")
            return
        self.sync_positions("SAFE")
        self.sync_positions("CLASSIC")
        self.reconcile_positions("SAFE")
        self.reconcile_positions("CLASSIC")
        while not self.is_market_hours():
            now = datetime.now(ET)
            self.console_logger.info(f"Market closed. Current: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}. Waiting...")
            time.sleep(60)
        self.console_logger.info("Market OPEN. Starting cycles...")
        self.running = True
        sync_file = Path(SYNC_COMPLETE_FILE)
        last_mtime = sync_file.stat().st_mtime if sync_file.exists() else 0
        self.console_logger.info(f"Watching: {sync_file}")
        try:
            while self.running:
                if not self.is_market_hours():
                    self.console_logger.info("Market closed. Stopping.")
                    break
                if sync_file.exists():
                    curr_mtime = sync_file.stat().st_mtime
                    if curr_mtime > last_mtime:
                        self.console_logger.info("Sync detected")
                        last_mtime = curr_mtime
                        try:
                            self.run_cycle()
                        except Exception as e:
                            self.console_logger.error(f"Cycle error: {e}", exc_info=True)
                time.sleep(5)
        except KeyboardInterrupt:
            self.console_logger.info("")
            self.console_logger.info("=" * 70)
            self.console_logger.info("SHUTDOWN (Ctrl+C)")
            self.console_logger.info("=" * 70)
            self.running = False
        self.console_logger.info("")
        self.console_logger.info("=" * 70)
        self.console_logger.info("END OF DAY SUMMARY")
        self.console_logger.info("=" * 70)
        self.console_logger.info(f"Total Cycles: {self.cycle_count}")
        try:
            sa = self.safe_client.get_account()
            self.console_logger.info(f"[SAFE] Final Equity: ${sa['equity']:,.2f}, Positions: {len(self.safe_positions)}")
        except:
            pass
        try:
            ca = self.classic_client.get_account()
            self.console_logger.info(f"[CLASSIC] Final Equity: ${ca['equity']:,.2f}, Positions: {len(self.classic_positions)}")
        except:
            pass
        self.console_logger.info(f"Ended: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.console_logger.info("=" * 70)
        self.console_logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    bot = ConnorsBot(paper=True)
    bot.run()
