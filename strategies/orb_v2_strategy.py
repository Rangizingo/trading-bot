"""
ORB V2 Strategy (Simplified Opening Range Breakout)

Win Rate: 74.56% (verified)
Profit Factor: 2.51
Source: Trade That Swing (verified with 114 trades over 1 year)

Entry Conditions:
- Time after 10:30 AM ET (60-min opening range established)
- 5-min candle CLOSES above opening range high
- Opening range width <= 0.8% of open price
- LONG ONLY (no short entries)
- Max 1 trade per symbol per day

Exit Conditions:
- Target: 50% of opening range height from entry
- Stop: Opening range low
- EOD: 3:00 PM ET forced exit

Key Differences from Original ORB:
1. Simplified entry: Only price breakout (no VWAP, no EMA slope)
2. Different target: 50% of range (not 100% measured move)
3. Earlier exit: 3:00 PM instead of 2:00 PM
4. Range width filter: Skip if range > 0.8% of open
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


class ORBV2Strategy(BaseStrategy):
    """
    Simplified Opening Range Breakout Strategy.

    Entry on breakout above 60-min range with range width filter.
    Target at 50% of range, stop at range low, EOD exit at 3:00 PM.
    """

    # Strategy-specific constants
    MARKET_OPEN = dt_time(9, 30)
    OPENING_RANGE_END = dt_time(10, 30)  # 60-minute range
    EOD_EXIT = dt_time(15, 0)  # 3:00 PM ET
    MAX_RANGE_WIDTH_PCT = 0.008  # 0.8% of open price
    TARGET_MULTIPLIER = 0.50  # 50% of range height

    def __init__(
        self,
        indicators: IntradayIndicators,
        max_positions: int = 5,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(15, 0),
        min_price: float = 5.0,
        max_range_width_pct: float = 0.008,
    ):
        """
        Initialize ORB V2 Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            max_positions: Maximum simultaneous positions (default 5)
            position_size_pct: Position size as % of equity (default 10%)
            risk_per_trade_pct: Max risk per trade (default 2%)
            eod_exit_time: Force exit time (default 3:00 PM)
            min_price: Minimum stock price (default $5)
            max_range_width_pct: Maximum opening range width as % of open (default 0.8%)
        """
        super().__init__(
            name="ORB_V2",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.max_range_width_pct = max_range_width_pct

        # Track daily trades to enforce max 1 trade per symbol per day
        self._daily_trades: Dict[date, Set[str]] = {}

    def _get_current_et(self) -> datetime:
        """Get current time in Eastern Time."""
        return datetime.now(ET)

    def _get_traded_today(self) -> Set[str]:
        """Get set of symbols already traded today"""
        today = self._get_current_et().date()
        return self._daily_trades.get(today, set())

    def _mark_traded(self, symbol: str) -> None:
        """Mark a symbol as traded today"""
        today = self._get_current_et().date()
        if today not in self._daily_trades:
            self._daily_trades = {today: set()}  # Clear old dates
        self._daily_trades[today].add(symbol)

    def is_trading_time(self) -> bool:
        """Check if we're in the valid trading window (after 10:30 AM, before 3:00 PM ET)"""
        now_et = self._get_current_et().time()
        return now_et >= self.OPENING_RANGE_END and now_et < self.eod_exit_time

    def _is_range_valid(self, opening_range: Dict, symbol: str) -> bool:
        """
        Check if opening range meets criteria.

        Range width must be <= 0.8% of the opening price.
        """
        if not opening_range:
            return False

        range_size = opening_range['range_size']
        range_low = opening_range['low']

        if range_low <= 0:
            return False

        # Calculate range width as % of range low (proxy for open price)
        range_width_pct = range_size / range_low

        if range_width_pct > self.max_range_width_pct:
            logger.debug(f"[ORB_V2] {symbol}: Range width {range_width_pct:.2%} > max {self.max_range_width_pct:.2%}")
            return False

        return True

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets ORB V2 entry criteria.

        Entry Conditions:
        1. Time after 10:30 AM ET
        2. Price closed above opening range high
        3. Range width <= 0.8% of open
        4. Symbol not already traded today

        Returns:
            EntrySignal if all conditions met, None otherwise
        """
        # Time check
        if not self.is_trading_time():
            return None

        # Check if already traded today
        if symbol in self._get_traded_today():
            return None

        # Get opening range
        opening_range = self.indicators.get_opening_range(symbol)
        if not opening_range:
            return None

        # Check range width filter
        if not self._is_range_valid(opening_range, symbol):
            return None

        # Get current price
        bars = self.indicators.get_latest_bars(symbol, 10)
        if not bars:
            return None

        current_price = bars[-1]['close']

        # Price filter
        if current_price < self.min_price:
            return None

        # Check for breakout: current close > range high
        if current_price <= opening_range['high']:
            return None

        # Calculate target and stop
        range_height = opening_range['range_size']
        target = current_price + (range_height * self.TARGET_MULTIPLIER)
        stop = opening_range['low']

        return EntrySignal(
            symbol=symbol,
            price=current_price,
            target=target,
            stop=stop,
            reason=f"ORB V2: Breakout above range high ${opening_range['high']:.2f}",
            metadata={
                'range_high': opening_range['high'],
                'range_low': opening_range['low'],
                'range_size': range_height,
                'target': target,
                'stop': stop,
                'range_width_pct': range_height / opening_range['low'],
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions:
        1. Price >= target (50% of range from entry)
        2. Price <= stop (range low)
        3. Time >= 3:00 PM ET (EOD)

        Args:
            position: Dict with keys: entry_price, shares, entry_time, target, stop

        Returns:
            ExitSignal if exit condition met, None otherwise
        """
        now_et = self._get_current_et()

        # Get current price
        bars = self.indicators.get_latest_bars(symbol, 5)
        if not bars:
            return None

        current_price = bars[-1]['close']
        entry_price = position.get('entry_price', 0)
        pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

        # Condition 1: EOD exit time
        if now_et.time() >= self.eod_exit_time:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={'eod_time': str(self.eod_exit_time)}
            )

        # Get target and stop from position metadata or recalculate
        target = position.get('target')
        stop = position.get('stop')

        # Condition 2: Target hit (50% of range)
        if target and current_price >= target:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='target',
                pnl_pct=pnl_pct,
                metadata={'target': target, 'hit_price': current_price}
            )

        # Condition 3: Stop hit (range low)
        if stop and current_price <= stop:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='stop',
                pnl_pct=pnl_pct,
                metadata={'stop': stop, 'hit_price': current_price}
            )

        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen all symbols for ORB V2 entry candidates.

        Returns:
            List of EntrySignal objects sorted by range width (smaller = better)
        """
        if not self.is_trading_time():
            logger.info(f"[ORB_V2] Outside trading window (10:30 AM - 3:00 PM)")
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

                    if len(candidates) >= self.max_positions * 3:
                        break

            except Exception as e:
                logger.debug(f"Error checking {symbol} for ORB V2: {e}")
                continue

        # Sort by range width (smaller = better setup)
        candidates.sort(key=lambda x: x.metadata.get('range_width_pct', 999))

        logger.info(f"[ORB_V2] Found {len(candidates)} entry candidates")
        return candidates[:self.max_positions * 2]

    def record_entry(self, symbol: str) -> None:
        """Record that a position was entered for this symbol today"""
        self._mark_traded(symbol)
        logger.info(f"[ORB_V2] Recorded entry for {symbol}")

    def __repr__(self) -> str:
        return (f"ORBV2Strategy(max_range_width={self.max_range_width_pct:.1%}, "
                f"target={self.TARGET_MULTIPLIER:.0%}, "
                f"max_pos={self.max_positions}, eod={self.eod_exit_time})")
