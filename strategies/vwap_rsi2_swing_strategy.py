"""
VWAP + RSI(2) Hybrid Swing Strategy (LONG ONLY)

Combines intraday VWAP confirmation with daily RSI(2) oversold signals.
This strategy HOLDS OVERNIGHT and exits the next morning.

Direction: LONG ONLY (no shorting)

Universe Filter (run once at 9:45 AM):
- Price > SMA(200) - long-term uptrend
- Price > $5 - avoid penny stocks
- RVOL > 1.5 - stock is "in play"
- ADX > 20 - enough volatility to move
- Overnight Gap % > -3% - not gapping down hard into downtrend

Entry Signal (scan every 5-min bar, 10:00 AM - 3:30 PM):
- Price > VWAP - intraday bullish bias
- RSI(2) < 10 OR Connors RSI < 15 - oversold
- Close of current 5-min bar > Open - buying pressure on signal bar
- No existing position in this stock - 1 entry per stock per day
- Total positions < 5 - max concurrent positions

Exit Rules (priority order):
1. Profit target: Exit if RSI(2) > 70
2. Next-day exit: Exit at 9:35 AM next day
3. Stop loss: Exit if Close < VWAP Lower Band
4. Trend break: Exit if Close < SMA(200) at end of day (3:55 PM)
5. Time stop: Exit any position held 2+ days at 9:35 AM Day 3

Position Sizing:
- Max positions: 5
- Position size: 20% of portfolio each
- Max 1 entry per stock per day
"""

from typing import Dict, List, Optional, Set
from datetime import datetime, time as dt_time, date, timedelta
from dataclasses import dataclass
import logging

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .base_strategy import BaseStrategy, EntrySignal, ExitSignal
from data.intraday_indicators import IntradayIndicators
from data.indicators_db import IndicatorsDB, normalize_symbol

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET = ZoneInfo('America/New_York')


@dataclass
class UniverseStock:
    """Represents a stock that passed the universe filter."""
    symbol: str
    price: float
    sma200: float
    rvol: float
    adx: float
    gap_pct: float


