"""
Connors RSI Trading Bot - Main Orchestrator

This module implements the main trading bot that coordinates all components:
- Database access for indicator screening
- Alpaca API for trade execution
- Position tracking and risk management
- Market hours scheduling

The bot runs a continuous cycle during market hours:
1. Sync positions with broker
2. Check exit conditions for existing positions
3. Find new entry candidates
4. Execute trades and update position tracking
"""

import logging
import time
import sys
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from blessed import Terminal

from config import (
    CAPITAL,
    POSITION_SIZE_PCT,
    MAX_POSITIONS,
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
    MODE_INFO
)
from data.indicators_db import IndicatorsDB
from execution.alpaca_client import AlpacaClient

# NYSE Market Holidays for 2024-2025
NYSE_HOLIDAYS_2024_2025 = {
    # 2024
    datetime(2024, 1, 1).date(),   # New Year's Day
    datetime(2024, 1, 15).date(),  # Martin Luther King Jr. Day
    datetime(2024, 2, 19).date(),  # Presidents' Day
    datetime(2024, 3, 29).date(),  # Good Friday
    datetime(2024, 5, 27).date(),  # Memorial Day
    datetime(2024, 6, 19).date(),  # Juneteenth
    datetime(2024, 7, 4).date(),   # Independence Day
    datetime(2024, 9, 2).date(),   # Labor Day
    datetime(2024, 11, 28).date(), # Thanksgiving
    datetime(2024, 12, 25).date(), # Christmas
    # 2025
    datetime(2025, 1, 1).date(),   # New Year's Day
    datetime(2025, 1, 20).date(),  # Martin Luther King Jr. Day
    datetime(2025, 2, 17).date(),  # Presidents' Day
    datetime(2025, 4, 18).date(),  # Good Friday
    datetime(2025, 5, 26).date(),  # Memorial Day
    datetime(2025, 6, 19).date(),  # Juneteenth
    datetime(2025, 7, 4).date(),   # Independence Day
    datetime(2025, 9, 1).date(),   # Labor Day
    datetime(2025, 11, 27).date(), # Thanksgiving
    datetime(2025, 12, 25).date(), # Christmas
}


def render_mode_menu(term: Terminal, selected_index: int) -> None:
    """
    Render the mode selection box with highlighting.

    Displays both trading modes with their features in a formatted box.
    The selected mode is highlighted with a '>' prefix and bold/green styling.

    Args:
        term: Blessed Terminal instance
        selected_index: Index of currently selected mode (0=SAFE, 1=CLASSIC)
    """
    modes = [TradingMode.SAFE, TradingMode.CLASSIC]

    print(term.clear())
    print("=" * 70)
    print("                    SELECT TRADING MODE")
    print("=" * 70)
    print()
    print("  " + "\u250c" + "\u2500" * 65 + "\u2510")
    print("  \u2502" + " " * 65 + "\u2502")

    for idx, mode in enumerate(modes):
        mode_data = MODE_INFO[mode]
        is_selected = (idx == selected_index)

        # Mode header with selection indicator
        selector = ">" if is_selected else " "
        mode_header_text = f"   {selector} {mode_data['name']} ({mode_data['subtitle']})"

        if is_selected:
            # Calculate padding needed (total width 65 - actual text length)
            # We need to account for ANSI escape sequences not contributing to visible width
            plain_text_len = len(mode_header_text)
            padding = 65 - plain_text_len
            print(f"  \u2502 {term.bold_green(mode_header_text)}{' ' * padding}\u2502")
        else:
            print(f"  \u2502 {mode_header_text:<65}\u2502")

        # Features
        for i, (feature_name, feature_value) in enumerate(mode_data['features']):
            if i == 0:
                prefix = "\u251c\u2500"
            elif i == len(mode_data['features']) - 1:
                prefix = "\u2514\u2500"
            else:
                prefix = "\u251c\u2500"

            feature_text = f"     {prefix} {feature_name}: {feature_value}"

            if is_selected:
                # Calculate padding for colored text
                plain_text_len = len(feature_text)
                padding = 65 - plain_text_len
                print(f"  \u2502 {term.green(feature_text)}{' ' * padding}\u2502")
            else:
                print(f"  \u2502 {feature_text:<65}\u2502")

        print("  \u2502" + " " * 65 + "\u2502")

    print("  " + "\u2514" + "\u2500" * 65 + "\u2518")
    print()
    print("        \u2191/\u2193 to select    ENTER to confirm    ESC to quit")
    print()
    print("=" * 70)


