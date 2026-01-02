"""
Trading Bot V3 (LONG ONLY)

Orchestrates 3 trading strategies:
- VWAP_RSI2_SWING: VWAP + RSI(2) swing (holds overnight, exits next AM)
- VWAP_PULLBACK: Mid-day mean reversion (10:00 AM - 2:00 PM)
- ORB_15MIN: 15-min Opening Range Breakout (9:45-11:00 AM)

Each strategy runs on its own Alpaca paper trading account.
All strategies are LONG ONLY (no shorting, no margin required).

Usage:
    python intraday_bot.py [--paper]
"""

import sys
import os
import time as time_module
import signal
import logging
import csv
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    StrategyType, STRATEGY_CONFIG, ACCOUNTS,
    INTRADAY_DB_PATH, SYNC_COMPLETE_FILE,
    MARKET_OPEN, MARKET_CLOSE,
    CYCLE_INTERVAL_MINUTES, MIN_PRICE,
    LOG_DIR, ET,
)
from data.intraday_indicators import IntradayIndicators
from strategies import VwapRsi2SwingStrategy, VWAPPullbackStrategy, ORB15MinStrategy
from data.indicators_db import IndicatorsDB
from strategies.base_strategy import EntrySignal, ExitSignal
from execution.alpaca_client import AlpacaClient


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(strategy_name: str) -> logging.Logger:
    """Create a logger for a specific strategy."""
    logger = logging.getLogger(f"intraday.{strategy_name}")
    logger.setLevel(logging.DEBUG)

    # File handler
    log_file = LOG_DIR / f"trading_{strategy_name.lower()}.log"
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger


def setup_console_logger() -> logging.Logger:
    """Create a console logger for unified output."""
    logger = logging.getLogger("intraday.console")
    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    return logger


# =============================================================================
# Position Tracking
# =============================================================================

@dataclass
class Position:
    """Tracks an open position."""
    symbol: str
    shares: int
    entry_price: float
    entry_time: datetime
    strategy: str
    direction: str = 'long'  # 'long' or 'short'
    target: Optional[float] = None
    stop: Optional[float] = None
    metadata: Dict = field(default_factory=dict)


# =============================================================================
# Intraday Bot
# =============================================================================

