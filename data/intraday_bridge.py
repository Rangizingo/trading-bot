"""Bridge to VV7 intraday cache for trading bot."""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar

# VV7 intraday cache location
VV7_INTRADAY_CACHE = Path("C:/Users/User/Documents/AI/VV7/vv7_data_cache/intraday_cache.db")

# VV7 project path for imports
VV7_PROJECT = Path("C:/Users/User/Documents/AI/VV7")


class IntradayBridge:
    """Bridge to read from VV7 intraday cache and trigger delta syncs."""

    def __init__(self, cache_path: Path = None):
        self.cache_path = cache_path or VV7_INTRADAY_CACHE
        self._vv7_client = None
        self._vv7_cache = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection with busy timeout for concurrent access."""
        if not self.cache_path.exists():
            raise FileNotFoundError(f"Intraday cache not found: {self.cache_path}")
        conn = sqlite3.connect(self.cache_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")  # Wait up to 30s for locks
        return conn

    def _get_vv7_client(self):
        """Lazy load VV7 client."""
        if self._vv7_client is None:
            sys.path.insert(0, str(VV7_PROJECT))
            sys.path.insert(0, str(VV7_PROJECT / "vv7_api"))
            from vv7_client.client import VV7Client
            self._vv7_client = VV7Client()
        return self._vv7_client

    def _get_vv7_cache(self):
        """Lazy load VV7 intraday cache manager."""
        if self._vv7_cache is None:
            sys.path.insert(0, str(VV7_PROJECT))
            from vv7_data_cache.intraday_cache import IntradayCache
            self._vv7_cache = IntradayCache()
        return self._vv7_cache

    def is_cache_available(self) -> bool:
        """Check if cache exists and has data."""
        if not self.cache_path.exists():
            return False
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM stock_data")
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except Exception:
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM stock_data")
        total_records = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM stock_data")
        symbol_count = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(timestamp) FROM stock_data")
        latest = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(timestamp) FROM stock_data")
        earliest = cursor.fetchone()[0]

        conn.close()

        return {
            "total_records": total_records,
            "symbol_count": symbol_count,
            "latest_timestamp": latest,
            "earliest_timestamp": earliest,
            "cache_path": str(self.cache_path)
        }

    def delta_sync(self) -> Dict[str, Any]:
        """Run delta sync to get latest data from VV7.

        Returns:
            Sync result dict
        """
        cache = self._get_vv7_cache()
        client = self._get_vv7_client()
        return cache.smart_sync(client, backfill_days=1)

    def get_sync_status(self) -> Dict[str, Any]:
        """Get cache sync status and freshness info.

        Returns:
            Dict with: has_data, has_timestamp, minutes_behind, latest_timestamp, needs_repair
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            # Check if has data
            cursor.execute("SELECT COUNT(*) FROM stock_data")
            has_data = cursor.fetchone()[0] > 0

            # Check if has sync timestamp
            cursor.execute("SELECT value FROM sync_metadata WHERE key = 'last_sync_timestamp'")
            row = cursor.fetchone()
            has_timestamp = row is not None

            # Get latest data timestamp
            cursor.execute("SELECT MAX(time_id) as tid, MAX(minute_id) as mid FROM stock_data WHERE time_id = (SELECT MAX(time_id) FROM stock_data)")
            data_row = cursor.fetchone()
            latest_time_id = data_row['tid'] if data_row else None
            latest_minute_id = data_row['mid'] if data_row else None

            conn.close()

            # Calculate minutes behind (estimate)
            minutes_behind = 0
            latest_timestamp = None
            if latest_time_id and latest_minute_id:
                # VV7 epoch is 2005-05-22
                from datetime import timedelta
                vv_epoch = datetime(2005, 5, 22)
                data_date = vv_epoch + timedelta(days=latest_time_id)
                hour = latest_minute_id // 60
                minute = latest_minute_id % 60
                latest_timestamp = f"{data_date.strftime('%Y-%m-%d')} {hour:02d}:{minute:02d}"

                # Rough minutes behind calculation
                now = datetime.now()
                current_minute_id = now.hour * 60 + now.minute
                current_time_id = (now.date() - vv_epoch.date()).days

                if current_time_id == latest_time_id:
                    minutes_behind = max(0, current_minute_id - latest_minute_id)
                else:
                    # Different days - rough estimate
                    days_behind = current_time_id - latest_time_id
                    minutes_behind = days_behind * 390 + (current_minute_id - latest_minute_id)

            return {
                "has_data": has_data,
                "has_timestamp": has_timestamp,
                "minutes_behind": minutes_behind,
                "latest_timestamp": latest_timestamp,
                "needs_repair": has_data and not has_timestamp
            }
        except Exception as e:
            return {
                "has_data": False,
                "has_timestamp": False,
                "minutes_behind": 0,
                "latest_timestamp": None,
                "needs_repair": False,
                "error": str(e)
            }

    def repair_sync_timestamp(self) -> bool:
        """Repair missing sync timestamp by setting it to latest data.

        Returns:
            True if repaired, False on error
        """
        try:
            import json
            conn = self._get_conn()
            cursor = conn.cursor()

            # Get latest data timestamp
            cursor.execute("""
                SELECT MAX(time_id) as tid, MAX(minute_id) as mid
                FROM stock_data
                WHERE time_id = (SELECT MAX(time_id) FROM stock_data)
            """)
            row = cursor.fetchone()

            if not row or not row['tid']:
                conn.close()
                return False

            time_id = row['tid']
            minute_id = row['mid']

            # Create sync metadata
            value = json.dumps({
                'time_id': time_id,
                'minute_id': minute_id,
                'updated': datetime.now().isoformat(),
                'repaired': True
            })

            cursor.execute(
                "INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (?, ?)",
                ('last_sync_timestamp', value)
            )
            conn.commit()
            conn.close()

            print(f"Repaired sync timestamp: time_id={time_id}, minute_id={minute_id}")
            return True

        except Exception as e:
            print(f"Failed to repair sync timestamp: {e}")
            return False

    def delta_sync_force(self) -> Dict[str, Any]:
        """Force delta sync regardless of market hours.

        Returns:
            Sync result dict
        """
        try:
            cache = self._get_vv7_cache()
            client = self._get_vv7_client()

            # Check and repair timestamp if needed
            status = self.get_sync_status()
            if status.get('needs_repair'):
                self.repair_sync_timestamp()

            # Use backfill_streaming with days=0 to fetch just today's data
            # This bypasses the market hours check in sync_streaming
            result = cache.backfill_streaming(client, days=0, show_progress=False)
            return result

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "stocks_stored": 0
            }

    def get_bar_history(self, symbol: str, limit: int = 200) -> List[Bar]:
        """Get bar history for a symbol from cache.

        Args:
            symbol: Stock symbol
            limit: Max bars to return (most recent)

        Returns:
            List of Bar objects, oldest first
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM stock_data
            WHERE symbol = ?
            ORDER BY time_id DESC, minute_id DESC
            LIMIT ?
        """, (symbol, limit))

        rows = cursor.fetchall()
        conn.close()

        # Convert to Bar objects, reverse to get oldest first
        bars = []
        for row in reversed(rows):
            try:
                ts = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            except (ValueError, TypeError):
                ts = datetime.now()

            bars.append(Bar(
                timestamp=ts,
                open=float(row['open'] or 0),
                high=float(row['high'] or 0),
                low=float(row['low'] or 0),
                close=float(row['close'] or 0),
                volume=int(row['volume'] or 0)
            ))

        return bars

    def get_symbols_with_data(self, min_bars: int = 50) -> List[str]:
        """Get symbols that have enough bar history.

        Args:
            min_bars: Minimum bars required

        Returns:
            List of symbols
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT symbol, COUNT(*) as bar_count
            FROM stock_data
            GROUP BY symbol
            HAVING bar_count >= ?
            ORDER BY bar_count DESC
        """, (min_bars,))

        symbols = [row['symbol'] for row in cursor.fetchall()]
        conn.close()

        return symbols

    def get_latest_data(self, symbols: List[str] = None) -> Dict[str, Dict]:
        """Get latest data point for each symbol.

        Args:
            symbols: Optional list of symbols to filter

        Returns:
            Dict mapping symbol to latest data
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        if symbols:
            placeholders = ','.join('?' * len(symbols))
            cursor.execute(f"""
                SELECT s.*
                FROM stock_data s
                INNER JOIN (
                    SELECT symbol, MAX(time_id * 10000 + minute_id) as max_time
                    FROM stock_data
                    WHERE symbol IN ({placeholders})
                    GROUP BY symbol
                ) latest ON s.symbol = latest.symbol
                    AND (s.time_id * 10000 + s.minute_id) = latest.max_time
            """, symbols)
        else:
            cursor.execute("""
                SELECT s.*
                FROM stock_data s
                INNER JOIN (
                    SELECT symbol, MAX(time_id * 10000 + minute_id) as max_time
                    FROM stock_data
                    GROUP BY symbol
                ) latest ON s.symbol = latest.symbol
                    AND (s.time_id * 10000 + s.minute_id) = latest.max_time
            """)

        result = {}
        for row in cursor.fetchall():
            result[row['symbol']] = dict(row)

        conn.close()
        return result

    def get_candidates_by_rsi(self, max_rsi: float = 35, min_volume: int = 100000) -> List[str]:
        """Get symbols with low RSI (oversold) from latest data.

        Args:
            max_rsi: Maximum RSI value
            min_volume: Minimum volume

        Returns:
            List of candidate symbols
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Get latest data for each symbol with RSI filter
        cursor.execute("""
            SELECT s.symbol, s.rsi, s.close, s.volume, s.sma200
            FROM stock_data s
            INNER JOIN (
                SELECT symbol, MAX(time_id * 10000 + minute_id) as max_time
                FROM stock_data
                GROUP BY symbol
            ) latest ON s.symbol = latest.symbol
                AND (s.time_id * 10000 + s.minute_id) = latest.max_time
            WHERE s.rsi IS NOT NULL
              AND s.rsi < ?
              AND s.volume >= ?
              AND s.sma200 IS NOT NULL
              AND s.close > s.sma200
            ORDER BY s.rsi ASC
            LIMIT 100
        """, (max_rsi, min_volume))

        symbols = [row['symbol'] for row in cursor.fetchall()]
        conn.close()

        return symbols

    def get_candidates_by_bb(self, min_volume: int = 100000) -> List[str]:
        """Get symbols below lower Bollinger Band.

        Args:
            min_volume: Minimum volume

        Returns:
            List of candidate symbols
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT s.symbol, s.close, s.bb_lower, s.rsi, s.volume
            FROM stock_data s
            INNER JOIN (
                SELECT symbol, MAX(time_id * 10000 + minute_id) as max_time
                FROM stock_data
                GROUP BY symbol
            ) latest ON s.symbol = latest.symbol
                AND (s.time_id * 10000 + s.minute_id) = latest.max_time
            WHERE s.bb_lower IS NOT NULL
              AND s.close < s.bb_lower
              AND s.volume >= ?
              AND s.rsi IS NOT NULL
              AND s.rsi < 30
            ORDER BY s.rsi ASC
            LIMIT 100
        """, (min_volume,))

        symbols = [row['symbol'] for row in cursor.fetchall()]
        conn.close()

        return symbols

    def close(self):
        """Close connections."""
        if self._vv7_client:
            self._vv7_client.close()
