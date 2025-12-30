"""
60-Minute Opening Range Breakout (ORB) Strategy

Win Rate: 89.4%
Timeframe: Intraday (same-day entry and exit)

Entry Conditions (All Required):
- Time > 10:30 AM ET (60-min range established)
- Price closes ABOVE 60-min opening range HIGH
- Volume > 1.5x relative volume (vs 20-day avg at same time)
- Price > VWAP
- 20 EMA slope is UP (current > previous bar)

Exit Conditions (First Triggered):
- TARGET: Range height projected from breakout point
- STOP: Few ticks inside range (below range high for longs)
- TIME: 2:00 PM ET forced exit (ORB works early in day)
- EOD: Any remaining positions closed
"""

from typing import Dict, List, Optional
from datetime import datetime, time as dt_time
import logging

from .base_strategy import BaseStrategy, EntrySignal, ExitSignal
from data.intraday_indicators import IntradayIndicators

logger = logging.getLogger(__name__)


class ORBStrategy(BaseStrategy):
    """
    60-Minute Opening Range Breakout Strategy

    Trades breakouts above the first 60 minutes' high with volume confirmation.
    89.4% win rate with 1.44 profit factor (backtested).
    """

    # Strategy-specific constants
    OPENING_RANGE_MINUTES = 60
    MIN_RELATIVE_VOLUME = 1.5
    RANGE_START = dt_time(9, 30)
    RANGE_END = dt_time(10, 30)
    STOP_BUFFER_PCT = 0.001  # 0.1% inside range for stop

    def __init__(
        self,
        indicators: IntradayIndicators,
        max_positions: int = 5,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(14, 0),  # 2:00 PM for ORB
        min_price: float = 5.0,
        min_relative_volume: float = 1.5,
    ):
        """
        Initialize ORB Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            max_positions: Maximum simultaneous positions (default 5)
            position_size_pct: Position size as % of equity (default 10%)
            risk_per_trade_pct: Max risk per trade (default 2%)
            eod_exit_time: Force exit time (default 2:00 PM for ORB)
            min_price: Minimum stock price (default $5)
            min_relative_volume: Minimum relative volume (default 1.5x)
        """
        super().__init__(
            name="ORB",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.min_relative_volume = min_relative_volume

        # Cache opening ranges for the day (reset daily)
        self._opening_ranges: Dict[str, Dict] = {}
        self._cache_date: Optional[datetime] = None

    def _ensure_cache_fresh(self):
        """Clear cache if it's a new trading day"""
        today = datetime.now().date()
        if self._cache_date != today:
            self._opening_ranges.clear()
            self._cache_date = today

    def _get_opening_range(self, symbol: str) -> Optional[Dict]:
        """Get opening range, using cache if available"""
        self._ensure_cache_fresh()

        if symbol not in self._opening_ranges:
            or_data = self.indicators.get_opening_range(symbol)
            if or_data:
                self._opening_ranges[symbol] = or_data

        return self._opening_ranges.get(symbol)

    def is_trading_time(self) -> bool:
        """Check if we're in the valid trading window for ORB (after 10:30 AM)"""
        now = datetime.now().time()
        return now >= self.RANGE_END and now < self.eod_exit_time

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets ORB entry criteria.

        Entry Conditions:
        1. Time > 10:30 AM (range established)
        2. Price > Opening Range High (breakout)
        3. Relative Volume > 1.5x
        4. Price > VWAP
        5. EMA(20) slope > 0

        Returns:
            EntrySignal if all conditions met, None otherwise
        """
        now = datetime.now()

        # Time check: must be after 10:30 AM
        if now.time() < self.RANGE_END:
            return None

        # Get current price
        current_price = self.indicators.get_current_price(symbol)
        if current_price is None or current_price < self.min_price:
            return None

        # Get opening range
        opening_range = self._get_opening_range(symbol)
        if opening_range is None:
            return None

        # Condition 1: Price > Opening Range High (breakout)
        if current_price <= opening_range['high']:
            return None

        # Condition 2: Relative Volume > 1.5x
        rel_vol = self.indicators.get_relative_volume(symbol)
        if rel_vol is None or rel_vol < self.min_relative_volume:
            return None

        # Condition 3: Price > VWAP
        vwap = self.indicators.get_current_vwap(symbol)
        if vwap is None or current_price <= vwap:
            return None

        # Condition 4: EMA(20) slope > 0 (uptrend)
        ema_slope = self.indicators.get_ema_slope(symbol, 20)
        if ema_slope is None or ema_slope <= 0:
            return None

        # All conditions met - calculate target and stop
        target = self.indicators.get_breakout_target(current_price, opening_range, 'long')
        stop = self.indicators.get_breakout_stop(opening_range, 'long', self.STOP_BUFFER_PCT)

        return EntrySignal(
            symbol=symbol,
            price=current_price,
            target=target,
            stop=stop,
            reason="ORB breakout above range high",
            metadata={
                'opening_range_high': opening_range['high'],
                'opening_range_low': opening_range['low'],
                'range_size': opening_range['range_size'],
                'relative_volume': rel_vol,
                'vwap': vwap,
                'ema_slope': ema_slope,
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions:
        1. Price >= Target (range height projected from entry)
        2. Price <= Stop (inside opening range)
        3. Time >= 2:00 PM ET

        Args:
            position: Dict with keys: entry_price, shares, entry_time, target, stop

        Returns:
            ExitSignal if exit condition met, None otherwise
        """
        now = datetime.now()
        current_price = self.indicators.get_current_price(symbol)

        if current_price is None:
            return None

        entry_price = position.get('entry_price', 0)
        target = position.get('target')
        stop = position.get('stop')

        # Calculate P&L percentage
        pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

        # Condition 1: Target hit
        if target and current_price >= target:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='target',
                pnl_pct=pnl_pct,
                metadata={'target': target, 'entry_price': entry_price}
            )

        # Condition 2: Stop hit
        if stop and current_price <= stop:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='stop',
                pnl_pct=pnl_pct,
                metadata={'stop': stop, 'entry_price': entry_price}
            )

        # Condition 3: EOD exit time (2:00 PM for ORB)
        if now.time() >= self.eod_exit_time:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={'eod_time': str(self.eod_exit_time), 'entry_price': entry_price}
            )

        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen all symbols for ORB entry candidates.

        Uses the bulk screening query from IntradayIndicators for efficiency.

        Returns:
            List of EntrySignal objects sorted by relative volume (highest first)
        """
        now = datetime.now()

        # Not in trading window
        if now.time() < self.RANGE_END:
            logger.info(f"[ORB] Too early for entries (before {self.RANGE_END})")
            return []

        if now.time() >= self.eod_exit_time:
            logger.info(f"[ORB] Past EOD exit time ({self.eod_exit_time})")
            return []

        # Use bulk screening
        raw_candidates = self.indicators.get_orb_candidates(
            min_relative_volume=self.min_relative_volume,
            min_price=self.min_price,
            max_candidates=self.max_positions * 3,  # Get extras for filtering
        )

        # Convert to EntrySignal objects
        signals = []
        for candidate in raw_candidates:
            signals.append(EntrySignal(
                symbol=candidate['symbol'],
                price=candidate['price'],
                target=candidate['target'],
                stop=candidate['stop'],
                reason="ORB breakout",
                metadata={
                    'relative_volume': candidate['relative_volume'],
                    'vwap': candidate['vwap'],
                    'ema_slope': candidate['ema_slope'],
                    'opening_range': candidate['opening_range'],
                }
            ))

        logger.info(f"[ORB] Found {len(signals)} entry candidates")
        return signals

    def __repr__(self) -> str:
        return (f"ORBStrategy(max_pos={self.max_positions}, "
                f"eod={self.eod_exit_time}, min_rvol={self.min_relative_volume})")