class IntradayBot:
    """
    Main orchestrator for 3-strategy intraday trading.

    Manages:
    - 3 Alpaca clients (one per strategy/account)
    - 3 Strategy instances
    - Position tracking per account
    - Trade journaling
    - EOD position closure
    """

    def __init__(self, paper: bool = True):
        """
        Initialize the bot.

        Args:
            paper: Use paper trading accounts (default True)
        """
        self.paper = paper
        self.running = False
        self.session_start: Optional[datetime] = None
        self.cycle_count = 0

        # Console logger (unified output)
        self.console = setup_console_logger()

        # Initialize shared data layer
        self.console.info("Initializing data layer...")
        self.indicators = IntradayIndicators(INTRADAY_DB_PATH)

        # Initialize clients, strategies, positions, and loggers for each account
        self.clients: Dict[StrategyType, AlpacaClient] = {}
        self.strategies: Dict[StrategyType, object] = {}
        self.positions: Dict[StrategyType, Dict[str, Position]] = {}
        self.loggers: Dict[StrategyType, logging.Logger] = {}
        self.session_pnl: Dict[StrategyType, float] = {}

        # Track which strategies have had EOD exits triggered today
        # This prevents repeated exit attempts and allows safety EOD logic
        self._eod_exits_triggered: Dict[StrategyType, datetime] = {}

        self._init_vwap_rsi2_swing(paper)
        self._init_vwap_pullback(paper)
        self._init_orb_15min(paper)

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _init_vwap_rsi2_swing(self, paper: bool):
        """Initialize VWAP + RSI(2) Swing strategy components."""
        config = STRATEGY_CONFIG[StrategyType.VWAP_RSI2_SWING]
        account = ACCOUNTS[StrategyType.VWAP_RSI2_SWING]

        self.clients[StrategyType.VWAP_RSI2_SWING] = AlpacaClient(
            paper=paper,
            api_key=account["api_key"],
            secret_key=account["secret_key"],
            name="VWAP_RSI2_SWING"
        )
        # Initialize IndicatorsDB for RSI2/CRSI/SMA200/ADX access
        indicators_db = IndicatorsDB()
        self.strategies[StrategyType.VWAP_RSI2_SWING] = VwapRsi2SwingStrategy(
            indicators=self.indicators,
            indicators_db=indicators_db,
            max_positions=config["max_positions"],
            position_size_pct=config["position_size_pct"],
            risk_per_trade_pct=config["risk_per_trade_pct"],
            eod_exit_time=config["eod_exit_time"],
            min_price=MIN_PRICE,
        )
        self.positions[StrategyType.VWAP_RSI2_SWING] = {}
        self.loggers[StrategyType.VWAP_RSI2_SWING] = setup_logging("VWAP_RSI2_SWING")
        self.session_pnl[StrategyType.VWAP_RSI2_SWING] = 0.0

    def _init_vwap_pullback(self, paper: bool):
        """Initialize VWAP Pullback strategy components."""
        config = STRATEGY_CONFIG[StrategyType.VWAP_PULLBACK]
        account = ACCOUNTS[StrategyType.VWAP_PULLBACK]

        self.clients[StrategyType.VWAP_PULLBACK] = AlpacaClient(
            paper=paper,
            api_key=account["api_key"],
            secret_key=account["secret_key"],
            name="VWAP_PULLBACK"
        )
        self.strategies[StrategyType.VWAP_PULLBACK] = VWAPPullbackStrategy(
            indicators=self.indicators,
            max_positions=config["max_positions"],
            position_size_pct=config["position_size_pct"],
            risk_per_trade_pct=config["risk_per_trade_pct"],
            eod_exit_time=config["eod_exit_time"],
            min_price=config.get("min_price", 10.0),
            min_avg_volume=config.get("min_avg_volume", 500_000),
        )
        self.positions[StrategyType.VWAP_PULLBACK] = {}
        self.loggers[StrategyType.VWAP_PULLBACK] = setup_logging("VWAP_PULLBACK")
        self.session_pnl[StrategyType.VWAP_PULLBACK] = 0.0

    def _init_orb_15min(self, paper: bool):
        """Initialize ORB 15-Min strategy components."""
        config = STRATEGY_CONFIG[StrategyType.ORB_15MIN]
        account = ACCOUNTS[StrategyType.ORB_15MIN]

        self.clients[StrategyType.ORB_15MIN] = AlpacaClient(
            paper=paper,
            api_key=account["api_key"],
            secret_key=account["secret_key"],
            name="ORB_15MIN"
        )
        self.strategies[StrategyType.ORB_15MIN] = ORB15MinStrategy(
            indicators=self.indicators,
            max_positions=config["max_positions"],
            position_size_pct=config["position_size_pct"],
            risk_per_trade_pct=config["risk_per_trade_pct"],
            eod_exit_time=config["eod_exit_time"],
            min_price=MIN_PRICE,
            min_range_pct=config.get("min_range_pct", 0.003),
            max_range_pct=config.get("max_range_pct", 0.015),
            min_relative_volume=config.get("min_relative_volume", 1.5),
        )
        self.positions[StrategyType.ORB_15MIN] = {}
        self.loggers[StrategyType.ORB_15MIN] = setup_logging("ORB_15MIN")
        self.session_pnl[StrategyType.ORB_15MIN] = 0.0

    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        self.console.info("\nShutdown signal received. Stopping bot...")
        self.running = False

    # =========================================================================
    # Startup Checks
    # =========================================================================

    def startup_checks(self) -> bool:
        """
        Validate all dependencies before trading.

        Returns:
            True if all checks pass, False otherwise
        """
        self.console.info("=" * 60)
        self.console.info("INTRADAY BOT V2 - STARTUP CHECKS")
        self.console.info("=" * 60)

        all_ok = True

        # Check database
        all_ok &= self._check_database()

        # Check each account
        for strategy_type in StrategyType:
            all_ok &= self._check_account(strategy_type)

        if all_ok:
            self.console.info("-" * 60)
            self.console.info("All startup checks PASSED")
            self.console.info("=" * 60)
        else:
            self.console.error("Startup checks FAILED - cannot continue")

        return all_ok

    def _check_database(self) -> bool:
        """Check database connectivity and data freshness."""
        try:
            stats = self.indicators.get_stats()
            self.console.info(f"[DB] Connected: {stats['symbol_count']:,} symbols, "
                            f"{stats['total_bars']:,} bars")

            # Check data freshness (should be within last hour during market hours)
            if stats['max_date']:
                age = datetime.now() - stats['max_date']
                if age > timedelta(hours=2):
                    self.console.warning(f"[DB] Data may be stale: last update {stats['max_date']}")
                else:
                    self.console.info(f"[DB] Data fresh: last update {stats['max_date']}")

            return True

        except Exception as e:
            self.console.error(f"[DB] Connection failed: {e}")
            return False

    def _check_account(self, strategy_type: StrategyType) -> bool:
        """Check Alpaca account connectivity."""
        name = strategy_type.value.upper()
        client = self.clients[strategy_type]

        try:
            account = client.get_account()
            if account:
                equity = float(account.get('equity', 0))
                self.console.info(f"[{name}] Connected: ${equity:,.2f} equity")
                return True
            else:
                self.console.error(f"[{name}] Failed to get account info")
                return False

        except Exception as e:
            self.console.error(f"[{name}] Connection failed: {e}")
            return False

    # =========================================================================
    # Position Sync
    # =========================================================================

    def sync_positions(self, strategy_type: StrategyType):
        """
        Sync positions from Alpaca to internal tracking.

        Args:
            strategy_type: Which strategy/account to sync
        """
        name = strategy_type.value.upper()
        client = self.clients[strategy_type]
        logger = self.loggers[strategy_type]

        try:
            alpaca_positions = client.get_positions()
            if alpaca_positions is None:
                logger.warning(f"[{name}] Failed to get positions from Alpaca")
                return

            # Build set of symbols we have
            current_symbols = set(self.positions[strategy_type].keys())
            alpaca_symbols = {p['symbol'] for p in alpaca_positions}

            # Add new positions from Alpaca
            for pos in alpaca_positions:
                symbol = pos['symbol']
                if symbol not in self.positions[strategy_type]:
                    qty = int(pos['qty'])
                    direction = 'short' if qty < 0 else 'long'
                    # Position exists in Alpaca but not tracked - add it
                    self.positions[strategy_type][symbol] = Position(
                        symbol=symbol,
                        shares=abs(qty),
                        entry_price=float(pos['avg_entry_price']),
                        entry_time=datetime.now(),  # Unknown, use now
                        strategy=name,
                        direction=direction,
                    )
                    logger.info(f"[{name}] Synced existing position: {symbol} "
                              f"{qty} shares @ ${pos['avg_entry_price']} ({direction})")

            # Remove positions closed outside bot
            for symbol in current_symbols - alpaca_symbols:
                del self.positions[strategy_type][symbol]
                logger.info(f"[{name}] Removed stale position: {symbol}")

        except Exception as e:
            logger.error(f"[{name}] Position sync error: {e}")

    def sync_all_positions(self):
        """Sync positions for all strategies."""
        for strategy_type in StrategyType:
            self.sync_positions(strategy_type)

    # =========================================================================
    # Trading Cycle
    # =========================================================================

    def run_cycle(self):
        """Execute one trading cycle for all strategies."""
        cycle_start = datetime.now()
        self.cycle_count += 1

        self.console.info("-" * 60)
        self.console.info(f"CYCLE {self.cycle_count} - {cycle_start.strftime('%H:%M:%S')}")
        self.console.info("-" * 60)

        # Sync positions first
        self.sync_all_positions()

        # Process each strategy
        for strategy_type in StrategyType:
            self._process_strategy(strategy_type)

        # Cycle summary
        self._log_cycle_summary(cycle_start)

    def _process_strategy(self, strategy_type: StrategyType):
        """Process exits and entries for one strategy."""
        name = strategy_type.value.upper()
        client = self.clients[strategy_type]
        strategy = self.strategies[strategy_type]
        positions = self.positions[strategy_type]
        logger = self.loggers[strategy_type]
        config = STRATEGY_CONFIG[strategy_type]

        # Check EOD exit time (in ET)
        now_et = datetime.now(ET)
        if now_et.time() >= config["eod_exit_time"]:
            self._force_eod_exits(strategy_type)
            return  # No new entries after EOD exit time

        # Check exits
        exits_executed = 0
        for symbol in list(positions.keys()):
            position = positions[symbol]
            exit_signal = strategy.check_exit(symbol, {
                'entry_price': position.entry_price,
                'shares': position.shares,
                'entry_time': position.entry_time,
                'target': position.target,
                'stop': position.stop,
                'direction': position.direction,
            })

            if exit_signal:
                success = self._execute_exit(strategy_type, symbol, exit_signal)
                if success:
                    exits_executed += 1

        # Check entries (only if we have room)
        available_slots = config["max_positions"] - len(positions)
        if available_slots > 0:
            candidates = strategy.get_candidates()

            # Filter out symbols we already own
            candidates = [c for c in candidates if c.symbol not in positions]

            # Take top candidates up to available slots
            for candidate in candidates[:available_slots]:
                success = self._execute_entry(strategy_type, candidate)
                if success:
                    available_slots -= 1
                    if available_slots <= 0:
                        break

        logger.info(f"[{name}] Cycle complete: {len(positions)} positions, "
                   f"{exits_executed} exits")

    def _force_eod_exits(self, strategy_type: StrategyType):
        """Force close all positions at EOD."""
        name = strategy_type.value.upper()
        positions = self.positions[strategy_type]
        logger = self.loggers[strategy_type]

        if not positions:
            return

        self.console.info(f"[{name}] EOD EXIT: Closing {len(positions)} positions")

        for symbol in list(positions.keys()):
            position = positions[symbol]
            current_price = self.indicators.get_current_price(symbol) or position.entry_price

            # Calculate P&L based on direction
            if position.direction == 'long':
                pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
            else:
                pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100

            exit_signal = ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
            )
            self._execute_exit(strategy_type, symbol, exit_signal)

    def _check_safety_eod_exits(self):
        """
        Safety check for EOD exits - runs every loop iteration.

        This ensures positions are closed at EOD even if the sync file
        doesn't update. Prevents positions from being held overnight.
        """
        now_et = datetime.now(ET)
        today = now_et.date()

        for strategy_type in StrategyType:
            config = STRATEGY_CONFIG[strategy_type]
            eod_time = config["eod_exit_time"]

            # Skip if not past EOD time yet
            if now_et.time() < eod_time:
                continue

            # Skip if we already triggered EOD exit for this strategy today
            if strategy_type in self._eod_exits_triggered:
                if self._eod_exits_triggered[strategy_type].date() == today:
                    continue

            # We're past EOD time and haven't triggered exits today
            positions = self.positions[strategy_type]
            if positions:
                name = strategy_type.value.upper()
                self.console.info(f"[{name}] SAFETY EOD EXIT: Time {now_et.time()} >= {eod_time}")
                self._force_eod_exits(strategy_type)

            # Mark as triggered for today (even if no positions)
            self._eod_exits_triggered[strategy_type] = now_et

    def _execute_entry(self, strategy_type: StrategyType, signal: EntrySignal) -> bool:
        """Execute an entry order."""
        name = strategy_type.value.upper()
        client = self.clients[strategy_type]
        logger = self.loggers[strategy_type]
        config = STRATEGY_CONFIG[strategy_type]

        try:
            # Get account equity for position sizing
            account = client.get_account()
            if not account:
                logger.error(f"[{name}] Cannot get account for sizing")
                return False

            equity = float(account.get('equity', 0))
            strategy = self.strategies[strategy_type]

            # Calculate shares
            shares = strategy.calculate_position_size(
                equity, signal.price, signal.stop
            )

            if shares <= 0:
                logger.warning(f"[{name}] Position size too small for {signal.symbol}")
                return False

            # Determine direction from signal metadata
            direction = signal.metadata.get('direction', 'long') if signal.metadata else 'long'
            side = 'buy' if direction == 'long' else 'sell'

            # Submit order
            logger.info(f"[{name}] SUBMITTING: {signal.symbol} {side} {shares} shares (signal ~${signal.price:.2f})")
            self.console.info(f"[{name}] SUBMITTING: {signal.symbol} {side.upper()} {shares} shares (signal ~${signal.price:.2f})")

            result = client.submit_simple_order(signal.symbol, shares, side=side)

            if result and result.get('fill_price'):
                fill_price = result['fill_price']
                filled_qty = result.get('qty', shares)

                # Use signal's target/stop (strategies handle their own calculations)
                adjusted_target = signal.target
                adjusted_stop = signal.stop

                # For ORB_15MIN: Recalculate target from actual fill price
                # Target = fill_price + (range_size * 1.0)
                if strategy_type == StrategyType.ORB_15MIN:
                    range_size = signal.metadata.get('range_size') if signal.metadata else None
                    if range_size:
                        TARGET_MULTIPLIER = 1.0  # 100% of range height
                        adjusted_target = fill_price + (range_size * TARGET_MULTIPLIER)
                        logger.info(f"[{name}] Target for {signal.symbol}: ${adjusted_target:.2f} "
                                  f"(fill=${fill_price:.2f} + {TARGET_MULTIPLIER:.0%} of range=${range_size:.2f})")

                # Safety check: target must be above entry for long positions
                if direction == 'long' and adjusted_target and adjusted_target <= fill_price:
                    logger.error(f"[{name}] Invalid target ${adjusted_target:.2f} <= entry ${fill_price:.2f}, "
                               f"setting minimum target")
                    adjusted_target = fill_price * 1.005  # 0.5% minimum target

                # Track position
                self.positions[strategy_type][signal.symbol] = Position(
                    symbol=signal.symbol,
                    shares=filled_qty,
                    entry_price=fill_price,
                    entry_time=datetime.now(),
                    strategy=name,
                    direction=direction,
                    target=adjusted_target,
                    stop=adjusted_stop,
                    metadata=signal.metadata or {},
                )

                # Record trade in strategy's daily tracker
                self.strategies[strategy_type].record_entry(signal.symbol)

                # Log trade
                self._log_trade(strategy_type, signal.symbol, 'ENTRY',
                              filled_qty, fill_price, 0, signal.reason, direction=direction)

                # Calculate and log slippage
                slippage_dollars = fill_price - signal.price
                slippage_pct = (slippage_dollars / signal.price) * 100
                logger.info(f"[{name}] ENTRY FILLED: {signal.symbol} {filled_qty} @ ${fill_price:.2f} ({direction})")
                logger.info(f"[{name}] Slippage: ${slippage_dollars:+.2f} ({slippage_pct:+.2f}%) "
                           f"[signal=${signal.price:.2f}, fill=${fill_price:.2f}]")
                self.console.info(f"[{name}] ENTRY FILLED: {signal.symbol} {filled_qty} @ ${fill_price:.2f} "
                                 f"(slippage {slippage_pct:+.2f}%)")
                return True
            else:
                logger.error(f"[{name}] Order failed for {signal.symbol}")
                return False

        except Exception as e:
            logger.error(f"[{name}] Entry error for {signal.symbol}: {e}")
            return False

    def _execute_exit(self, strategy_type: StrategyType, symbol: str,
                     signal: ExitSignal) -> bool:
        """Execute an exit order."""
        name = strategy_type.value.upper()
        client = self.clients[strategy_type]
        logger = self.loggers[strategy_type]
        positions = self.positions[strategy_type]

        if symbol not in positions:
            return False

        position = positions[symbol]

        try:
            logger.info(f"[{name}] EXIT: {symbol} ({signal.reason}) "
                       f"P&L: {signal.pnl_pct:+.2f}%")
            self.console.info(f"[{name}] EXIT: {symbol} ({signal.reason}) "
                            f"P&L: {signal.pnl_pct:+.2f}%")

            result = client.close_position(symbol)

            if result:
                # Use actual fill price from Alpaca, fallback to signal price
                exit_price = result.get('fill_price') or signal.price

                # Calculate P&L based on direction using ACTUAL fill price
                if position.direction == 'long':
                    pnl = (exit_price - position.entry_price) * position.shares
                else:
                    pnl = (position.entry_price - exit_price) * position.shares

                hold_minutes = (datetime.now() - position.entry_time).total_seconds() / 60

                # Update session P&L
                self.session_pnl[strategy_type] += pnl

                # Log trade with actual fill price
                self._log_trade(strategy_type, symbol, 'EXIT',
                              position.shares, exit_price, pnl, signal.reason,
                              hold_minutes=hold_minutes, direction=position.direction)

                # Remove from tracking
                del positions[symbol]

                # Calculate and log slippage
                slippage_dollars = exit_price - signal.price
                slippage_pct = (slippage_dollars / signal.price) * 100 if signal.price > 0 else 0
                logger.info(f"[{name}] CLOSED: {symbol} @ ${exit_price:.2f} P&L: ${pnl:+.2f} "
                           f"(held {hold_minutes:.0f} min, {position.direction})")
                logger.info(f"[{name}] Slippage: ${slippage_dollars:+.2f} ({slippage_pct:+.2f}%) "
                           f"[signal=${signal.price:.2f}, fill=${exit_price:.2f}]")
                return True
            else:
                logger.error(f"[{name}] Failed to close {symbol}")
                return False

        except Exception as e:
            logger.error(f"[{name}] Exit error for {symbol}: {e}")
            return False

    # =========================================================================
    # Trade Journaling
    # =========================================================================

    def _log_trade(self, strategy_type: StrategyType, symbol: str, action: str,
                   shares: int, price: float, pnl: float, reason: str,
                   hold_minutes: float = 0, direction: str = 'long'):
        """Log a trade to the CSV journal."""
        name = strategy_type.value.lower()
        journal_file = LOG_DIR / f"trade_journal_{name}.csv"

        # Create file with headers if needed
        if not journal_file.exists():
            with open(journal_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'action', 'direction', 'shares', 'price',
                    'pnl', 'reason', 'hold_minutes'
                ])

        # Append trade
        with open(journal_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                symbol,
                action,
                direction,
                shares,
                f"{price:.2f}",
                f"{pnl:.2f}",
                reason,
                f"{hold_minutes:.1f}",
            ])

    def _log_cycle_summary(self, cycle_start: datetime):
        """Log a summary of the cycle."""
        cycle_duration = (datetime.now() - cycle_start).total_seconds()

        self.console.info("")
        self.console.info("CYCLE SUMMARY:")
        self.console.info(f"{'Strategy':<20} {'Positions':<10} {'Session P&L':<15}")
        self.console.info("-" * 50)

        total_pnl = 0
        for strategy_type in StrategyType:
            name = strategy_type.value.upper()
            pos_count = len(self.positions[strategy_type])
            pnl = self.session_pnl[strategy_type]
            total_pnl += pnl
            self.console.info(f"{name:<20} {pos_count:<10} ${pnl:>+12,.2f}")

        self.console.info("-" * 50)
        self.console.info(f"{'TOTAL':<20} {'':<10} ${total_pnl:>+12,.2f}")
        self.console.info(f"Cycle duration: {cycle_duration:.1f}s")

    def _log_end_of_day(self):
        """Log end of day summary."""
        self.console.info("")
        self.console.info("=" * 60)
        self.console.info("END OF DAY SUMMARY")
        self.console.info("=" * 60)

        for strategy_type in StrategyType:
            name = strategy_type.value.upper()
            pnl = self.session_pnl[strategy_type]
            account = self.clients[strategy_type].get_account()
            equity = float(account.get('equity', 0)) if account else 0

            self.console.info(f"[{name}] Equity: ${equity:,.2f} | Session P&L: ${pnl:+,.2f}")

        total_pnl = sum(self.session_pnl.values())
        self.console.info("-" * 60)
        self.console.info(f"Total Session P&L: ${total_pnl:+,.2f}")
        self.console.info(f"Total Cycles: {self.cycle_count}")
        self.console.info("=" * 60)

    # =========================================================================
    # Main Loop
    # =========================================================================

    def wait_for_market_open(self):
        """Wait until market opens (blocks until market is open)."""
        while self.running:
            now_et = datetime.now(ET)

            # Check if it's a weekend
            if now_et.weekday() >= 5:
                self.console.info("Weekend detected. Market closed until Monday.")
                return False

            current_time = now_et.time()

            if current_time >= MARKET_CLOSE:
                self.console.info("Market closed for today.")
                return False

            if current_time >= MARKET_OPEN:
                # Market is open!
                return True

            # Before market open - wait
            market_open_dt = now_et.replace(hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute, second=0, microsecond=0)
            wait_seconds = (market_open_dt - now_et).total_seconds()
            wait_minutes = wait_seconds / 60

            if wait_minutes > 1:
                self.console.info(f"Market opens at {MARKET_OPEN}. Waiting {wait_minutes:.0f} minutes...")
                # Sleep in 60-second intervals to allow Ctrl+C
                time_module.sleep(min(60, wait_seconds))
            else:
                self.console.info(f"Market opens in {wait_seconds:.0f} seconds...")
                time_module.sleep(wait_seconds)

        return False

    def is_market_hours(self) -> bool:
        """Check if we're within market hours (Eastern Time)."""
        now_et = datetime.now(ET)
        if now_et.weekday() >= 5:  # Weekend
            return False
        current_time = now_et.time()
        return MARKET_OPEN <= current_time < MARKET_CLOSE

    def get_sync_file_mtime(self) -> Optional[float]:
        """Get the modification time of the sync file."""
        try:
            if os.path.exists(SYNC_COMPLETE_FILE):
                return os.path.getmtime(SYNC_COMPLETE_FILE)
        except Exception:
            pass
        return None

    def run(self):
        """Main bot loop."""
        self.console.info("")
        self.console.info("=" * 60)
        self.console.info("INTRADAY TRADING BOT V3 (LONG ONLY)")
        self.console.info("3 Strategies | 3 Accounts | Intraday Only")
        self.console.info("=" * 60)
        self.console.info("")
        self.console.info("Strategies:")
        self.console.info("  - VWAP_RSI2_SWING: RSI(2) oversold + VWAP (holds overnight)")
        self.console.info("  - VWAP_PULLBACK: Mid-day mean reversion (10 AM-2 PM)")
        self.console.info("  - ORB_15MIN: 15-min ORB breakout (9:45-11 AM)")
        self.console.info("")

        # Startup checks
        if not self.startup_checks():
            self.console.error("Startup checks failed. Exiting.")
            return

        self.running = True

        # Wait for market open (blocks until open)
        if not self.wait_for_market_open():
            self.console.info("Market closed. Exiting.")
            return
        self.session_start = datetime.now()
        last_sync_mtime = self.get_sync_file_mtime()

        self.console.info("")
        self.console.info("Bot started. Watching for sync updates...")
        self.console.info(f"Cycle interval: {CYCLE_INTERVAL_MINUTES} minutes")
        self.console.info("Press Ctrl+C to stop")
        self.console.info("")

        # Initial sync
        self.sync_all_positions()

        while self.running and self.is_market_hours():
            try:
                # Safety EOD check - runs every iteration regardless of sync
                # This ensures positions are closed even if VV7 stops syncing
                self._check_safety_eod_exits()

                # Check for sync file update
                current_mtime = self.get_sync_file_mtime()

                if current_mtime and current_mtime != last_sync_mtime:
                    last_sync_mtime = current_mtime
                    self.run_cycle()

                # Sleep briefly to avoid busy-waiting
                time_module.sleep(5)

            except Exception as e:
                self.console.error(f"Cycle error: {e}")
                import traceback
                traceback.print_exc()
                time_module.sleep(30)

        # End of day
        self._log_end_of_day()
        self.console.info("Bot stopped.")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Intraday Trading Bot V2")
    parser.add_argument('--paper', action='store_true', default=True,
                       help="Use paper trading (default: True)")
    parser.add_argument('--live', action='store_true',
                       help="Use live trading (CAUTION)")

    args = parser.parse_args()
    paper = not args.live

    if not paper:
        print("=" * 60)
        print("WARNING: LIVE TRADING MODE")
        print("Real money will be used!")
        print("=" * 60)
        confirm = input("Type 'CONFIRM' to proceed: ")
        if confirm != 'CONFIRM':
            print("Aborted.")
            return

    bot = IntradayBot(paper=paper)
    bot.run()


if __name__ == "__main__":
    main()
