"""
VWAP Pullback Strategy (LONG ONLY)

Mid-day mean reversion: Buy when price pulls back to VWAP from above.
Entry: 10:00 AM - 2:00 PM ET
Exit: Target, Stop (0.3% below VWAP), VWAP loss, or 2:00 PM forced

Direction: LONG ONLY

Win Rate Target: ~65-70% (mean reversion)
Risk/Reward: 1.5:1 minimum

Strategy Logic:
1. Find stocks trading ABOVE VWAP (established strength)
2. Wait for price to pull back TO VWAP (within 0.2%)
3. Confirm bounce: 3 candles holding above VWAP after touch
4. Enter long with stop 0.3% below VWAP
5. Target: Prior swing high or 1.5:1 R/R
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


class VWAPPullbackStrategy(BaseStrategy):
    """
    VWAP Pullback - Mid-Day Mean Reversion (LONG ONLY)

    Buys when price pulls back to VWAP from above and bounces.
    Entries 10:00 AM - 2:00 PM, all positions closed by 2:00 PM.

    Entry Conditions:
    1. Time between 10:00 AM - 2:00 PM ET
    2. Stock price >= $10, average volume >= 500k
    3. Price was trading above VWAP (within last 10 candles)
    4. Price pulled back to VWAP (within 0.2%)
    5. Price bouncing: 3 consecutive candles holding above VWAP

    Exit Conditions:
    1. Target hit: Prior swing high OR 1.5:1 R/R from entry
    2. Stop hit: 0.3% below VWAP
    3. VWAP lost: Price closes below VWAP for 3 consecutive candles
    4. EOD: 2:00 PM ET forced exit
    """

    # Strategy-specific constants
    ENTRY_WINDOW_START = dt_time(10, 0)
    ENTRY_WINDOW_END = dt_time(14, 0)
    EOD_EXIT = dt_time(14, 0)
    MIN_PRICE = 10.0
    MIN_AVG_VOLUME = 500_000
    PULLBACK_THRESHOLD = 0.002  # 0.2% from VWAP = "at VWAP"
    STOP_BELOW_VWAP_PCT = 0.003  # 0.3% below VWAP
    RR_RATIO = 1.5  # 1.5:1 reward to risk
    CANDLES_FOR_BOUNCE = 3  # Wait 3 candles to confirm bounce
    CANDLES_FOR_VWAP_LOSS = 3  # 3 closes below VWAP = exit
    LOOKBACK_FOR_ABOVE_VWAP = 10  # Check last 10 candles for "was above VWAP"

    def __init__(
        self,
        indicators: IntradayIndicators,
        max_positions: int = 5,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.015,
        eod_exit_time: dt_time = dt_time(14, 0),
        min_price: float = 10.0,
        min_avg_volume: int = 500_000,
    ):
        """
        Initialize VWAP Pullback Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            max_positions: Maximum simultaneous positions (default 5)
            position_size_pct: Position size as % of equity (default 10%)
            risk_per_trade_pct: Max risk per trade (default 1.5%)
            eod_exit_time: Force exit time (default 2:00 PM)
            min_price: Minimum stock price (default $10)
            min_avg_volume: Minimum average volume (default 500k)
        """
        super().__init__(
            name="VWAP_PULLBACK",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.min_avg_volume = min_avg_volume

        # Track daily trades to enforce max 1 trade per symbol per day
        self._daily_trades: Dict[date, Set[str]] = {}

        # Track symbols that touched VWAP and are bouncing
        # Key: symbol, Value: count of candles above VWAP since touch
        self._bounce_tracking: Dict[str, int] = {}

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

    def is_entry_window(self) -> bool:
        """Check if we're in entry window (10:00 AM - 2:00 PM ET)."""
        now_et = self._get_current_et().time()
        return self.ENTRY_WINDOW_START <= now_et < self.ENTRY_WINDOW_END

    def _is_at_vwap(self, price: float, vwap: float) -> bool:
        """
        Check if price is within 0.2% of VWAP (at VWAP level).

        Args:
            price: Current price
            vwap: Current VWAP value

        Returns:
            True if price is within PULLBACK_THRESHOLD of VWAP
        """
        if vwap <= 0:
            return False
        distance_pct = abs(price - vwap) / vwap
        return distance_pct <= self.PULLBACK_THRESHOLD

    def _was_above_vwap(self, symbol: str, bars: List[Dict], vwap_values: List[float],
                        lookback: int = 10) -> bool:
        """
        Check if price was above VWAP in recent candles (before pullback).

        We want stocks that were trading ABOVE VWAP and pulled back to it,
        not stocks that were below and just touched it.

        Args:
            symbol: Stock symbol
            bars: Recent bars
            vwap_values: Corresponding VWAP values
            lookback: Number of candles to look back

        Returns:
            True if at least one candle in lookback was significantly above VWAP
        """
        if len(bars) < lookback or len(vwap_values) < lookback:
            return False

        # Check last N candles (excluding the most recent few which should be at VWAP)
        # We want to see the stock was trading above VWAP before the pullback
        check_start = max(0, len(bars) - lookback)
        check_end = len(bars) - self.CANDLES_FOR_BOUNCE  # Exclude bounce candles

        if check_end <= check_start:
            return False

        for i in range(check_start, check_end):
            if i >= len(vwap_values):
                continue
            close = bars[i]['close']
            vwap = vwap_values[i]
            if vwap > 0:
                # Stock was meaningfully above VWAP (at least 0.3% above)
                if (close - vwap) / vwap > 0.003:
                    return True

        return False

    def _is_bouncing(self, bars: List[Dict], vwap_values: List[float]) -> bool:
        """
        Check if price is bouncing off VWAP.

        Bounce confirmation: Last CANDLES_FOR_BOUNCE candles all closed above VWAP.

        Args:
            bars: Recent bars (oldest first)
            vwap_values: Corresponding VWAP values

        Returns:
            True if last N candles all closed above VWAP
        """
        if len(bars) < self.CANDLES_FOR_BOUNCE or len(vwap_values) < self.CANDLES_FOR_BOUNCE:
            return False

        # Check last N candles
        for i in range(-self.CANDLES_FOR_BOUNCE, 0):
            if bars[i]['close'] <= vwap_values[i]:
                return False

        return True

    def _get_prior_swing_high(self, bars: List[Dict], lookback: int = 30) -> Optional[float]:
        """
        Find the prior swing high before the pullback.

        A swing high is a local maximum (high > highs on both sides).

        Args:
            bars: Recent bars
            lookback: Number of bars to search

        Returns:
            Prior swing high price or None
        """
        if len(bars) < 10:
            return None

        # Search for swing highs in the lookback period
        # Exclude very recent bars (the pullback area)
        search_start = max(0, len(bars) - lookback)
        search_end = len(bars) - 5  # Exclude recent pullback

        swing_highs = []
        for i in range(search_start + 2, search_end - 2):
            # Check if this is a local high
            is_swing = True
            current_high = bars[i]['high']
            for j in range(i - 2, i + 3):
                if j != i and j < len(bars):
                    if bars[j]['high'] >= current_high:
                        is_swing = False
                        break
            if is_swing:
                swing_highs.append(current_high)

        if swing_highs:
            # Return the most recent swing high
            return swing_highs[-1]

        # Fallback: return the highest high in the lookback period
        search_bars = bars[search_start:search_end]
        if search_bars:
            return max(b['high'] for b in search_bars)

        return None

    def _get_average_volume(self, symbol: str) -> Optional[float]:
        """
        Get approximate average volume for liquidity check.

        Uses today's bars to estimate if stock is liquid enough.

        Args:
            symbol: Stock symbol

        Returns:
            Average volume estimate or None
        """
        bars = self.indicators.get_todays_bars(symbol)
        if not bars or len(bars) < 10:
            return None

        total_volume = sum(b['volume'] for b in bars)
        # Extrapolate to full day (390 minutes)
        minutes_elapsed = len(bars)
        if minutes_elapsed > 0:
            projected_volume = (total_volume / minutes_elapsed) * 390
            return projected_volume

        return None

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets VWAP Pullback entry criteria.

        Entry Conditions:
        1. In entry window (10:00 AM - 2:00 PM)
        2. Price >= $10, liquid stock
        3. Price was above VWAP in recent candles
        4. Price pulled back to VWAP (within 0.2%)
        5. Price bouncing (3 candles above VWAP after touch)

        Returns:
            EntrySignal if all conditions met, None otherwise
        """
        # Time check
        if not self.is_entry_window():
            return None

        # Check if already traded today
        if symbol in self._get_traded_today():
            return None

        # Get today's bars for VWAP calculation
        todays_bars = self.indicators.get_todays_bars(symbol)
        if not todays_bars or len(todays_bars) < 20:
            return None

        # Get current price
        current_price = todays_bars[-1]['close']

        # Price filter
        if current_price < self.min_price:
            return None

        # Liquidity check (approximate)
        avg_volume = self._get_average_volume(symbol)
        if avg_volume is not None and avg_volume < self.min_avg_volume:
            return None

        # Calculate VWAP for all bars
        vwap_values = self.indicators.calculate_vwap(todays_bars)
        if not vwap_values:
            return None

        current_vwap = vwap_values[-1]
        if current_vwap <= 0:
            return None

        # Condition 1: Current price must be above VWAP (after bounce)
        if current_price <= current_vwap:
            return None

        # Condition 2: Price was trading above VWAP before pullback
        if not self._was_above_vwap(symbol, todays_bars, vwap_values,
                                     self.LOOKBACK_FOR_ABOVE_VWAP):
            return None

        # Condition 3: Price is bouncing (last N candles above VWAP)
        if not self._is_bouncing(todays_bars, vwap_values):
            return None

        # Condition 4: Price touched VWAP recently (within last 10 candles)
        # Look for a candle that was "at VWAP" before the bounce
        touched_vwap = False
        check_start = max(0, len(todays_bars) - 10)
        for i in range(check_start, len(todays_bars) - self.CANDLES_FOR_BOUNCE + 1):
            low_price = todays_bars[i]['low']
            if self._is_at_vwap(low_price, vwap_values[i]):
                touched_vwap = True
                break

        if not touched_vwap:
            return None

        # Calculate target and stop
        stop_price = current_vwap * (1 - self.STOP_BELOW_VWAP_PCT)
        risk = current_price - stop_price

        # Target: Prior swing high or 1.5:1 R/R
        prior_high = self._get_prior_swing_high(todays_bars)
        rr_target = current_price + (risk * self.RR_RATIO)

        # Use the better target (higher of swing high or R/R target)
        if prior_high and prior_high > current_price:
            target_price = max(prior_high, rr_target)
        else:
            target_price = rr_target

        # Ensure minimum R/R
        if target_price - current_price < risk * self.RR_RATIO:
            target_price = current_price + (risk * self.RR_RATIO)

        logger.info(f"[VWAP_PULLBACK] {symbol}: Entry signal at ${current_price:.2f}, "
                   f"VWAP=${current_vwap:.2f}, Target=${target_price:.2f}, "
                   f"Stop=${stop_price:.2f}")

        return EntrySignal(
            symbol=symbol,
            price=current_price,
            target=target_price,
            stop=stop_price,
            reason=f"VWAP Pullback: Bounce off VWAP ${current_vwap:.2f}",
            metadata={
                'direction': 'long',
                'vwap': current_vwap,
                'prior_high': prior_high,
                'rr_target': rr_target,
                'risk': risk,
                'avg_volume': avg_volume,
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions:
        1. Target hit (1.5:1 R/R or prior high)
        2. Stop hit (0.3% below VWAP at entry)
        3. Price closes below VWAP for 3 consecutive candles
        4. Time >= 2:00 PM ET (EOD)

        Args:
            position: Dict with keys: entry_price, shares, entry_time, target, stop

        Returns:
            ExitSignal if exit condition met, None otherwise
        """
        now_et = self._get_current_et()

        # Get current price and VWAP
        todays_bars = self.indicators.get_todays_bars(symbol)
        if not todays_bars:
            return None

        current_price = todays_bars[-1]['close']
        vwap_values = self.indicators.calculate_vwap(todays_bars)
        current_vwap = vwap_values[-1] if vwap_values else None

        entry_price = position.get('entry_price', 0)
        pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

        # Condition 1: EOD exit time (highest priority)
        if now_et.time() >= self.eod_exit_time:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={'eod_time': str(self.eod_exit_time), 'vwap': current_vwap}
            )

        # Get target and stop from position
        target = position.get('target')
        stop = position.get('stop')

        # Condition 2: Target hit
        if target and current_price >= target:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='target',
                pnl_pct=pnl_pct,
                metadata={'target': target, 'hit_price': current_price, 'vwap': current_vwap}
            )

        # Condition 3: Stop hit
        if stop and current_price <= stop:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='stop',
                pnl_pct=pnl_pct,
                metadata={'stop': stop, 'hit_price': current_price, 'vwap': current_vwap}
            )

        # Condition 4: VWAP lost - 3 consecutive closes below VWAP
        if current_vwap and len(todays_bars) >= self.CANDLES_FOR_VWAP_LOSS:
            candles_below = 0
            for i in range(-self.CANDLES_FOR_VWAP_LOSS, 0):
                if todays_bars[i]['close'] < vwap_values[i]:
                    candles_below += 1
                else:
                    break

            if candles_below >= self.CANDLES_FOR_VWAP_LOSS:
                return ExitSignal(
                    symbol=symbol,
                    price=current_price,
                    reason='signal',
                    pnl_pct=pnl_pct,
                    metadata={
                        'exit_reason': 'vwap_lost',
                        'candles_below': candles_below,
                        'vwap': current_vwap
                    }
                )

        return None

    def _get_tradeable_universe(self) -> List[str]:
        """
        Get liquid stocks that are candidates for VWAP pullback.

        Filters:
        - Price >= $10
        - Currently above VWAP
        - Reasonable liquidity

        Returns:
            List of symbols meeting basic criteria
        """
        all_symbols = self.indicators.get_all_symbols()
        tradeable = []

        for symbol in all_symbols:
            try:
                # Get current price
                bars = self.indicators.get_latest_bars(symbol, 5)
                if not bars:
                    continue

                current_price = bars[-1]['close']

                # Price filter
                if current_price < self.min_price:
                    continue

                # Get VWAP
                vwap = self.indicators.get_current_vwap(symbol)
                if vwap is None or vwap <= 0:
                    continue

                # Must be above VWAP (strength)
                if current_price <= vwap:
                    continue

                tradeable.append(symbol)

            except Exception as e:
                logger.debug(f"Error filtering {symbol}: {e}")
                continue

        return tradeable

    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen for VWAP pullback candidates.

        Returns stocks pulling back to VWAP from above with bounce confirmation.

        Returns:
            List of EntrySignal objects sorted by distance from VWAP (closer = better)
        """
        if not self.is_entry_window():
            now_et = self._get_current_et().time()
            logger.info(f"[VWAP_PULLBACK] Outside entry window "
                       f"(10:00 AM - 2:00 PM). Current: {now_et}")
            return []

        traded_today = self._get_traded_today()
        candidates = []

        # Get all symbols and screen
        symbols = self.indicators.get_all_symbols()
        logger.info(f"[VWAP_PULLBACK] Screening {len(symbols)} symbols for pullback setups")

        for symbol in symbols:
            # Skip if already traded today
            if symbol in traded_today:
                continue

            try:
                signal = self.check_entry(symbol)
                if signal:
                    candidates.append(signal)

                    # Limit candidates to avoid over-screening
                    if len(candidates) >= self.max_positions * 3:
                        break

            except Exception as e:
                logger.debug(f"Error checking {symbol} for VWAP pullback: {e}")
                continue

        # Sort by distance from VWAP (smaller = tighter setup)
        def vwap_distance(signal: EntrySignal) -> float:
            vwap = signal.metadata.get('vwap', 0) if signal.metadata else 0
            if vwap > 0:
                return abs(signal.price - vwap) / vwap
            return 999

        candidates.sort(key=vwap_distance)

        logger.info(f"[VWAP_PULLBACK] Found {len(candidates)} entry candidates")
        return candidates[:self.max_positions * 2]

    def record_entry(self, symbol: str) -> None:
        """Record that a position was entered for this symbol today."""
        self._mark_traded(symbol)
        logger.info(f"[VWAP_PULLBACK] Recorded entry for {symbol}")

    def __repr__(self) -> str:
        return (f"VWAPPullbackStrategy(min_price=${self.min_price:.0f}, "
                f"stop={self.STOP_BELOW_VWAP_PCT:.1%}, "
                f"rr={self.RR_RATIO:.1f}:1, "
                f"max_pos={self.max_positions}, eod={self.eod_exit_time})")
