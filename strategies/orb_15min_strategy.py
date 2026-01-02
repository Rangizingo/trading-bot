"""
ORB 15-Minute Strategy (LONG ONLY)

Opening Range Breakout using 15-minute range (9:30-9:45 AM).
Entry: 9:45 AM - 11:00 AM (after range established)
Exit: Target (100% range), Stop (range low), Failed breakout, or 11:00 AM forced

Direction: LONG ONLY (only breakout above range high)

Entry Conditions:
- Time: 9:45 AM - 11:00 AM ET
- 15-min opening range established (9:30-9:45 AM)
- Range width: 0.3% - 1.5% of range low
- 5-min candle CLOSES above range high
- RVOL > 1.5x average
- Price above VWAP

Exit Conditions:
- Target: 100% of range height from entry (entry_price + range_size)
- Stop: Range low
- Failed breakout: Price closes back inside range
- Time: 11:00 AM forced exit
"""

from typing import Dict, List, Optional, Set
from datetime import datetime, time as dt_time, date
import logging

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .base_strategy import BaseStrategy, EntrySignal, ExitSignal
from data.intraday_indicators import IntradayIndicators

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET = ZoneInfo('America/New_York')


class ORB15MinStrategy(BaseStrategy):
    """
    ORB 15-Minute - Opening Range Breakout (LONG ONLY)

    Uses 15-minute opening range (9:30-9:45 AM).
    Entry on 5-min candle close above range high.
    Target: 100% of range from entry.

    Key characteristics:
    - Very short trading window (9:45 AM - 11:00 AM)
    - Strict range width filter (0.3% - 1.5%)
    - RVOL filter ensures momentum
    - VWAP filter ensures bullish bias
    - 100% range target for better R:R
    """

    # Strategy-specific constants
    MARKET_OPEN = dt_time(9, 30)
    OPENING_RANGE_START = dt_time(9, 30)
    OPENING_RANGE_END = dt_time(9, 45)  # 15-minute range
    ENTRY_START = dt_time(9, 45)
    ENTRY_END = dt_time(11, 0)
    EOD_EXIT_DEFAULT = dt_time(11, 0)  # 11:00 AM forced exit

    # Range width filters (as % of range low)
    MIN_RANGE_PCT = 0.003  # 0.3% minimum range
    MAX_RANGE_PCT = 0.015  # 1.5% maximum range

    # Volume filter
    MIN_RELATIVE_VOLUME = 1.5

    # Target calculation
    TARGET_MULTIPLIER = 1.0  # 100% of range height

    def __init__(
        self,
        indicators: IntradayIndicators,
        max_positions: int = 3,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(11, 0),
        min_price: float = 5.0,
        min_range_pct: float = 0.003,
        max_range_pct: float = 0.015,
        min_relative_volume: float = 1.5,
        use_mid_range_stop: bool = False,
    ):
        """
        Initialize ORB 15-Minute Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            max_positions: Maximum simultaneous positions (default 3)
            position_size_pct: Position size as % of equity (default 10%)
            risk_per_trade_pct: Max risk per trade (default 2%)
            eod_exit_time: Force exit time (default 11:00 AM)
            min_price: Minimum stock price (default $5)
            min_range_pct: Minimum opening range width as % (default 0.3%)
            max_range_pct: Maximum opening range width as % (default 1.5%)
            min_relative_volume: Minimum relative volume (default 1.5)
            use_mid_range_stop: If True, use middle of range as stop instead of range low
        """
        super().__init__(
            name="ORB_15MIN",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.min_range_pct = min_range_pct
        self.max_range_pct = max_range_pct
        self.min_relative_volume = min_relative_volume
        self.use_mid_range_stop = use_mid_range_stop

        # Track daily trades to enforce max 1 trade per symbol per day
        self._daily_trades: Dict[date, Set[str]] = {}

        # Cache for opening ranges (reset daily)
        self._range_cache: Dict[str, Dict] = {}
        self._range_cache_date: Optional[date] = None

    def _get_current_et(self) -> datetime:
        """Get current time in Eastern Time."""
        return datetime.now(ET)

    def _get_traded_today(self) -> Set[str]:
        """Get set of symbols already traded today."""
        today = self._get_current_et().date()
        return self._daily_trades.get(today, set())

    def _mark_traded(self, symbol: str) -> None:
        """Mark a symbol as traded today."""
        today = self._get_current_et().date()
        if today not in self._daily_trades:
            self._daily_trades = {today: set()}  # Clear old dates
        self._daily_trades[today].add(symbol)

    def _clear_range_cache_if_new_day(self) -> None:
        """Clear range cache if it's a new day."""
        today = self._get_current_et().date()
        if self._range_cache_date != today:
            self._range_cache = {}
            self._range_cache_date = today

    def _get_opening_range_15min(self, symbol: str) -> Optional[Dict]:
        """
        Get the 15-minute opening range (9:30-9:45 AM).

        Uses caching to avoid recalculating the same range multiple times.

        Args:
            symbol: Stock symbol

        Returns:
            Dict with keys: high, low, range_size, bar_count, or None if insufficient data
        """
        self._clear_range_cache_if_new_day()

        # Check cache first
        if symbol in self._range_cache:
            return self._range_cache[symbol]

        # Calculate the range
        now_et = self._get_current_et()

        # Use the indicators helper for timestamp conversion
        start_ts = self.indicators._et_to_timestamp(
            now_et.date(), self.OPENING_RANGE_START
        )
        end_ts = self.indicators._et_to_timestamp(
            now_et.date(), self.OPENING_RANGE_END
        )

        bars = self.indicators.get_bars(symbol, start_ts, end_ts)

        if not bars or len(bars) < 5:  # Need at least 5 minutes of data
            return None

        or_high = max(bar['high'] for bar in bars)
        or_low = min(bar['low'] for bar in bars)
        or_size = or_high - or_low

        opening_range = {
            'high': or_high,
            'low': or_low,
            'range_size': or_size,
            'bar_count': len(bars),
            'start_ts': start_ts,
            'end_ts': end_ts,
            'mid': (or_high + or_low) / 2,
        }

        # Cache the result
        self._range_cache[symbol] = opening_range

        return opening_range

    def _is_range_valid(self, opening_range: Dict) -> bool:
        """
        Check if range meets criteria:
        - Range width between 0.3% and 1.5% of range low

        Args:
            opening_range: Dict with high, low, range_size keys

        Returns:
            True if range meets criteria
        """
        if not opening_range:
            return False

        range_size = opening_range['range_size']
        range_low = opening_range['low']

        if range_low <= 0:
            return False

        # Calculate range width as % of range low
        range_width_pct = range_size / range_low

        # Check bounds
        if range_width_pct < self.min_range_pct:
            return False
        if range_width_pct > self.max_range_pct:
            return False

        return True

    def is_entry_window(self) -> bool:
        """
        Check if we're in entry window (9:45 AM - 11:00 AM).

        Returns:
            True if current time is within entry window
        """
        now_et = self._get_current_et().time()
        return now_et >= self.ENTRY_START and now_et < self.ENTRY_END

    def is_range_established(self) -> bool:
        """
        Check if we're past 9:45 AM (15-min range is complete).

        Returns:
            True if range is established
        """
        now_et = self._get_current_et().time()
        return now_et >= self.OPENING_RANGE_END

    def is_trading_time(self) -> bool:
        """
        Check if we're in the valid trading window.
        Same as is_entry_window for this strategy.

        Returns:
            True if within trading window (9:45 AM - 11:00 AM)
        """
        return self.is_entry_window()

    def _get_5min_candle_close(self, symbol: str) -> Optional[float]:
        """
        Get the close price of the most recent completed 5-minute candle.

        This aggregates 1-minute bars into a 5-minute candle.

        Args:
            symbol: Stock symbol

        Returns:
            Close price of the last 5-minute candle, or None
        """
        # Get last 10 bars to ensure we have enough data
        bars = self.indicators.get_latest_bars(symbol, 10)
        if not bars or len(bars) < 5:
            return None

        # Aggregate last 5 bars into a candle
        # The close is simply the last bar's close
        last_5_bars = bars[-5:]
        return last_5_bars[-1]['close']

    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get the most recent close price for a symbol."""
        bars = self.indicators.get_latest_bars(symbol, 5)
        return bars[-1]['close'] if bars else None

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets ORB 15-Min entry criteria.

        Entry Conditions:
        1. Time: 9:45 AM - 11:00 AM ET
        2. 15-min opening range established
        3. Range width: 0.3% - 1.5%
        4. 5-min candle CLOSES above range high
        5. RVOL > 1.5x
        6. Price above VWAP

        Returns:
            EntrySignal if all conditions met, None otherwise
        """
        # Time check
        if not self.is_entry_window():
            return None

        # Check if already traded today
        if symbol in self._get_traded_today():
            return None

        # Get opening range
        opening_range = self._get_opening_range_15min(symbol)
        if not opening_range:
            logger.debug(f"[ORB_15MIN] {symbol}: No opening range data")
            return None

        # Check range width filter
        if not self._is_range_valid(opening_range):
            range_pct = (opening_range['range_size'] / opening_range['low']) * 100
            logger.debug(
                f"[ORB_15MIN] {symbol}: Range {range_pct:.2f}% outside "
                f"{self.min_range_pct*100:.1f}%-{self.max_range_pct*100:.1f}%"
            )
            return None

        # Get current price (5-min candle close)
        current_price = self._get_5min_candle_close(symbol)
        if current_price is None:
            return None

        # Price filter
        if current_price < self.min_price:
            return None

        # Check for breakout: candle closed above range high
        if current_price <= opening_range['high']:
            return None

        # VWAP check: price must be above VWAP
        vwap = self.indicators.get_current_vwap(symbol)
        if vwap is None or current_price <= vwap:
            logger.debug(
                f"[ORB_15MIN] {symbol}: Price ${current_price:.2f} not above "
                f"VWAP ${vwap:.2f if vwap else 0:.2f}"
            )
            return None

        # Relative volume check
        rel_vol = self.indicators.get_relative_volume(symbol)
        if rel_vol is None or rel_vol < self.min_relative_volume:
            logger.debug(
                f"[ORB_15MIN] {symbol}: RVOL {rel_vol:.2f if rel_vol else 0:.2f}x "
                f"< {self.min_relative_volume}x"
            )
            return None

        # Calculate target and stop
        range_height = opening_range['range_size']
        target = current_price + (range_height * self.TARGET_MULTIPLIER)

        # Stop at range low or mid-range
        if self.use_mid_range_stop:
            stop = opening_range['mid']
        else:
            stop = opening_range['low']

        # Calculate range width for metadata
        range_width_pct = range_height / opening_range['low']

        logger.info(
            f"[ORB_15MIN] {symbol}: ENTRY SIGNAL - Price ${current_price:.2f} > "
            f"Range high ${opening_range['high']:.2f}, RVOL {rel_vol:.2f}x, "
            f"Target ${target:.2f}, Stop ${stop:.2f}"
        )

        return EntrySignal(
            symbol=symbol,
            price=current_price,
            target=target,
            stop=stop,
            reason=f"ORB 15-Min: Breakout above range high ${opening_range['high']:.2f}",
            metadata={
                'direction': 'long',
                'range_high': opening_range['high'],
                'range_low': opening_range['low'],
                'range_mid': opening_range['mid'],
                'range_size': range_height,
                'range_width_pct': range_width_pct,
                'target': target,
                'stop': stop,
                'vwap': vwap,
                'relative_volume': rel_vol,
                'strategy': 'ORB_15MIN',
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions:
        1. Target hit (100% of range from entry)
        2. Stop hit (range low or mid-range)
        3. Failed breakout (price closes back inside range)
        4. Time >= 11:00 AM ET (EOD)

        Args:
            symbol: Stock symbol
            position: Dict with keys: entry_price, shares, entry_time, target, stop

        Returns:
            ExitSignal if exit condition met, None otherwise
        """
        now_et = self._get_current_et()

        # Get current price
        current_price = self._get_current_price(symbol)
        if current_price is None:
            return None

        entry_price = position.get('entry_price', 0)
        pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

        # Condition 1: EOD exit time (11:00 AM)
        if now_et.time() >= self.eod_exit_time:
            logger.info(
                f"[ORB_15MIN] {symbol}: EOD EXIT at {self.eod_exit_time}, "
                f"P&L: {pnl_pct:.2f}%"
            )
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={
                    'eod_time': str(self.eod_exit_time),
                    'strategy': 'ORB_15MIN',
                }
            )

        # Get target and stop from position metadata
        target = position.get('target')
        stop = position.get('stop')

        # Condition 2: Target hit (100% of range)
        if target and current_price >= target:
            logger.info(
                f"[ORB_15MIN] {symbol}: TARGET HIT at ${current_price:.2f} "
                f"(target ${target:.2f}), P&L: {pnl_pct:.2f}%"
            )
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='target',
                pnl_pct=pnl_pct,
                metadata={
                    'target': target,
                    'hit_price': current_price,
                    'strategy': 'ORB_15MIN',
                }
            )

        # Condition 3: Stop hit (range low or mid-range)
        if stop and current_price <= stop:
            logger.info(
                f"[ORB_15MIN] {symbol}: STOP HIT at ${current_price:.2f} "
                f"(stop ${stop:.2f}), P&L: {pnl_pct:.2f}%"
            )
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='stop',
                pnl_pct=pnl_pct,
                metadata={
                    'stop': stop,
                    'hit_price': current_price,
                    'strategy': 'ORB_15MIN',
                }
            )

        # Condition 4: Failed breakout (price closes back inside range)
        opening_range = self._get_opening_range_15min(symbol)
        if opening_range:
            range_high = opening_range['high']
            range_low = opening_range['low']

            # If price closes back below range high, it's a failed breakout
            if current_price < range_high:
                logger.info(
                    f"[ORB_15MIN] {symbol}: FAILED BREAKOUT - Price ${current_price:.2f} "
                    f"back below range high ${range_high:.2f}, P&L: {pnl_pct:.2f}%"
                )
                return ExitSignal(
                    symbol=symbol,
                    price=current_price,
                    reason='signal',
                    pnl_pct=pnl_pct,
                    metadata={
                        'exit_type': 'failed_breakout',
                        'range_high': range_high,
                        'range_low': range_low,
                        'strategy': 'ORB_15MIN',
                    }
                )

        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen all symbols for ORB 15-Min entry candidates.

        Returns:
            List of EntrySignal objects sorted by RVOL (higher = better)
        """
        if not self.is_entry_window():
            now_time = self._get_current_et().time()
            logger.info(
                f"[ORB_15MIN] Outside entry window (9:45 AM - 11:00 AM). "
                f"Current time: {now_time}"
            )
            return []

        symbols = self.indicators.get_all_symbols()
        traded_today = self._get_traded_today()
        candidates = []

        for symbol in symbols:
            # Skip if already traded today
            if symbol in traded_today:
                continue

            try:
                signal = self.check_entry(symbol)
                if signal:
                    candidates.append(signal)

                    # Don't check too many symbols, stop when we have enough
                    if len(candidates) >= self.max_positions * 3:
                        break

            except Exception as e:
                logger.debug(f"Error checking {symbol} for ORB 15-Min: {e}")
                continue

        # Sort by relative volume (higher = better momentum)
        candidates.sort(
            key=lambda x: x.metadata.get('relative_volume', 0),
            reverse=True
        )

        logger.info(f"[ORB_15MIN] Found {len(candidates)} entry candidates")
        return candidates[:self.max_positions * 2]

    def record_entry(self, symbol: str) -> None:
        """
        Record that a position was entered for this symbol today.

        Args:
            symbol: Stock symbol that was traded
        """
        self._mark_traded(symbol)
        logger.info(f"[ORB_15MIN] Recorded entry for {symbol}")

    def __repr__(self) -> str:
        return (
            f"ORB15MinStrategy("
            f"range={self.min_range_pct*100:.1f}%-{self.max_range_pct*100:.1f}%, "
            f"target={self.TARGET_MULTIPLIER:.0%}, "
            f"RVOL>{self.min_relative_volume}x, "
            f"max_pos={self.max_positions}, "
            f"eod={self.eod_exit_time})"
        )