class VwapRsi2SwingStrategy(BaseStrategy):
    """
    VWAP + RSI(2) Hybrid Swing Strategy (LONG ONLY)

    Combines intraday VWAP confirmation with RSI(2) oversold signals.
    This strategy HOLDS OVERNIGHT and exits the next morning.

    Key characteristics:
    - Overnight holds (does NOT exit at EOD)
    - Uses daily RSI(2) and ConnorsRSI from indicators table
    - Uses real-time VWAP from intraday bars
    - Morning exit logic at 9:35 AM next day
    - Time stop at Day 3 open
    """

    # Strategy-specific time constants
    MARKET_OPEN = dt_time(9, 30)
    UNIVERSE_FILTER_TIME = dt_time(9, 45)
    ENTRY_WINDOW_START = dt_time(10, 0)
    ENTRY_WINDOW_END = dt_time(15, 30)  # 3:30 PM
    MORNING_EXIT_TIME = dt_time(9, 35)
    TREND_CHECK_TIME = dt_time(15, 55)  # 3:55 PM for trend break check

    # Filter thresholds
    MIN_SMA200_ABOVE = 0  # Price must be > SMA200 (positive difference)
    MIN_RVOL = 1.5
    MIN_ADX = 20.0
    MAX_GAP_DOWN_PCT = -3.0  # Don't buy stocks gapping down > 3%

    # Entry thresholds
    MAX_RSI2_ENTRY = 10
    MAX_CRSI_ENTRY = 15

    # Exit thresholds
    RSI2_PROFIT_TARGET = 70
    MAX_HOLDING_DAYS = 2

    def __init__(
        self,
        indicators: IntradayIndicators,
        indicators_db: Optional[IndicatorsDB] = None,
        max_positions: int = 5,
        position_size_pct: float = 0.20,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(15, 55),  # Not used for forced exits
        min_price: float = 5.0,
    ):
        """
        Initialize VWAP + RSI(2) Swing Strategy.

        Args:
            indicators: IntradayIndicators instance for real-time data
            indicators_db: IndicatorsDB instance for daily indicators (RSI2, CRSI, SMA200, ADX)
            max_positions: Maximum simultaneous positions (default 5)
            position_size_pct: Position size as % of equity (default 20%)
            risk_per_trade_pct: Max risk per trade (default 2%)
            eod_exit_time: End of day check time (default 3:55 PM) - NOT for forced exits
            min_price: Minimum stock price (default $5)
        """
        super().__init__(
            name="VWAP_RSI2_SWING",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.indicators_db = indicators_db or IndicatorsDB()

        # Track daily trades to enforce max 1 trade per symbol per day
        self._daily_trades: Dict[date, Set[str]] = {}

        # Cache for universe filter results (computed once at 9:45 AM)
        self._universe_cache: List[UniverseStock] = []
        self._universe_cache_date: Optional[date] = None

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

    def _clear_cache_if_new_day(self) -> None:
        """Clear universe cache if it's a new day."""
        today = self._get_current_et().date()
        if self._universe_cache_date != today:
            self._universe_cache = []
            self._universe_cache_date = today

    def is_entry_window(self) -> bool:
        """Check if we're in the entry window (10:00 AM - 3:30 PM ET)."""
        now_et = self._get_current_et().time()
        return self.ENTRY_WINDOW_START <= now_et < self.ENTRY_WINDOW_END

    def is_morning_exit_time(self) -> bool:
        """Check if we're at the morning exit time (9:35 AM ET)."""
        now_et = self._get_current_et().time()
        # Allow a 5-minute window for the morning exit check
        morning_exit_end = dt_time(9, 40)
        return self.MORNING_EXIT_TIME <= now_et < morning_exit_end

    def is_trend_check_time(self) -> bool:
        """Check if we're at the end-of-day trend check time (3:55 PM ET)."""
        now_et = self._get_current_et().time()
        return now_et >= self.TREND_CHECK_TIME

    def _get_universe_filter(self) -> List[UniverseStock]:
        """
        Run universe filter at 9:45 AM to identify tradeable stocks.

        Criteria:
        - Price > SMA(200) - long-term uptrend
        - Price > $5 - avoid penny stocks
        - RVOL > 1.5 - stock is "in play"
        - ADX > 20 - enough volatility to move
        - Overnight Gap % > -3% - not gapping down hard

        Returns:
            List of UniverseStock objects that pass the filter
        """
        self._clear_cache_if_new_day()

        # Return cached results if available
        if self._universe_cache:
            return self._universe_cache

        now_et = self._get_current_et()

        # Only run the full filter after 9:45 AM
        if now_et.time() < self.UNIVERSE_FILTER_TIME:
            logger.debug(
                f"[VWAP_RSI2_SWING] Too early for universe filter, "
                f"current time: {now_et.time()}"
            )
            return []

        symbols = self.indicators.get_all_symbols()
        universe = []

        for symbol in symbols:
            try:
                # Get daily indicators from database
                indicator_data = self.indicators_db.get_indicator(symbol)
                if indicator_data is None:
                    continue

                # Extract required fields
                close_price = indicator_data.get('close')
                sma200 = indicator_data.get('sma200')
                adx = indicator_data.get('adx')

                # Validate required fields
                if close_price is None or sma200 is None:
                    continue

                # Price filter
                if close_price < self.min_price:
                    continue

                # Long-term uptrend: Price > SMA(200)
                if close_price <= sma200:
                    continue

                # ADX filter: Must have enough volatility
                if adx is None or adx < self.MIN_ADX:
                    continue

                # Calculate RVOL from intraday data
                rvol = self.indicators.calculate_relative_volume(symbol, lookback_days=5)
                if rvol is None or rvol < self.MIN_RVOL:
                    continue

                # Calculate overnight gap
                gap_data = self.indicators.get_overnight_gap(symbol, now_et)
                if gap_data is None:
                    gap_pct = 0.0  # Default to neutral if no gap data
                else:
                    gap_pct = gap_data['gap_pct']

                # Filter out stocks gapping down hard
                if gap_pct < self.MAX_GAP_DOWN_PCT:
                    continue

                # Stock passes all filters
                universe.append(UniverseStock(
                    symbol=symbol,
                    price=close_price,
                    sma200=sma200,
                    rvol=rvol,
                    adx=adx,
                    gap_pct=gap_pct,
                ))

            except Exception as e:
                logger.debug(f"Error filtering {symbol} for universe: {e}")
                continue

        # Cache the results
        self._universe_cache = universe
        self._universe_cache_date = now_et.date()

        logger.info(
            f"[VWAP_RSI2_SWING] Universe filter complete: "
            f"{len(universe)} stocks pass filters out of {len(symbols)}"
        )

        return universe

    def _get_current_5min_bar(self, symbol: str) -> Optional[Dict]:
        """
        Get the current (most recent) 5-minute bar for a symbol.

        Returns:
            Dict with open, high, low, close, volume or None if no data
        """
        now_et = self._get_current_et()

        # Get last 5 minutes of 1-min bars
        end_ts = self.indicators._et_to_timestamp(now_et.date(), now_et.time())
        start_ts = end_ts - (5 * 60)  # 5 minutes ago

        bars = self.indicators.get_bars(symbol, start_ts, end_ts)

        if not bars or len(bars) < 1:
            return None

        # Aggregate into 5-min bar
        candle_open = bars[0]['open']
        candle_high = max(b['high'] for b in bars)
        candle_low = min(b['low'] for b in bars)
        candle_close = bars[-1]['close']
        candle_volume = sum(b['volume'] for b in bars)

        return {
            'open': candle_open,
            'high': candle_high,
            'low': candle_low,
            'close': candle_close,
            'volume': candle_volume,
        }

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets entry criteria.

        Entry Conditions (all must be true):
        1. In entry window (10:00 AM - 3:30 PM ET)
        2. Symbol in universe (passed filter)
        3. Price > VWAP - intraday bullish bias
        4. RSI(2) < 10 OR Connors RSI < 15 - oversold
        5. Close of current 5-min bar > Open - buying pressure
        6. Not already traded today

        Returns:
            EntrySignal if all conditions met, None otherwise
        """
        # Time check - must be in entry window
        if not self.is_entry_window():
            return None

        # Check if already traded today
        if symbol in self._get_traded_today():
            return None

        # Check if symbol is in universe
        universe = self._get_universe_filter()
        universe_symbols = {s.symbol for s in universe}

        # Normalize symbol for comparison
        normalized_symbol = normalize_symbol(symbol)
        if normalized_symbol not in universe_symbols and symbol not in universe_symbols:
            return None

        # Get daily indicators from database
        indicator_data = self.indicators_db.get_indicator(symbol)
        if indicator_data is None:
            return None

        rsi2 = indicator_data.get('rsi2')
        crsi = indicator_data.get('crsi')
        sma200 = indicator_data.get('sma200')
        adx = indicator_data.get('adx')
        close_price = indicator_data.get('close')

        # Re-validate universe filters at entry time (VV7 updates every 5 min)
        # ADX filter: Must have enough trend strength
        if adx is None or adx < self.MIN_ADX:
            logger.debug(f"[VWAP_RSI2_SWING] {symbol} rejected: ADX={adx} < {self.MIN_ADX}")
            return None

        # SMA200 filter: Price must be above long-term trend
        if close_price is None or sma200 is None or close_price <= sma200:
            logger.debug(f"[VWAP_RSI2_SWING] {symbol} rejected: Price {close_price} <= SMA200 {sma200}")
            return None

        # Check oversold condition: RSI(2) < 10 OR CRSI < 15
        is_oversold = False
        oversold_reason = ""

        if rsi2 is not None and rsi2 < self.MAX_RSI2_ENTRY:
            is_oversold = True
            oversold_reason = f"RSI(2)={rsi2:.1f}"
        elif crsi is not None and crsi < self.MAX_CRSI_ENTRY:
            is_oversold = True
            oversold_reason = f"CRSI={crsi:.1f}"

        if not is_oversold:
            return None

        # Get current VWAP with bands
        vwap_data = self.indicators.get_vwap_with_bands(symbol)
        if vwap_data is None:
            return None

        vwap = vwap_data['vwap']
        vwap_lower = vwap_data['lower_band']
        current_price = vwap_data['current_price']

        # Price must be above VWAP (intraday bullish bias)
        if current_price <= vwap:
            return None

        # Get current 5-min bar to check buying pressure
        bar_5min = self._get_current_5min_bar(symbol)
        if bar_5min is None:
            return None

        # Close must be > Open (buying pressure on signal bar)
        if bar_5min['close'] <= bar_5min['open']:
            return None

        # Calculate stop loss (VWAP lower band)
        stop_price = vwap_lower

        # No fixed target - exit on RSI(2) > 70 or next morning
        # Use SMA200 as a reference target for position sizing
        target_price = None

        return EntrySignal(
            symbol=symbol,
            price=current_price,
            target=target_price,
            stop=stop_price,
            reason=(
                f"VWAP+RSI2 Swing: {oversold_reason}, "
                f"Price ${current_price:.2f} > VWAP ${vwap:.2f}"
            ),
            metadata={
                'direction': 'long',
                'rsi2': rsi2,
                'crsi': crsi,
                'adx': adx,
                'vwap': vwap,
                'vwap_lower': vwap_lower,
                'vwap_upper': vwap_data['upper_band'],
                'sma200': sma200,
                'bar_5min_open': bar_5min['open'],
                'bar_5min_close': bar_5min['close'],
                'holds_overnight': True,
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions (priority order):
        1. Profit target: Exit if RSI(2) > 70
        2. Next-day exit: Exit at 9:35 AM next day
        3. Stop loss: Exit if Close < VWAP Lower Band
        4. Trend break: Exit if Close < SMA(200) at 3:55 PM
        5. Time stop: Exit any position held 2+ days at 9:35 AM Day 3

        Args:
            position: Dict with keys: entry_price, shares, entry_time,
                      entry_date, target, stop, etc.

        Returns:
            ExitSignal if exit condition met, None otherwise
        """
        now_et = self._get_current_et()

        # Get current price from latest bars
        bars = self.indicators.get_latest_bars(symbol, 5)
        if not bars:
            return None

        current_price = bars[-1]['close']
        entry_price = position.get('entry_price', 0)
        pnl_pct = (
            ((current_price - entry_price) / entry_price) * 100
            if entry_price > 0
            else 0
        )

        # Get entry date from position
        entry_date = position.get('entry_date')
        if entry_date is None:
            # Try to parse from entry_time
            entry_time_str = position.get('entry_time')
            if entry_time_str:
                try:
                    if isinstance(entry_time_str, str):
                        entry_date = datetime.fromisoformat(entry_time_str).date()
                    elif isinstance(entry_time_str, datetime):
                        entry_date = entry_time_str.date()
                except (ValueError, TypeError):
                    entry_date = now_et.date()
            else:
                entry_date = now_et.date()

        # Calculate days held
        days_held = (now_et.date() - entry_date).days if entry_date else 0

        # Get daily indicators
        indicator_data = self.indicators_db.get_indicator(symbol)
        rsi2 = indicator_data.get('rsi2') if indicator_data else None
        sma200 = indicator_data.get('sma200') if indicator_data else None

        # =========================================================
        # Exit Condition 1: Profit Target - RSI(2) > 70 AND profitable
        # Only exit on RSI recovery if we're actually in profit
        # =========================================================
        if rsi2 is not None and rsi2 > self.RSI2_PROFIT_TARGET and pnl_pct > 0:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='target',
                pnl_pct=pnl_pct,
                metadata={
                    'exit_type': 'rsi2_profit_target',
                    'rsi2': rsi2,
                    'direction': 'long',
                }
            )

        # =========================================================
        # Exit Condition 2 & 5: Morning Exit (Next Day or Time Stop)
        # =========================================================
        if self.is_morning_exit_time():
            # Time stop: Position held 2+ days
            if days_held >= self.MAX_HOLDING_DAYS:
                return ExitSignal(
                    symbol=symbol,
                    price=current_price,
                    reason='time_stop',
                    pnl_pct=pnl_pct,
                    metadata={
                        'exit_type': 'time_stop_day3',
                        'days_held': days_held,
                        'direction': 'long',
                    }
                )

            # Next-day exit: Position entered yesterday
            if days_held >= 1:
                return ExitSignal(
                    symbol=symbol,
                    price=current_price,
                    reason='next_day_exit',
                    pnl_pct=pnl_pct,
                    metadata={
                        'exit_type': 'morning_exit',
                        'days_held': days_held,
                        'direction': 'long',
                    }
                )

        # =========================================================
        # Exit Condition 3: Stop Loss - Close < VWAP Lower Band
        # =========================================================
        vwap_data = self.indicators.get_vwap_with_bands(symbol)
        if vwap_data:
            vwap_lower = vwap_data['lower_band']

            # Use position's stop if available, otherwise use current VWAP lower
            stop_price = position.get('stop')
            if stop_price is None:
                stop_price = vwap_lower

            if stop_price is not None and current_price < stop_price:
                return ExitSignal(
                    symbol=symbol,
                    price=current_price,
                    reason='stop',
                    pnl_pct=pnl_pct,
                    metadata={
                        'exit_type': 'vwap_lower_stop',
                        'stop_price': stop_price,
                        'vwap_lower': vwap_lower,
                        'direction': 'long',
                    }
                )

        # =========================================================
        # Exit Condition 4: Trend Break - Close < SMA(200) at 3:55 PM
        # =========================================================
        if self.is_trend_check_time() and sma200 is not None:
            if current_price < sma200:
                return ExitSignal(
                    symbol=symbol,
                    price=current_price,
                    reason='trend_break',
                    pnl_pct=pnl_pct,
                    metadata={
                        'exit_type': 'sma200_trend_break',
                        'sma200': sma200,
                        'direction': 'long',
                    }
                )

        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen universe for entry candidates.

        Returns:
            List of EntrySignal objects sorted by RSI2 (most oversold first)
        """
        if not self.is_entry_window():
            now_et = self._get_current_et().time()
            logger.info(
                f"[VWAP_RSI2_SWING] Outside entry window "
                f"(10:00 AM - 3:30 PM), current time: {now_et}"
            )
            return []

        # Get universe of tradeable stocks
        universe = self._get_universe_filter()
        traded_today = self._get_traded_today()
        candidates = []

        logger.info(
            f"[VWAP_RSI2_SWING] Scanning {len(universe)} universe stocks "
            f"for entry candidates"
        )

        for stock in universe:
            symbol = stock.symbol

            # Skip if already traded today
            if symbol in traded_today:
                continue

            try:
                signal = self.check_entry(symbol)
                if signal:
                    candidates.append(signal)

                    # Stop early if we have enough candidates
                    if len(candidates) >= self.max_positions * 2:
                        break

            except Exception as e:
                logger.debug(f"Error checking {symbol} for entry: {e}")
                continue

        # Sort by RSI2 ascending (most oversold first)
        def sort_key(sig):
            rsi2 = sig.metadata.get('rsi2')
            crsi = sig.metadata.get('crsi')
            # Prefer RSI2, fall back to CRSI
            if rsi2 is not None:
                return rsi2
            elif crsi is not None:
                return crsi
            return 100  # High value pushes to end

        candidates.sort(key=sort_key)

        logger.info(f"[VWAP_RSI2_SWING] Found {len(candidates)} entry candidates")
        return candidates[:self.max_positions * 2]

    def record_entry(self, symbol: str) -> None:
        """Record that a position was entered for this symbol today."""
        self._mark_traded(symbol)
        logger.info(f"[VWAP_RSI2_SWING] Recorded entry for {symbol}")

    def should_force_eod_exit(self) -> bool:
        """
        Override base class - this strategy does NOT force EOD exits.

        The VWAP + RSI(2) strategy holds overnight by design.

        Returns:
            False always - no forced EOD exits
        """
        return False

    def __repr__(self) -> str:
        return (
            f"VwapRsi2SwingStrategy(max_rsi2={self.MAX_RSI2_ENTRY}, "
            f"max_crsi={self.MAX_CRSI_ENTRY}, "
            f"max_pos={self.max_positions}, "
            f"holds_overnight=True)"
        )
