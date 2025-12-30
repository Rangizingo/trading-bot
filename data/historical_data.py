"""
Historical Data Module

Fetches historical daily data from Alpaca API for:
- 14-day ATR (Average True Range)
- 20-day average volume

Used by strategies that require historical data not available in the local intraday.db
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

logger = logging.getLogger(__name__)


class HistoricalData:
    """
    Fetches and caches historical daily data from Alpaca API.

    Provides ATR and average volume calculations that require
    more history than the local intraday database contains.
    """

    def __init__(self, api_key: str, secret_key: str, cache_ttl_seconds: int = 3600):
        """
        Initialize with Alpaca API credentials.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            cache_ttl_seconds: How long to cache results (default 1 hour)
        """
        self.client = StockHistoricalDataClient(api_key, secret_key)
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Dict] = {}
        self._cache_time: Dict[str, datetime] = {}

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time[cache_key]).total_seconds()
        return elapsed < self.cache_ttl

    def _get_daily_bars(self, symbol: str, days: int = 30) -> List[Dict]:
        """
        Fetch daily bars from Alpaca.

        Args:
            symbol: Stock symbol
            days: Number of days of history to fetch

        Returns:
            List of daily bar dicts with keys: timestamp, open, high, low, close, volume
        """
        cache_key = f"bars_{symbol}_{days}"

        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        try:
            end = datetime.now()
            start = end - timedelta(days=days + 10)  # Extra buffer for weekends/holidays

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                start=start,
                end=end
            )

            bars_data = self.client.get_stock_bars(request)

            if symbol not in bars_data.data:
                return []

            bars = []
            for bar in bars_data.data[symbol]:
                bars.append({
                    'timestamp': bar.timestamp,
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close),
                    'volume': int(bar.volume),
                })

            # Cache the result
            self._cache[cache_key] = bars
            self._cache_time[cache_key] = datetime.now()

            return bars

        except Exception as e:
            logger.warning(f"Error fetching daily bars for {symbol}: {e}")
            return []

    def get_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """
        Calculate Average True Range (ATR) for a symbol.

        ATR = Average of True Range over period
        True Range = max(High - Low, abs(High - Prev Close), abs(Low - Prev Close))

        Args:
            symbol: Stock symbol
            period: ATR period (default 14)

        Returns:
            ATR value or None if insufficient data
        """
        cache_key = f"atr_{symbol}_{period}"

        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        bars = self._get_daily_bars(symbol, days=period + 10)

        if len(bars) < period + 1:
            return None

        # Calculate True Range for each bar
        true_ranges = []
        for i in range(1, len(bars)):
            high = bars[i]['high']
            low = bars[i]['low']
            prev_close = bars[i - 1]['close']

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        if len(true_ranges) < period:
            return None

        # ATR is simple moving average of True Range
        atr = sum(true_ranges[-period:]) / period

        # Cache the result
        self._cache[cache_key] = atr
        self._cache_time[cache_key] = datetime.now()

        return atr

    def get_average_volume(self, symbol: str, period: int = 20) -> Optional[int]:
        """
        Calculate average daily volume for a symbol.

        Args:
            symbol: Stock symbol
            period: Number of days to average (default 20)

        Returns:
            Average volume or None if insufficient data
        """
        cache_key = f"avg_vol_{symbol}_{period}"

        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        bars = self._get_daily_bars(symbol, days=period + 5)

        if len(bars) < period:
            return None

        # Calculate average volume over period
        volumes = [bar['volume'] for bar in bars[-period:]]
        avg_volume = int(sum(volumes) / len(volumes))

        # Cache the result
        self._cache[cache_key] = avg_volume
        self._cache_time[cache_key] = datetime.now()

        return avg_volume

    def get_daily_stats(self, symbol: str) -> Optional[Dict]:
        """
        Get comprehensive daily statistics for a symbol.

        Returns:
            Dict with atr_14, avg_volume_20, last_close, or None if error
        """
        try:
            atr = self.get_atr(symbol, period=14)
            avg_volume = self.get_average_volume(symbol, period=20)

            bars = self._get_daily_bars(symbol, days=5)
            last_close = bars[-1]['close'] if bars else None

            return {
                'symbol': symbol,
                'atr_14': atr,
                'avg_volume_20': avg_volume,
                'last_close': last_close,
            }

        except Exception as e:
            logger.warning(f"Error getting daily stats for {symbol}: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear all cached data"""
        self._cache.clear()
        self._cache_time.clear()
        logger.info("Historical data cache cleared")

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            'entries': len(self._cache),
            'cache_ttl_seconds': self.cache_ttl,
        }