def select_trading_mode() -> TradingMode:
    """
    Interactive mode selector with arrow keys.

    Displays a formatted menu allowing the user to choose between SAFE and CLASSIC
    trading modes using arrow key navigation. Returns the selected mode when user
    presses ENTER, or exits the program if ESC is pressed.

    Returns:
        Selected TradingMode enum value
    """
    term = Terminal()
    modes = [TradingMode.SAFE, TradingMode.CLASSIC]
    selected_index = 0  # Default to SAFE mode

    with term.cbreak():
        while True:
            render_mode_menu(term, selected_index)

            key = term.inkey()

            if key.name == 'KEY_UP':
                selected_index = max(0, selected_index - 1)
            elif key.name == 'KEY_DOWN':
                selected_index = min(len(modes) - 1, selected_index + 1)
            elif key.name == 'KEY_ENTER' or key == '\n' or key == '\r':
                # Clear screen and return selection
                print(term.clear())
                return modes[selected_index]
            elif key.name == 'KEY_ESCAPE' or key == '\x1b':
                # ESC pressed - exit program
                print(term.clear())
                print("Exiting...")
                sys.exit(0)


class ConnorsBot:
    """
    Main trading bot orchestrator for Connors RSI strategy.

    Coordinates database screening, position management, and trade execution.
    Runs automated trading cycles during market hours with comprehensive logging.

    Attributes:
        db: IndicatorsDB instance for technical indicator access
        alpaca: AlpacaClient instance for trade execution
        mode: Trading mode (SAFE or CLASSIC)
        positions: Dict tracking open positions with entry prices, stop losses, and stop order IDs
                  Format: {symbol: {'entry_price': float, 'stop_loss': float,
                                    'shares': int, 'stop_order_id': str|None}}
        cycle_count: Number of trading cycles executed
        running: Boolean flag indicating if bot is actively running
        logger: Logger instance for bot activity tracking
    """

    def __init__(self, paper: bool = True, mode: TradingMode = TradingMode.SAFE) -> None:
        """
        Initialize ConnorsBot with database and broker connections.

        Args:
            paper: If True, use paper trading environment. If False, use live trading.
            mode: Trading mode (SAFE or CLASSIC). SAFE uses bracket orders with stops,
                  CLASSIC uses simple orders without stops.
        """
        # Initialize components
        self.db = IndicatorsDB()
        self.alpaca = AlpacaClient(paper=paper)
        self.mode = mode
        self.positions: Dict[str, Dict] = {}
        self.cycle_count = 0
        self.running = False

        # Set up logging
        self.logger = self._setup_logging()
        self.logger.info(f"ConnorsBot initialized (paper={paper}, mode={mode.value.upper()})")

    def _setup_logging(self) -> logging.Logger:
        """
        Configure logging to console and file.

        Returns:
            Configured logger instance.
        """
        # Create logger (DEBUG to capture all, handlers filter by level)
        logger = logging.getLogger("ConnorsBot")
        logger.setLevel(logging.DEBUG)

        # Clear any existing handlers
        logger.handlers.clear()

        # Console handler - INFO level
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # File handler - DEBUG level (overwrites on each run)
        log_file = LOG_DIR / "trading.log"
        file_handler = logging.FileHandler(log_file, mode='w')  # 'w' = overwrite
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        return logger

    def startup_checks(self) -> bool:
        """
        Perform startup health checks for database and broker connectivity.

        Returns:
            True if all checks pass, False otherwise.
        """
        self.logger.info("=" * 70)
        self.logger.info("STARTUP CHECKS")
        self.logger.info("=" * 70)

        # Check database availability
        self.logger.info("Checking database availability...")
        if not self.db.is_available():
            self.logger.error("Database is not available. Cannot proceed.")
            return False
        self.logger.info("Database check: PASSED")

        # Check Alpaca connection and get account info
        self.logger.info("Checking Alpaca API connection...")
        try:
            account = self.alpaca.get_account()
            self.logger.info(
                f"Alpaca check: PASSED - "
                f"Equity: ${account['equity']:,.2f}, "
                f"Cash: ${account['cash']:,.2f}, "
                f"Buying Power: ${account['buying_power']:,.2f}"
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to Alpaca API: {e}")
            return False

        self.logger.info("=" * 70)
        self.logger.info("All startup checks PASSED")
        self.logger.info("=" * 70)
        return True

    def is_market_hours(self) -> bool:
        """
        Check if current time is within market hours (Mon-Fri, 9:30 AM - 4:00 PM ET).
        Also checks for NYSE market holidays.

        Returns:
            True if market is open, False otherwise.
        """
        now = datetime.now(ET)

        # Check if weekday (Monday=0, Friday=4)
        if now.weekday() >= 5:  # Saturday or Sunday
            return False

        # Check if it's a market holiday
        if now.date() in NYSE_HOLIDAYS_2024_2025:
            return False

        # Check if within market hours
        current_time = now.time()
        if MARKET_OPEN <= current_time <= MARKET_CLOSE:
            return True

        return False

    def sync_positions(self) -> None:
        """
        Synchronize internal position tracking with Alpaca positions.

        Updates self.positions dict with current broker positions.
        For new positions not in our tracking, calculates stop loss from current price
        and sets stop_order_id to None.

        For positions that disappeared from Alpaca, checks if stop order was filled.
        """
        self.logger.debug("Syncing positions with Alpaca...")

        try:
            alpaca_positions = self.alpaca.get_positions()

            # Track symbols we found
            found_symbols = set()

            for pos in alpaca_positions:
                symbol = pos['symbol']
                found_symbols.add(symbol)

                # If this is a new position we don't have tracked, add it
                if symbol not in self.positions:
                    self.positions[symbol] = {
                        'entry_price': pos['avg_entry_price'],
                        'stop_loss': pos['avg_entry_price'] * (1 - STOP_LOSS_PCT),
                        'shares': int(pos['qty']),
                        'stop_order_id': None  # Unknown stop order for existing positions
                    }
                    self.logger.info(
                        f"Added existing position to tracking: {symbol} - "
                        f"{self.positions[symbol]['shares']} shares @ "
                        f"${self.positions[symbol]['entry_price']:.2f}"
                    )
                else:
                    # Update share count in case it changed
                    self.positions[symbol]['shares'] = int(pos['qty'])

            # Remove positions from our tracking that no longer exist at broker
            removed_symbols = set(self.positions.keys()) - found_symbols
            for symbol in removed_symbols:
                # Check if we had a stop order for this position
                stop_order_id = self.positions[symbol].get('stop_order_id')

                if stop_order_id:
                    try:
                        # Check if stop was filled
                        order_status = self.alpaca.get_order(stop_order_id)

                        if order_status and order_status.get('status') == 'filled':
                            # Calculate P&L from stop execution
                            entry_price = self.positions[symbol]['entry_price']
                            stop_price = self.positions[symbol]['stop_loss']
                            shares = self.positions[symbol]['shares']
                            pnl = (stop_price - entry_price) * shares

                            self.logger.info(
                                f"Stop loss executed by Alpaca for {symbol}: "
                                f"{shares} shares @ ${stop_price:.2f}, P&L=${pnl:+.2f} "
                                f"(stop_order_id={stop_order_id})"
                            )
                        else:
                            status = order_status.get('status') if order_status else 'unknown'
                            self.logger.info(
                                f"Removing closed position from tracking: {symbol} "
                                f"(stop_order_id={stop_order_id}, status={status})"
                            )
                    except Exception as e:
                        self.logger.warning(
                            f"Could not check stop order for {symbol} (stop_order_id={stop_order_id}): {e}"
                        )
                        self.logger.info(f"Removing closed position from tracking: {symbol}")
                else:
                    self.logger.info(
                        f"Removing closed position from tracking: {symbol} (no stop order on record)"
                    )

                del self.positions[symbol]

            self.logger.info(f"Position sync complete: {len(self.positions)} open positions")

        except Exception as e:
            self.logger.error(f"Error syncing positions: {e}")

    def reconcile_positions(self) -> None:
        """
        Reconcile existing positions with selected trading mode.

        SAFE mode: Ensure all positions have stop orders (create if missing)
        CLASSIC mode: Cancel any existing stop orders (not needed)

        Called after sync_positions() on startup to align orders with mode.
        """
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("RECONCILING POSITIONS WITH TRADING MODE")
        self.logger.info("=" * 70)

        for symbol, pos_data in self.positions.items():
            # Check for existing stop orders for this symbol
            existing_orders = self.alpaca.get_open_orders(symbol)
            has_stop = any(order['type'] == 'stop' and order['side'] == 'sell' for order in existing_orders)

            if self.mode == TradingMode.SAFE:
                if has_stop:
                    self.logger.info(f"{symbol}: Stop order exists - OK")
                    # Update tracking with the stop order ID if we don't have it
                    if pos_data.get('stop_order_id') is None:
                        for order in existing_orders:
                            if order['type'] == 'stop' and order['side'] == 'sell':
                                pos_data['stop_order_id'] = order['id']
                                pos_data['stop_loss'] = order['stop_price']
                                self.logger.info(f"  Tracking existing stop: ${order['stop_price']:.2f}")
                                break
                else:
                    # Need to create a stop order
                    shares = pos_data['shares']
                    stop_price = pos_data['stop_loss']
                    self.logger.info(f"{symbol}: No stop order - creating one @ ${stop_price:.2f}")

                    stop_order_id = self.alpaca.submit_stop_order(symbol, shares, stop_price)
                    if stop_order_id:
                        pos_data['stop_order_id'] = stop_order_id
                        self.logger.info(f"  Stop order created: {stop_order_id}")
                    else:
                        self.logger.warning(f"  Failed to create stop order for {symbol}")

            else:  # CLASSIC mode
                if has_stop:
                    self.logger.info(f"{symbol}: Stop order exists - cancelling (classic mode)")
                    cancelled = self.alpaca.cancel_orders_for_symbol(symbol)
                    if cancelled > 0:
                        pos_data['stop_order_id'] = None
                        self.logger.info(f"  Cancelled {cancelled} order(s)")
                else:
                    self.logger.info(f"{symbol}: No stop order - OK (classic mode)")
                    pos_data['stop_order_id'] = None

        self.logger.info("=" * 70)
        self.logger.info(f"Reconciliation complete - all positions aligned with {self.mode.value.upper()} mode")
        self.logger.info("=" * 70)

    def validate_positions(self) -> List[Dict]:
        """
        Validate existing positions against exit conditions on startup.

        True Connors RSI exit conditions:
        1. Stop hit: close <= stop_loss (risk management)
        2. SMA5 exit: close > sma5 (mean reversion complete)

        Returns:
            List of invalid position dicts containing:
                - symbol: Stock symbol
                - shares: Number of shares
                - current_price: Current market price
                - reason: Exit reason (stop_hit/sma5_exit)
                - pnl: Profit/loss amount
        """
        if not self.positions:
            self.logger.debug("No positions to validate")
            return []

        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("VALIDATING EXISTING POSITIONS")
        self.logger.info("=" * 70)

        # Get current indicator data for all positions
        symbols = list(self.positions.keys())
        position_data = self.db.get_position_data(symbols)

        invalid_positions = []
        valid_count = 0

        for symbol, pos_info in self.positions.items():
            # Check if we have current data for this symbol
            if symbol not in position_data:
                self.logger.warning(f"No indicator data found for {symbol}, skipping validation")
                continue

            data = position_data[symbol]
            current_price = data['close']
            sma5 = data['sma5']

            entry_price = pos_info['entry_price']
            stop_loss = pos_info['stop_loss']
            shares = pos_info['shares']

            # Calculate P&L
            pnl = (current_price - entry_price) * shares

            # Check exit conditions based on trading mode
            exit_reason = None

            if self.mode == TradingMode.SAFE:
                # SAFE mode: Check both stop loss and SMA5 exit
                # 1. Stop loss hit (highest priority - risk management)
                if current_price <= stop_loss:
                    exit_reason = "stop_hit"
                    self.logger.info(
                        f"{symbol}: EXIT - Stop hit (Price=${current_price:.2f} <= Stop=${stop_loss:.2f})"
                    )
                # 2. SMA5 exit - mean reversion complete
                elif current_price > sma5:
                    exit_reason = "sma5_exit"
                    self.logger.info(
                        f"{symbol}: EXIT - SMA5 (Price=${current_price:.2f} > SMA5=${sma5:.2f})"
                    )
            else:
                # CLASSIC mode: Only check SMA5 exit (no stop loss)
                if current_price > sma5:
                    exit_reason = "sma5_exit"
                    self.logger.info(
                        f"{symbol}: EXIT - SMA5 (Price=${current_price:.2f} > SMA5=${sma5:.2f})"
                    )

            # Build invalid position signal if any condition met
            if exit_reason:
                invalid_position = {
                    'symbol': symbol,
                    'shares': shares,
                    'current_price': current_price,
                    'reason': exit_reason,
                    'pnl': pnl
                }
                invalid_positions.append(invalid_position)

                self.logger.debug(
                    f"{symbol} validation details: Entry=${entry_price:.2f}, Current=${current_price:.2f}, "
                    f"Stop=${stop_loss:.2f}, SMA5=${sma5:.2f}, P&L=${pnl:+.2f}"
                )
            else:
                valid_count += 1
                self.logger.info(
                    f"{symbol}: VALID - {shares} shares @ ${current_price:.2f} "
                    f"(Entry=${entry_price:.2f}, P&L=${pnl:+.2f})"
                )

        # Log summary
        self.logger.info("-" * 70)
        self.logger.info(f"Validation complete: {valid_count} valid, {len(invalid_positions)} exited")
        self.logger.info("=" * 70)

        return invalid_positions

    def find_entries(self) -> List[Dict]:
        """
        Find new entry candidates based on Connors RSI strategy.

        Screens database for oversold stocks, filters out existing positions,
        and calculates position sizing based on available buying power with safety margin.

        Uses bracket orders for entries to provide immediate stop loss protection.

        Returns:
            List of entry signal dicts containing:
                - symbol: Stock symbol
                - shares: Number of shares to buy
                - entry_price: Expected entry price
                - stop_loss: Stop loss price
                - rsi: Current RSI value
        """
        self.logger.debug("Searching for entry candidates...")

        # Calculate available slots
        available_slots = MAX_POSITIONS - len(self.positions)

        if available_slots <= 0:
            self.logger.info(
                f"No available slots for new positions (current: {len(self.positions)}/{MAX_POSITIONS})"
            )
            return []

        # Get entry candidates from database
        candidates = self.db.get_entry_candidates(
            max_crsi=ENTRY_CRSI,
            min_volume=MIN_VOLUME,
            min_price=MIN_PRICE,
            limit=available_slots * 2  # Get extra to allow for filtering
        )

        if not candidates:
            self.logger.info("No entry candidates found matching criteria")
            return []

        # Filter out symbols we already own
        candidates = [c for c in candidates if c['symbol'] not in self.positions]

        if not candidates:
            self.logger.info("All candidates filtered out (already in positions)")
            return []

        # Get current account info
        try:
            account = self.alpaca.get_account()
            buying_power = account['buying_power']
            equity = account['equity']
        except Exception as e:
            self.logger.error(f"Failed to get account info: {e}")
            return []

        # Calculate position size with safety margin
        # Use min of: 95% of buying power, or equity-based position size
        safe_buying_power = buying_power * 0.95
        equity_based_size = equity * POSITION_SIZE_PCT
        position_value = min(safe_buying_power, equity_based_size)

        self.logger.debug(
            f"Position sizing: buying_power=${buying_power:.2f}, equity=${equity:.2f}, "
            f"safe_buying_power=${safe_buying_power:.2f}, equity_based=${equity_based_size:.2f}, "
            f"using=${position_value:.2f}"
        )

        # Build entry signals
        entry_signals = []

        for candidate in candidates[:available_slots]:
            symbol = candidate['symbol']
            close_price = candidate['close']
            rsi = candidate['rsi']
            crsi = candidate['crsi']

            # Calculate position size
            shares = int(position_value / close_price)

            if shares == 0:
                self.logger.warning(
                    f"Skipping {symbol}: calculated shares = 0 (price=${close_price:.2f})"
                )
                continue

            # Calculate stop loss
            stop_loss = close_price * (1 - STOP_LOSS_PCT)

            entry_signal = {
                'symbol': symbol,
                'shares': shares,
                'entry_price': close_price,
                'stop_loss': stop_loss,
                'rsi': rsi,
                'crsi': crsi
            }

            entry_signals.append(entry_signal)

            self.logger.info(
                f"Entry candidate: {symbol} - {shares} shares @ ${close_price:.2f}, "
                f"CRSI={crsi:.2f}, RSI={rsi:.2f}, Stop=${stop_loss:.2f}"
            )

        self.logger.info(f"Found {len(entry_signals)} entry signals")
        return entry_signals

    def check_exits(self) -> List[Dict]:
        """
        Check exit conditions for all open positions.

        True Connors RSI exit criteria:
        1. close <= stop_loss (risk exit - stop loss hit) - HIGHEST PRIORITY
        2. close > sma5 (mean reversion complete - price above short-term average)

        When exiting, cancels any existing stop orders before closing the position.

        Returns:
            List of exit signal dicts containing:
                - symbol: Stock symbol
                - shares: Number of shares to sell
                - current_price: Current market price
                - reason: Exit reason (risk/trend)
                - pnl: Profit/loss amount
        """
        if not self.positions:
            self.logger.debug("No positions to check for exits")
            return []

        self.logger.debug(f"Checking exit conditions for {len(self.positions)} positions...")

        # Get current indicator data for all positions
        symbols = list(self.positions.keys())
        position_data = self.db.get_position_data(symbols)

        exit_signals = []

        for symbol, pos_info in self.positions.items():
            # Check if we have current data for this symbol
            if symbol not in position_data:
                self.logger.warning(f"No indicator data found for {symbol}, skipping exit check")
                continue

            data = position_data[symbol]
            current_price = data['close']
            sma5 = data['sma5']

            entry_price = pos_info['entry_price']
            stop_loss = pos_info['stop_loss']
            shares = pos_info['shares']

            # Calculate P&L
            pnl = (current_price - entry_price) * shares

            # Check exit conditions based on trading mode
            exit_reason = None

            if self.mode == TradingMode.SAFE:
                # SAFE mode: Check both stop loss and SMA5 exit
                # 1. Stop loss hit (HIGHEST PRIORITY - capital protection)
                if current_price <= stop_loss:
                    exit_reason = "risk"
                    self.logger.info(
                        f"Exit signal (stop): {symbol} - Price=${current_price:.2f} <= Stop=${stop_loss:.2f}"
                    )
                # 2. SMA5 exit - price above short-term average (mean reversion complete)
                elif current_price > sma5:
                    exit_reason = "trend"
                    self.logger.info(
                        f"Exit signal (SMA5): {symbol} - Price=${current_price:.2f} > SMA5=${sma5:.2f}"
                    )
            else:
                # CLASSIC mode: Only check SMA5 exit (no stop loss)
                if current_price > sma5:
                    exit_reason = "trend"
                    self.logger.info(
                        f"Exit signal (SMA5): {symbol} - Price=${current_price:.2f} > SMA5=${sma5:.2f}"
                    )

            # Build exit signal if any condition met
            if exit_reason:
                exit_signal = {
                    'symbol': symbol,
                    'shares': shares,
                    'current_price': current_price,
                    'reason': exit_reason,
                    'pnl': pnl
                }
                exit_signals.append(exit_signal)

                self.logger.info(
                    f"Exit candidate: {symbol} - {shares} shares @ ${current_price:.2f}, "
                    f"reason={exit_reason}, P&L=${pnl:+.2f}"
                )

        self.logger.info(f"Found {len(exit_signals)} exit signals")
        return exit_signals

    def run_cycle(self) -> None:
        """
        Execute one complete trading cycle.

        Performs the following steps:
        1. Sync positions with broker
        2. Check and execute exits
        3. Find and execute entries
        4. Log cycle summary with performance metrics
        """
        self.cycle_count += 1
        cycle_start = time.time()

        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info(f"CYCLE #{self.cycle_count} - {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.logger.info("=" * 70)

        # Step 1: Sync positions
        self.sync_positions()

        # Track cycle statistics
        exits_executed = 0
        entries_executed = 0
        total_pnl = 0.0

        # Step 2: Check and execute exits
        exit_signals = self.check_exits()

        for exit_signal in exit_signals:
            symbol = exit_signal['symbol']
            shares = exit_signal['shares']
            current_price = exit_signal['current_price']
            reason = exit_signal['reason']
            pnl = exit_signal['pnl']

            self.logger.info(
                f"Executing EXIT: {symbol} x {shares} @ ${current_price:.2f} "
                f"(reason={reason}, P&L=${pnl:+.2f})"
            )

            # Execute close position (automatically cancels stop orders)
            if self.alpaca.close_position(symbol):
                exits_executed += 1
                total_pnl += pnl

                # Remove from tracking
                if symbol in self.positions:
                    del self.positions[symbol]

                self.logger.info(
                    f"EXIT SUCCESS: {symbol} - {shares} shares closed @ ${current_price:.2f}, "
                    f"P&L=${pnl:+.2f}"
                )
            else:
                self.logger.error(
                    f"EXIT FAILED: {symbol} - Position close rejected. "
                    f"Check broker status and position availability."
                )

        # Step 3: Find and execute entries
        entry_signals = self.find_entries()

        for entry_signal in entry_signals:
            symbol = entry_signal['symbol']
            shares = entry_signal['shares']
            entry_price = entry_signal['entry_price']
            stop_loss = entry_signal['stop_loss']
            rsi = entry_signal['rsi']
            crsi = entry_signal['crsi']

            self.logger.info(
                f"Executing ENTRY: {symbol} x {shares} @ ~${entry_price:.2f} "
                f"with {STOP_LOSS_PCT*100:.1f}% stop (CRSI={crsi:.2f}, RSI={rsi:.2f})"
            )

            # Defensive cleanup: cancel any orphaned orders for this symbol
            # This prevents wash trade rejections from leftover stop orders
            cancelled = self.alpaca.cancel_orders_for_symbol(symbol)
            if cancelled > 0:
                self.logger.info(f"Cleaned up {cancelled} orphaned order(s) for {symbol}")

            # Execute order based on trading mode
            if self.mode == TradingMode.SAFE:
                # SAFE mode: Bracket order with stop loss protection
                # Pass stop loss PERCENTAGE, not price
                # Stop price will be calculated from ACTUAL fill price inside bracket order
                result = self.alpaca.submit_bracket_order(symbol, shares, STOP_LOSS_PCT)
            else:
                # CLASSIC mode: Simple market order without stop loss
                result = self.alpaca.submit_simple_order(symbol, shares)

            if result:
                entries_executed += 1

                # Extract fill details
                fill_price = result.get('fill_price', entry_price)
                order_id = result.get('order_id')

                if self.mode == TradingMode.SAFE:
                    # SAFE mode: track stop order and stop loss price
                    stop_order_id = result.get('stop_order_id')
                    actual_stop_loss = result.get('stop_price', fill_price * (1 - STOP_LOSS_PCT))

                    # Add to position tracking with stop information
                    self.positions[symbol] = {
                        'entry_price': fill_price,
                        'stop_loss': actual_stop_loss,
                        'shares': shares,
                        'stop_order_id': stop_order_id
                    }

                    self.logger.info(
                        f"ENTRY SUCCESS (SAFE): {symbol} - {shares} shares @ ${fill_price:.2f}, "
                        f"stop @ ${actual_stop_loss:.2f} (order_id={order_id}, stop_order_id={stop_order_id})"
                    )
                else:
                    # CLASSIC mode: no stop order, set stop_order_id to None
                    # Calculate a theoretical stop_loss for tracking purposes (not used for actual trading)
                    theoretical_stop_loss = fill_price * (1 - STOP_LOSS_PCT)

                    # Add to position tracking without stop order
                    self.positions[symbol] = {
                        'entry_price': fill_price,
                        'stop_loss': theoretical_stop_loss,  # For tracking only
                        'shares': shares,
                        'stop_order_id': None  # No stop order in classic mode
                    }

                    self.logger.info(
                        f"ENTRY SUCCESS (CLASSIC): {symbol} - {shares} shares @ ${fill_price:.2f}, "
                        f"no stop (order_id={order_id})"
                    )

                # Log fill details if fill price differs from expected
                if abs(fill_price - entry_price) > 0.01:
                    self.logger.info(
                        f"Fill price note: Expected ${entry_price:.2f}, Filled @ ${fill_price:.2f} "
                        f"(diff=${fill_price - entry_price:+.2f})"
                    )
            else:
                order_type = "Bracket" if self.mode == TradingMode.SAFE else "Simple"
                self.logger.error(
                    f"ENTRY FAILED: {symbol} - {order_type} order rejected. "
                    f"Check account buying power and order limits."
                )

        # Step 4: Get current account state
        try:
            account = self.alpaca.get_account()
            current_equity = account['equity']
        except Exception as e:
            self.logger.error(f"Failed to get account info: {e}")
            current_equity = 0.0

        # Calculate cycle duration
        cycle_duration = time.time() - cycle_start

        # Log cycle summary
        self.logger.info("")
        self.logger.info("-" * 70)
        self.logger.info("CYCLE SUMMARY")
        self.logger.info("-" * 70)
        self.logger.info(f"Account Equity:  ${current_equity:,.2f}")
        self.logger.info(f"Open Positions:  {len(self.positions)}/{MAX_POSITIONS}")
        self.logger.info(f"Entries:         {entries_executed}")
        self.logger.info(f"Exits:           {exits_executed}")
        self.logger.info(f"Cycle P&L:       ${total_pnl:+,.2f}")
        self.logger.info(f"Cycle Duration:  {cycle_duration:.2f}s")
        self.logger.info("-" * 70)

    def run(self) -> None:
        """
        Main bot execution loop.

        Performs startup checks, waits for market open, then runs trading cycles
        at regular intervals during market hours. Handles graceful shutdown on
        KeyboardInterrupt.
        """
        # Display startup banner
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("CONNORS RSI TRADING BOT")
        self.logger.info("=" * 70)
        self.logger.info(f"Started: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.logger.info(f"Mode: {self.mode.value.upper()}")
        self.logger.info(f"Strategy: Entry CRSI <= {ENTRY_CRSI}, Exit Close > SMA5")
        self.logger.info(f"Position Size: {POSITION_SIZE_PCT*100:.0f}% per position")
        self.logger.info(f"Max Positions: {MAX_POSITIONS}")
        if self.mode == TradingMode.SAFE:
            self.logger.info(f"Stop Loss: {STOP_LOSS_PCT*100:.0f}% (bracket orders)")
        else:
            self.logger.info(f"Stop Loss: None (classic mode - no stops)")
        self.logger.info(f"Cycle Interval: {CYCLE_INTERVAL_MINUTES} minutes")
        self.logger.info("=" * 70)

        # Perform startup checks
        if not self.startup_checks():
            self.logger.error("Startup checks failed. Exiting.")
            return

        # Sync positions and validate them
        self.sync_positions()
        self.reconcile_positions()
        invalid_positions = self.validate_positions()

        # Auto-exit any invalid positions
        if invalid_positions:
            if not self.is_market_hours():
                self.logger.warning(
                    f"Market closed - skipping {len(invalid_positions)} auto-exit(s). "
                    f"Will retry when market opens."
                )
            else:
                self.logger.info("")
                self.logger.info("=" * 70)
                self.logger.info("AUTO-EXITING INVALID POSITIONS")
                self.logger.info("=" * 70)

                for invalid_pos in invalid_positions:
                    symbol = invalid_pos['symbol']
                    shares = invalid_pos['shares']
                    current_price = invalid_pos['current_price']
                    reason = invalid_pos['reason']
                    pnl = invalid_pos['pnl']

                    self.logger.info(
                        f"Closing {symbol}: {shares} shares @ ${current_price:.2f} "
                        f"(reason={reason}, P&L=${pnl:+.2f})"
                    )

                    # Execute close position (automatically cancels stop orders)
                    if self.alpaca.close_position(symbol):
                        # Remove from tracking
                        if symbol in self.positions:
                            del self.positions[symbol]

                        self.logger.info(
                            f"EXIT SUCCESS: {symbol} - {shares} shares closed @ ${current_price:.2f}, "
                            f"P&L=${pnl:+.2f}"
                        )
                    else:
                        self.logger.error(
                            f"EXIT FAILED: {symbol} - Position close rejected. "
                            f"Check broker status and position availability."
                        )

                self.logger.info("=" * 70)
                self.logger.info(f"Auto-exit complete: {len(invalid_positions)} positions closed")
                self.logger.info("=" * 70)

                # Wait for Alpaca to process the close orders before continuing
                self.logger.info("Waiting 5 seconds for orders to settle...")
                time.sleep(5)

                # Re-sync positions to get accurate state after auto-exits
                self.sync_positions()

        # Wait for market to open
        while not self.is_market_hours():
            now = datetime.now(ET)
            self.logger.info(
                f"Market is closed. Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}. "
                f"Waiting for market hours ({MARKET_OPEN} - {MARKET_CLOSE} ET)..."
            )
            time.sleep(60)  # Check every minute

        self.logger.info("Market is OPEN. Starting trading cycles...")
        self.logger.info("Bot will run when VV7 sync completes (watching sync_complete.txt)...")
        self.running = True

        # Track last sync completion file modification time
        sync_file = Path(SYNC_COMPLETE_FILE)
        last_sync_mtime = sync_file.stat().st_mtime if sync_file.exists() else 0
        self.logger.info(f"Sync file: {sync_file}")
        self.logger.info(f"Current sync file mtime: {last_sync_mtime}")

        try:
            # Main trading loop - triggered by sync completion file updates
            while self.running:
                # Check if still in market hours
                if not self.is_market_hours():
                    self.logger.info("Market has closed. Stopping trading cycles.")
                    break

                # Check if sync completion file was updated
                if sync_file.exists():
                    current_mtime = sync_file.stat().st_mtime

                    if current_mtime > last_sync_mtime:
                        # Sync completed - file was written by VV7
                        self.logger.info(f"Sync complete detected (mtime: {last_sync_mtime} -> {current_mtime})")
                        last_sync_mtime = current_mtime

                        try:
                            self.run_cycle()
                        except Exception as e:
                            self.logger.error(f"Error in trading cycle: {e}", exc_info=True)

                # Check every 5 seconds for sync completion
                time.sleep(5)

        except KeyboardInterrupt:
            self.logger.info("")
            self.logger.info("=" * 70)
            self.logger.info("SHUTDOWN REQUESTED (Ctrl+C)")
            self.logger.info("=" * 70)
            self.running = False

        # Display end-of-day summary
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("END OF DAY SUMMARY")
        self.logger.info("=" * 70)
        self.logger.info(f"Total Cycles Run: {self.cycle_count}")

        try:
            account = self.alpaca.get_account()
            self.logger.info(f"Final Equity: ${account['equity']:,.2f}")
            self.logger.info(f"Final Cash: ${account['cash']:,.2f}")
        except Exception as e:
            self.logger.error(f"Failed to get final account state: {e}")

        self.logger.info(f"Open Positions: {len(self.positions)}")

        if self.positions:
            self.logger.info("Open positions:")
            for symbol, pos_info in self.positions.items():
                self.logger.info(
                    f"  {symbol}: {pos_info['shares']} shares @ "
                    f"${pos_info['entry_price']:.2f}, Stop=${pos_info['stop_loss']:.2f}"
                )

        self.logger.info(f"Ended: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.logger.info("=" * 70)
        self.logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    # Select trading mode interactively
    mode = select_trading_mode()

    # Create and run bot in paper trading mode with selected mode
    bot = ConnorsBot(paper=True, mode=mode)
    bot.run()
