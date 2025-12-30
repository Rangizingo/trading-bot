"""
Intraday Indicators Module

Calculates technical indicators from 1-minute bar data for intraday trading strategies:
- VWAP (Volume Weighted Average Price)
- EMA (Exponential Moving Average)
- WMA (Weighted Moving Average)
- HMA (Hull Moving Average)
- Heikin Ashi candles
- Opening Range (60-minute)
- Relative Volume

Data source: bars_1min table in VV7SimpleBridge intraday.db
"""

import sqlite3
import os
from datetime import datetime, timedelta, time as dt_time, timezone
from typing import Dict, List, Optional, Tuple
from math import sqrt
from contextlib import contextmanager
import logging

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET = ZoneInfo('America/New_York')


class IntradayIndicators:
    """
    Calculates intraday technical indicators from 1-minute bar data.

    Uses the bars_1min table which contains OHLCV data for ~9,800 symbols
    with 3 trading days of history.
    """

    # Market hours (Eastern Time)
    MARKET_OPEN = dt_time(9, 30)
    MARKET_CLOSE = dt_time(16, 0)
    OPENING_RANGE_END = dt_time(10, 30)  # 60-minute opening range

    def _et_to_timestamp(self, date_obj, time_obj) -> int:
        """
        Convert a date and time in Eastern Time to a Unix timestamp.

        NOTE: VV7SimpleBridge stores VectorVest's Eastern Time values as UTC
        (marks ET as DateTimeKind.Utc without conversion). So a 9:30 AM ET bar
        is stored with timestamp for 9:30 AM UTC. When querying, we must treat
        the target ET time as if it were UTC to match what's in the database.

        Args:
            date_obj: date object (or datetime.date())
            time_obj: time object (e.g., dt_time(9, 30))

        Returns:
            Unix timestamp (seconds since epoch) - using UTC interpretation
        """
        naive_dt = datetime.combine(date_obj, time_obj)
        # Treat as UTC because VV7 stores ET times marked as UTC
        utc_aware = naive_dt.replace(tzinfo=timezone.utc)
        return int(utc_aware.timestamp())

    def _get_current_et(self) -> datetime:
        """Get current time in Eastern Time as aware datetime."""
        return datetime.now(ET)

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize with path to intraday.db

        Args:
            db_path: Path to SQLite database. Defaults to VV7SimpleBridge location.
        """
        if db_path is None:
            local_app_data = os.environ.get('LOCALAPPDATA', '')
            db_path = os.path.join(local_app_data, 'VV7SimpleBridge', 'intraday.db')

        self.db_path = db_path
        self._validate_database()

    def _validate_database(self):
        """Verify database exists and has bars_1min table"""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bars_1min'")
            if not cursor.fetchone():
                raise ValueError("bars_1min table not found in database")

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # =========================================================================
    # 1.1 Basic Data Access
    # =========================================================================

    def get_bars(self, symbol: str, start_ts: int, end_ts: int) -> List[Dict]:
        """
        Fetch 1-minute bars for a symbol within timestamp range.

        Args:
            symbol: Stock symbol
            start_ts: Start Unix timestamp
            end_ts: End Unix timestamp

        Returns:
            List of bar dicts with keys: timestamp, open, high, low, close, volume
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, open, high, low, close, volume
                FROM bars_1min
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            """, (symbol, start_ts, end_ts))

            return [dict(row) for row in cursor.fetchall()]

    def get_latest_bars(self, symbol: str, count: int = 100) -> List[Dict]:
        """
        Fetch the most recent N bars for a symbol.

        Args:
            symbol: Stock symbol
            count: Number of bars to fetch

        Returns:
            List of bar dicts, oldest first
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, open, high, low, close, volume
                FROM bars_1min
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol, count))

            bars = [dict(row) for row in cursor.fetchall()]
            return list(reversed(bars))  # Return oldest first

    def get_all_symbols(self) -> List[str]:
        """Get list of all unique symbols in bars_1min"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT symbol FROM bars_1min ORDER BY symbol")
            return [row[0] for row in cursor.fetchall()]

    def get_latest_timestamp(self) -> int:
        """Get the most recent bar timestamp in the database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(timestamp) FROM bars_1min")
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_todays_bars(self, symbol: str) -> List[Dict]:
        """
        Get all bars for a symbol from today's trading session.

        Returns:
            List of bar dicts from market open to current time
        """
        # Get today's market open timestamp in ET
        now_et = self._get_current_et()
        start_ts = self._et_to_timestamp(now_et.date(), self.MARKET_OPEN)
        end_ts = int(now_et.timestamp())

        return self.get_bars(symbol, start_ts, end_ts)

    # =========================================================================
    # 1.2 VWAP Calculation
    # =========================================================================

    def calculate_vwap(self, bars: List[Dict]) -> List[float]:
        """
        Calculate VWAP (Volume Weighted Average Price) for a series of bars.

        VWAP = Cumulative(Typical_Price * Volume) / Cumulative(Volume)
        Typical_Price = (High + Low + Close) / 3

        Args:
            bars: List of bar dicts with high, low, close, volume

        Returns:
            List of VWAP values, one per bar
        """
        if not bars:
            return []

        vwap_values = []
        cumulative_tp_volume = 0.0
        cumulative_volume = 0

        for bar in bars:
            typical_price = (bar['high'] + bar['low'] + bar['close']) / 3
            cumulative_tp_volume += typical_price * bar['volume']
            cumulative_volume += bar['volume']

            if cumulative_volume > 0:
                vwap = cumulative_tp_volume / cumulative_volume
            else:
                vwap = bar['close']

            vwap_values.append(vwap)

        return vwap_values

    def get_current_vwap(self, symbol: str) -> Optional[float]:
        """
        Get the current VWAP for a symbol (calculated from today's bars).

        Returns:
            Current VWAP value or None if no data
        """
        bars = self.get_todays_bars(symbol)
        if not bars:
            return None

        vwap_values = self.calculate_vwap(bars)
        return vwap_values[-1] if vwap_values else None

    # =========================================================================
    # 1.3 Moving Averages
    # =========================================================================

    def calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """
        Calculate Exponential Moving Average.

        EMA = Price * alpha + Previous_EMA * (1 - alpha)
        alpha = 2 / (period + 1)

        Args:
            prices: List of prices (typically close prices)
            period: EMA period (e.g., 20)

        Returns:
            List of EMA values (first period-1 values are SMA-based warmup)
        """
        if not prices or len(prices) < period:
            return []

        alpha = 2 / (period + 1)
        ema_values = []

        # First value is SMA of first 'period' prices
        first_sma = sum(prices[:period]) / period
        ema_values.extend([None] * (period - 1))  # Warmup period
        ema_values.append(first_sma)

        # Calculate EMA for remaining prices
        for i in range(period, len(prices)):
            ema = prices[i] * alpha + ema_values[-1] * (1 - alpha)
            ema_values.append(ema)

        return ema_values

    def calculate_wma(self, prices: List[float], period: int) -> List[float]:
        """
        Calculate Weighted Moving Average.

        WMA = Sum(Price_i * Weight_i) / Sum(Weights)
        Weights = [1, 2, 3, ..., period]

        Args:
            prices: List of prices
            period: WMA period (e.g., 20)

        Returns:
            List of WMA values
        """
        if not prices or len(prices) < period:
            return []

        weights = list(range(1, period + 1))
        weight_sum = sum(weights)
        wma_values = [None] * (period - 1)  # Warmup period

        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1:i + 1]
            weighted_sum = sum(p * w for p, w in zip(window, weights))
            wma = weighted_sum / weight_sum
            wma_values.append(wma)

        return wma_values

    def calculate_hma(self, prices: List[float], period: int = 9) -> List[float]:
        """
        Calculate Hull Moving Average.

        HMA = WMA(2 * WMA(n/2) - WMA(n), sqrt(n))

        Args:
            prices: List of prices
            period: HMA period (default 9)

        Returns:
            List of HMA values
        """
        if not prices or len(prices) < period:
            return []

        half_period = period // 2
        sqrt_period = int(sqrt(period))

        # Calculate WMA(n/2) and WMA(n)
        wma_half = self.calculate_wma(prices, half_period)
        wma_full = self.calculate_wma(prices, period)

        # Find where both WMAs have valid values
        start_idx = period - 1  # WMA(n) starts here

        # Calculate 2 * WMA(n/2) - WMA(n)
        raw_hma = []
        for i in range(len(prices)):
            if i < start_idx or wma_half[i] is None or wma_full[i] is None:
                raw_hma.append(None)
            else:
                raw_hma.append(2 * wma_half[i] - wma_full[i])

        # Filter out None values for final WMA calculation
        valid_raw = [v for v in raw_hma if v is not None]
        if len(valid_raw) < sqrt_period:
            return [None] * len(prices)

        # Calculate final WMA on raw values
        hma_final = self.calculate_wma(valid_raw, sqrt_period)

        # Rebuild full-length result with None padding
        result = [None] * (len(prices) - len(hma_final))
        result.extend(hma_final)

        return result

    def get_ema20(self, symbol: str, bars: Optional[List[Dict]] = None) -> Optional[float]:
        """Get current EMA(20) for a symbol"""
        if bars is None:
            bars = self.get_latest_bars(symbol, 100)
        if not bars:
            return None

        prices = [b['close'] for b in bars]
        ema_values = self.calculate_ema(prices, 20)

        # Return last valid EMA
        for v in reversed(ema_values):
            if v is not None:
                return v
        return None

    def get_wma20(self, symbol: str, bars: Optional[List[Dict]] = None) -> Optional[float]:
        """Get current WMA(20) for a symbol"""
        if bars is None:
            bars = self.get_latest_bars(symbol, 100)
        if not bars:
            return None

        prices = [b['close'] for b in bars]
        wma_values = self.calculate_wma(prices, 20)

        for v in reversed(wma_values):
            if v is not None:
                return v
        return None

    def get_hma(self, symbol: str, period: int = 9, bars: Optional[List[Dict]] = None) -> Optional[float]:
        """Get current HMA for a symbol"""
        if bars is None:
            bars = self.get_latest_bars(symbol, 100)
        if not bars:
            return None

        prices = [b['close'] for b in bars]
        hma_values = self.calculate_hma(prices, period)

        for v in reversed(hma_values):
            if v is not None:
                return v
        return None

    def get_ema_slope(self, symbol: str, period: int = 20, bars: Optional[List[Dict]] = None) -> Optional[float]:
        """
        Get the slope of EMA (current - previous).
        Positive = uptrend, Negative = downtrend
        """
        if bars is None:
            bars = self.get_latest_bars(symbol, 100)
        if not bars:
            return None

        prices = [b['close'] for b in bars]
        ema_values = self.calculate_ema(prices, period)

        # Get last two valid EMA values
        valid_emas = [v for v in ema_values if v is not None]
        if len(valid_emas) < 2:
            return None

        return valid_emas[-1] - valid_emas[-2]

    # =========================================================================
    # 1.4 Heikin Ashi Candles
    # =========================================================================

    def calculate_heikin_ashi(self, bars: List[Dict]) -> List[Dict]:
        """
        Convert OHLC bars to Heikin Ashi candles.

        HA_Close = (Open + High + Low + Close) / 4
        HA_Open = (Previous_HA_Open + Previous_HA_Close) / 2
        HA_High = max(High, HA_Open, HA_Close)
        HA_Low = min(Low, HA_Open, HA_Close)

        Args:
            bars: List of OHLC bar dicts

        Returns:
            List of Heikin Ashi candle dicts
        """
        if not bars:
            return []

        ha_candles = []

        for i, bar in enumerate(bars):
            ha_close = (bar['open'] + bar['high'] + bar['low'] + bar['close']) / 4

            if i == 0:
                # First candle: HA_Open = (Open + Close) / 2
                ha_open = (bar['open'] + bar['close']) / 2
            else:
                # Subsequent candles: HA_Open = (prev_HA_Open + prev_HA_Close) / 2
                prev_ha = ha_candles[-1]
                ha_open = (prev_ha['ha_open'] + prev_ha['ha_close']) / 2

            ha_high = max(bar['high'], ha_open, ha_close)
            ha_low = min(bar['low'], ha_open, ha_close)

            ha_candles.append({
                'timestamp': bar['timestamp'],
                'ha_open': ha_open,
                'ha_high': ha_high,
                'ha_low': ha_low,
                'ha_close': ha_close,
                'volume': bar['volume'],
                # Original OHLC for reference
                'open': bar['open'],
                'high': bar['high'],
                'low': bar['low'],
                'close': bar['close'],
            })

        return ha_candles

    def is_green_ha(self, ha_candle: Dict) -> bool:
        """Check if Heikin Ashi candle is green (bullish)"""
        return ha_candle['ha_close'] > ha_candle['ha_open']

    def is_red_ha(self, ha_candle: Dict) -> bool:
        """Check if Heikin Ashi candle is red (bearish)"""
        return ha_candle['ha_close'] < ha_candle['ha_open']

    def is_flat_bottom_ha(self, ha_candle: Dict) -> bool:
        """
        Check if Heikin Ashi candle has no lower wick (flat bottom).
        Flat bottom = HA_Low equals the lower of HA_Open or HA_Close
        """
        body_low = min(ha_candle['ha_open'], ha_candle['ha_close'])
        return abs(ha_candle['ha_low'] - body_low) < 0.0001

    def is_flat_top_ha(self, ha_candle: Dict) -> bool:
        """
        Check if Heikin Ashi candle has no upper wick (flat top).
        Flat top = HA_High equals the higher of HA_Open or HA_Close
        """
        body_high = max(ha_candle['ha_open'], ha_candle['ha_close'])
        return abs(ha_candle['ha_high'] - body_high) < 0.0001

    def get_ha_candles(self, symbol: str, count: int = 50) -> List[Dict]:
        """Get last N Heikin Ashi candles for a symbol"""
        bars = self.get_latest_bars(symbol, count + 10)  # Extra for warmup
        if not bars:
            return []

        ha_candles = self.calculate_heikin_ashi(bars)
        return ha_candles[-count:] if len(ha_candles) >= count else ha_candles

    # =========================================================================
    # 1.5 Opening Range Calculation
    # =========================================================================

    def get_opening_range(self, symbol: str, date: Optional[datetime] = None) -> Optional[Dict]:
        """
        Calculate the 60-minute opening range for a symbol.

        Args:
            symbol: Stock symbol
            date: Date to calculate for (defaults to today)

        Returns:
            Dict with keys: high, low, range_size, or None if insufficient data
        """
        if date is None:
            date = self._get_current_et()

        # Calculate timestamps for opening range window (9:30 - 10:30 ET)
        start_ts = self._et_to_timestamp(date.date(), self.MARKET_OPEN)
        end_ts = self._et_to_timestamp(date.date(), self.OPENING_RANGE_END)

        bars = self.get_bars(symbol, start_ts, end_ts)

        if not bars:
            return None

        or_high = max(bar['high'] for bar in bars)
        or_low = min(bar['low'] for bar in bars)
        or_size = or_high - or_low

        return {
            'high': or_high,
            'low': or_low,
            'range_size': or_size,
            'bar_count': len(bars),
            'start_ts': start_ts,
            'end_ts': end_ts,
        }

    def is_breakout_above(self, symbol: str, current_price: float,
                          opening_range: Optional[Dict] = None) -> bool:
        """Check if current price is above the opening range high"""
        if opening_range is None:
            opening_range = self.get_opening_range(symbol)

        if opening_range is None:
            return False

        return current_price > opening_range['high']

    def is_breakout_below(self, symbol: str, current_price: float,
                          opening_range: Optional[Dict] = None) -> bool:
        """Check if current price is below the opening range low"""
        if opening_range is None:
            opening_range = self.get_opening_range(symbol)

        if opening_range is None:
            return False

        return current_price < opening_range['low']

    def get_breakout_target(self, entry_price: float, opening_range: Dict,
                            direction: str = 'long') -> float:
        """
        Calculate the breakout target price.
        Target = Entry +/- Range Size (measured move)
        """
        if direction == 'long':
            return entry_price + opening_range['range_size']
        else:
            return entry_price - opening_range['range_size']

    def get_breakout_stop(self, opening_range: Dict, direction: str = 'long',
                          buffer_pct: float = 0.001) -> float:
        """
        Calculate the breakout stop price.
        Stop is just inside the range (few ticks inside range high/low)
        """
        if direction == 'long':
            # Stop below range high for longs
            return opening_range['high'] * (1 - buffer_pct)
        else:
            # Stop above range low for shorts
            return opening_range['low'] * (1 + buffer_pct)

    # =========================================================================
    # 1.6 Relative Volume
    # =========================================================================

    def calculate_relative_volume(self, symbol: str, lookback_days: int = 20) -> Optional[float]:
        """
        Calculate relative volume (current vs historical average at same time).

        Args:
            symbol: Stock symbol
            lookback_days: Days to average for comparison

        Returns:
            Relative volume ratio (1.5 = 150% of average)
        """
        now_et = self._get_current_et()
        current_time = now_et.time()

        # Get today's cumulative volume from open to now
        todays_bars = self.get_todays_bars(symbol)
        if not todays_bars:
            return None

        current_volume = sum(bar['volume'] for bar in todays_bars)

        # Get historical volume at same time of day
        historical_volumes = []

        for days_ago in range(1, lookback_days + 1):
            past_date = now_et - timedelta(days=days_ago)

            # Skip weekends
            if past_date.weekday() >= 5:
                continue

            # Get bars from market open to same time as current (in ET)
            start_ts = self._et_to_timestamp(past_date.date(), self.MARKET_OPEN)
            end_ts = self._et_to_timestamp(past_date.date(), current_time)

            bars = self.get_bars(symbol, start_ts, end_ts)
            if bars:
                day_volume = sum(bar['volume'] for bar in bars)
                historical_volumes.append(day_volume)

        if not historical_volumes:
            return None

        avg_historical_volume = sum(historical_volumes) / len(historical_volumes)

        if avg_historical_volume == 0:
            return None

        return current_volume / avg_historical_volume

    def get_relative_volume(self, symbol: str) -> Optional[float]:
        """Convenience method for relative volume with default lookback"""
        return self.calculate_relative_volume(symbol, lookback_days=20)

    # =========================================================================
    # 1.7 Bulk Screening Queries
    # =========================================================================

    def get_orb_candidates(self, min_relative_volume: float = 1.5,
                           min_price: float = 5.0,
                           max_candidates: int = 50) -> List[Dict]:
        """
        Screen for ORB (Opening Range Breakout) entry candidates.

        Criteria:
        - Price > Opening Range High (breakout)
        - Relative Volume > 1.5x
        - Price > VWAP
        - EMA(20) slope > 0 (uptrend)
        - Time > 10:30 AM (range established)

        Returns:
            List of candidate dicts with symbol and indicator data
        """
        now_et = self._get_current_et()

        # Must be after 10:30 AM ET for ORB
        if now_et.time() < self.OPENING_RANGE_END:
            logger.info("ORB screening: Too early, opening range not established")
            return []

        candidates = []
        symbols = self.get_all_symbols()

        for symbol in symbols:
            try:
                # Get bars for calculations
                bars = self.get_latest_bars(symbol, 100)
                if not bars:
                    continue

                current_price = bars[-1]['close']

                # Price filter
                if current_price < min_price:
                    continue

                # Opening range check
                opening_range = self.get_opening_range(symbol)
                if not opening_range:
                    continue

                # Breakout above range high
                if current_price <= opening_range['high']:
                    continue

                # VWAP check
                vwap = self.get_current_vwap(symbol)
                if vwap is None or current_price <= vwap:
                    continue

                # EMA slope check
                ema_slope = self.get_ema_slope(symbol, 20, bars)
                if ema_slope is None or ema_slope <= 0:
                    continue

                # Relative volume check (expensive, do last)
                rel_vol = self.get_relative_volume(symbol)
                if rel_vol is None or rel_vol < min_relative_volume:
                    continue

                candidates.append({
                    'symbol': symbol,
                    'price': current_price,
                    'vwap': vwap,
                    'ema_slope': ema_slope,
                    'relative_volume': rel_vol,
                    'opening_range': opening_range,
                    'target': self.get_breakout_target(current_price, opening_range, 'long'),
                    'stop': self.get_breakout_stop(opening_range, 'long'),
                })

                if len(candidates) >= max_candidates:
                    break

            except Exception as e:
                logger.debug(f"Error screening {symbol} for ORB: {e}")
                continue

        # Sort by relative volume (highest first)
        candidates.sort(key=lambda x: x['relative_volume'], reverse=True)

        return candidates

    def get_wma_ha_candidates(self, min_price: float = 5.0,
                               max_candidates: int = 50) -> List[Dict]:
        """
        Screen for WMA(20) + Heikin Ashi entry candidates.

        Criteria:
        - HA close crossed above WMA(20)
        - Last 2 HA candles are green
        - Last 2 HA candles are flat-bottomed (no lower wick)

        Returns:
            List of candidate dicts
        """
        candidates = []
        symbols = self.get_all_symbols()

        for symbol in symbols:
            try:
                bars = self.get_latest_bars(symbol, 50)
                if len(bars) < 25:
                    continue

                current_price = bars[-1]['close']
                if current_price < min_price:
                    continue

                # Calculate WMA(20)
                prices = [b['close'] for b in bars]
                wma_values = self.calculate_wma(prices, 20)

                if len(wma_values) < 3:
                    continue

                current_wma = wma_values[-1]
                prev_wma = wma_values[-2]

                if current_wma is None or prev_wma is None:
                    continue

                # Calculate Heikin Ashi
                ha_candles = self.calculate_heikin_ashi(bars)
                if len(ha_candles) < 3:
                    continue

                # Check last 2 HA candles
                ha_current = ha_candles[-1]
                ha_prev = ha_candles[-2]
                ha_prev2 = ha_candles[-3]

                # Must be green
                if not (self.is_green_ha(ha_current) and self.is_green_ha(ha_prev)):
                    continue

                # Must be flat-bottomed
                if not (self.is_flat_bottom_ha(ha_current) and self.is_flat_bottom_ha(ha_prev)):
                    continue

                # Check for crossover (HA close crossed above WMA)
                # Current: HA close > WMA, Previous: HA close was <= WMA
                if not (ha_current['ha_close'] > current_wma):
                    continue

                # Crossover check: previous HA close was at or below previous WMA
                if ha_prev2['ha_close'] > prev_wma:
                    continue  # Already above, not a fresh crossover

                candidates.append({
                    'symbol': symbol,
                    'price': current_price,
                    'ha_close': ha_current['ha_close'],
                    'wma20': current_wma,
                    'consecutive_green': 2,
                    'flat_bottom': True,
                })

                if len(candidates) >= max_candidates:
                    break

            except Exception as e:
                logger.debug(f"Error screening {symbol} for WMA+HA: {e}")
                continue

        return candidates

    def get_hma_ha_candidates(self, min_price: float = 5.0,
                               hma_period: int = 9,
                               max_candidates: int = 50) -> List[Dict]:
        """
        Screen for HMA + Heikin Ashi entry candidates.

        Criteria:
        - HA close crossed above HMA
        - Current HA candle is green

        Returns:
            List of candidate dicts
        """
        candidates = []
        symbols = self.get_all_symbols()

        for symbol in symbols:
            try:
                bars = self.get_latest_bars(symbol, 50)
                if len(bars) < 20:
                    continue

                current_price = bars[-1]['close']
                if current_price < min_price:
                    continue

                # Calculate HMA
                prices = [b['close'] for b in bars]
                hma_values = self.calculate_hma(prices, hma_period)

                if len(hma_values) < 3:
                    continue

                current_hma = hma_values[-1]
                prev_hma = hma_values[-2]

                if current_hma is None or prev_hma is None:
                    continue

                # Calculate Heikin Ashi
                ha_candles = self.calculate_heikin_ashi(bars)
                if len(ha_candles) < 3:
                    continue

                ha_current = ha_candles[-1]
                ha_prev = ha_candles[-2]

                # Current HA must be green
                if not self.is_green_ha(ha_current):
                    continue

                # Check for crossover (HA close crossed above HMA)
                if not (ha_current['ha_close'] > current_hma):
                    continue

                # Previous HA close was at or below HMA (crossover)
                if ha_prev['ha_close'] > prev_hma:
                    continue

                candidates.append({
                    'symbol': symbol,
                    'price': current_price,
                    'ha_close': ha_current['ha_close'],
                    'hma': current_hma,
                    'is_green': True,
                })

                if len(candidates) >= max_candidates:
                    break

            except Exception as e:
                logger.debug(f"Error screening {symbol} for HMA+HA: {e}")
                continue

        return candidates

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get the most recent close price for a symbol"""
        bars = self.get_latest_bars(symbol, 1)
        return bars[0]['close'] if bars else None

    def get_stats(self) -> Dict:
        """Get database statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM bars_1min")
            total_bars = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT symbol) FROM bars_1min")
            symbol_count = cursor.fetchone()[0]

            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM bars_1min")
            min_ts, max_ts = cursor.fetchone()

            return {
                'total_bars': total_bars,
                'symbol_count': symbol_count,
                'min_timestamp': min_ts,
                'max_timestamp': max_ts,
                'min_date': datetime.fromtimestamp(min_ts) if min_ts else None,
                'max_date': datetime.fromtimestamp(max_ts) if max_ts else None,
            }

    # =========================================================================
    # 2.0 Overnight-Intraday Reversal Data Methods
    # =========================================================================

    def get_prior_close(self, symbol: str, for_date: Optional[datetime] = None) -> Optional[float]:
        """
        Get the prior day's closing price for a symbol.

        Args:
            symbol: Stock symbol
            for_date: Date to get prior close for (defaults to today)

        Returns:
            Prior day's close price or None if not found
        """
        if for_date is None:
            for_date = self._get_current_et()

        # Get today's market open timestamp in ET
        today_open_ts = self._et_to_timestamp(for_date.date(), self.MARKET_OPEN)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Get the last bar before today's market open
            cursor.execute("""
                SELECT close
                FROM bars_1min
                WHERE symbol = ? AND timestamp < ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (symbol, today_open_ts))

            result = cursor.fetchone()
            return result[0] if result else None

    def calculate_overnight_return(self, symbol: str, for_date: Optional[datetime] = None) -> Optional[float]:
        """
        Calculate overnight return for a symbol.

        Overnight return = (Today's Open - Prior Close) / Prior Close

        Args:
            symbol: Stock symbol
            for_date: Date to calculate for (defaults to today)

        Returns:
            Overnight return as decimal (e.g., -0.02 for -2%) or None if data missing
        """
        if for_date is None:
            for_date = self._get_current_et()

        # Get prior close
        prior_close = self.get_prior_close(symbol, for_date)
        if prior_close is None or prior_close <= 0:
            return None

        # Get today's open price (first bar of the day) in ET
        start_ts = self._et_to_timestamp(for_date.date(), self.MARKET_OPEN)
        end_ts = start_ts + 60  # First minute

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT open
                FROM bars_1min
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                LIMIT 1
            """, (symbol, start_ts, end_ts))

            result = cursor.fetchone()
            if not result:
                return None

            today_open = result[0]

        if today_open is None or today_open <= 0:
            return None

        return (today_open - prior_close) / prior_close

    def get_overnight_return_deciles(
        self,
        min_price: float = 5.0,
        for_date: Optional[datetime] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Calculate overnight returns for all symbols and return deciles.

        Args:
            min_price: Minimum stock price filter
            for_date: Date to calculate for (defaults to today)

        Returns:
            Tuple of (bottom_decile, top_decile) where each is a list of dicts
            with symbol, overnight_return, prior_close, today_open
        """
        if for_date is None:
            for_date = self._get_current_et()

        # Get all symbols
        symbols = self.get_all_symbols()
        returns_data = []

        for symbol in symbols:
            try:
                # Get prior close
                prior_close = self.get_prior_close(symbol, for_date)
                if prior_close is None or prior_close < min_price:
                    continue

                # Get today's open in ET
                start_ts = self._et_to_timestamp(for_date.date(), self.MARKET_OPEN)
                end_ts = start_ts + 60

                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT open
                        FROM bars_1min
                        WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp ASC
                        LIMIT 1
                    """, (symbol, start_ts, end_ts))
                    result = cursor.fetchone()

                if not result:
                    continue

                today_open = result[0]
                if today_open is None or today_open <= 0:
                    continue

                overnight_return = (today_open - prior_close) / prior_close

                returns_data.append({
                    'symbol': symbol,
                    'overnight_return': overnight_return,
                    'prior_close': prior_close,
                    'today_open': today_open,
                })

            except Exception as e:
                logger.debug(f"Error calculating overnight return for {symbol}: {e}")
                continue

        if not returns_data:
            return [], []

        # Sort by overnight return (ascending: biggest losers first)
        returns_data.sort(key=lambda x: x['overnight_return'])

        # Calculate decile boundaries
        n = len(returns_data)
        decile_size = max(1, n // 10)

        bottom_decile = returns_data[:decile_size]  # Biggest losers
        top_decile = returns_data[-decile_size:]    # Biggest winners

        logger.info(f"Overnight returns calculated for {n} symbols. "
                   f"Bottom decile: {len(bottom_decile)}, Top decile: {len(top_decile)}")

        return bottom_decile, top_decile

    # =========================================================================
    # 2.1 Stocks in Play Screening Methods
    # =========================================================================

    def get_first_5min_candle(self, symbol: str, for_date: Optional[datetime] = None) -> Optional[Dict]:
        """
        Get the first 5-minute candle of the trading day (9:30-9:35 AM).

        Args:
            symbol: Stock symbol
            for_date: Date to get candle for (defaults to today)

        Returns:
            Dict with open, high, low, close, volume, is_bullish, is_bearish, is_doji
            or None if insufficient data
        """
        if for_date is None:
            for_date = self._get_current_et()

        # Get bars from 9:30-9:35 AM ET
        start_ts = self._et_to_timestamp(for_date.date(), self.MARKET_OPEN)
        end_ts = start_ts + (5 * 60)  # 5 minutes

        bars = self.get_bars(symbol, start_ts, end_ts)

        if not bars:
            return None

        # Aggregate 1-min bars into 5-min candle
        candle_open = bars[0]['open']
        candle_high = max(b['high'] for b in bars)
        candle_low = min(b['low'] for b in bars)
        candle_close = bars[-1]['close']
        candle_volume = sum(b['volume'] for b in bars)

        # Determine candle type
        price_range = candle_high - candle_low
        body_size = abs(candle_close - candle_open)

        # Doji: body is less than 10% of range (or very small absolute)
        is_doji = body_size < (price_range * 0.1) if price_range > 0 else True
        is_bullish = candle_close > candle_open and not is_doji
        is_bearish = candle_close < candle_open and not is_doji

        return {
            'symbol': symbol,
            'open': candle_open,
            'high': candle_high,
            'low': candle_low,
            'close': candle_close,
            'volume': candle_volume,
            'is_bullish': is_bullish,
            'is_bearish': is_bearish,
            'is_doji': is_doji,
            'body_size': body_size,
            'range_size': price_range,
        }

    def get_stocks_in_play(
        self,
        top_n: int = 20,
        min_price: float = 5.0,
        min_avg_volume: int = 1_000_000,
        min_atr: float = 0.50,
        for_date: Optional[datetime] = None,
        historical_data: Optional['HistoricalData'] = None
    ) -> List[Dict]:
        """
        Screen for "Stocks in Play" - high relative volume stocks with momentum.

        Criteria:
        - Price > min_price
        - 20-day average volume > min_avg_volume
        - 14-day ATR > min_atr
        - Sorted by relative volume (highest first)

        Args:
            top_n: Number of stocks to return
            min_price: Minimum stock price
            min_avg_volume: Minimum 20-day average volume
            min_atr: Minimum 14-day ATR
            for_date: Date to screen for (defaults to today)
            historical_data: HistoricalData instance for ATR/volume (optional)

        Returns:
            List of dicts with symbol and screening data, sorted by relative volume
        """
        if for_date is None:
            for_date = self._get_current_et()

        symbols = self.get_all_symbols()
        candidates = []

        for symbol in symbols:
            try:
                # Get current price
                bars = self.get_latest_bars(symbol, 10)
                if not bars:
                    continue

                current_price = bars[-1]['close']
                if current_price < min_price:
                    continue

                # Calculate relative volume from local data
                rel_vol = self.calculate_relative_volume(symbol, lookback_days=5)
                if rel_vol is None:
                    continue

                # If historical_data provided, use it for ATR and avg volume
                avg_volume = None
                atr = None

                if historical_data:
                    try:
                        avg_volume = historical_data.get_average_volume(symbol, period=20)
                        atr = historical_data.get_atr(symbol, period=14)
                    except Exception:
                        pass

                # For now, if no historical_data, use simplified screening
                # based just on relative volume and price
                if avg_volume is not None and avg_volume < min_avg_volume:
                    continue
                if atr is not None and atr < min_atr:
                    continue

                candidates.append({
                    'symbol': symbol,
                    'price': current_price,
                    'relative_volume': rel_vol,
                    'avg_volume': avg_volume,
                    'atr': atr,
                })

            except Exception as e:
                logger.debug(f"Error screening {symbol} for stocks in play: {e}")
                continue

        # Sort by relative volume (highest first)
        candidates.sort(key=lambda x: x['relative_volume'], reverse=True)

        return candidates[:top_n]

    def get_stocks_in_play_with_candles(
        self,
        top_n: int = 20,
        min_price: float = 5.0,
        for_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get Stocks in Play with their first 5-minute candle analysis.

        Returns candidates with bullish/bearish first candle signals.

        Returns:
            List of dicts with symbol, screening data, and first candle analysis
        """
        stocks_in_play = self.get_stocks_in_play(
            top_n=top_n * 2,  # Get more to filter
            min_price=min_price,
            for_date=for_date
        )

        candidates = []

        for stock in stocks_in_play:
            first_candle = self.get_first_5min_candle(stock['symbol'], for_date)
            if first_candle is None:
                continue

            # Skip doji candles (no clear direction)
            if first_candle['is_doji']:
                continue

            stock['first_candle'] = first_candle
            stock['direction'] = 'long' if first_candle['is_bullish'] else 'short'
            candidates.append(stock)

            if len(candidates) >= top_n:
                break

        return candidates
