"""
IndicatorsDB - SQLite database interface for pre-computed technical indicators.

This module provides efficient access to a SQLite database containing technical
indicators for 9,847+ symbols with 47 columns including:
- Price data: open, high, low, close, volume
- Momentum: RSI (Relative Strength Index)
- Moving averages: SMA5, SMA200
- Volatility: ATR (Average True Range), Bollinger Bands

The database is populated externally and used for real-time trading decisions.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager
import logging

from config import INTRADAY_DB_PATH

logger = logging.getLogger(__name__)


class IndicatorsDB:
    """
    Interface to SQLite database containing pre-computed technical indicators.

    The database contains an 'indicators' table with technical indicators
    for thousands of symbols, enabling fast screening and position analysis.

    Attributes:
        db_path: Path to the SQLite database file

    Example:
        >>> db = IndicatorsDB()
        >>> if db.is_available():
        ...     candidates = db.get_entry_candidates(max_rsi=5, limit=10)
        ...     for stock in candidates:
        ...         print(f"{stock['symbol']}: RSI={stock['rsi']:.2f}")
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize IndicatorsDB with database path.

        Args:
            db_path: Optional path to SQLite database. If None, uses INTRADAY_DB_PATH
                    from config module.

        Note:
            Connection is not established until first query to minimize resource usage.
        """
        self.db_path = db_path or INTRADAY_DB_PATH
        self._connection: Optional[sqlite3.Connection] = None
        logger.info(f"IndicatorsDB initialized with path: {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """
        Create a new SQLite connection with optimized settings.

        Returns:
            SQLite connection configured with:
            - Row factory for dict-like access
            - 30-second timeout for concurrent access
            - 30000ms busy timeout pragma

        Raises:
            sqlite3.Error: If connection cannot be established
        """
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def connection(self):
        """
        Context manager for database connection reuse.

        Provides a reusable connection for multiple queries within a single
        context. The connection is automatically closed when exiting the context.

        Yields:
            sqlite3.Connection: Reusable database connection

        Example:
            >>> db = IndicatorsDB()
            >>> with db.connection() as conn:
            ...     # Multiple queries can reuse this connection
            ...     cursor = conn.execute("SELECT * FROM indicators WHERE symbol = ?", ("AAPL",))
            ...     result = cursor.fetchone()
        """
        conn = self._get_conn()
        try:
            yield conn
        finally:
            conn.close()

    def is_available(self) -> bool:
        """
        Check if database is available and contains data.

        Returns:
            True if database file exists and contains indicator records,
            False otherwise.

        Example:
            >>> db = IndicatorsDB()
            >>> if db.is_available():
            ...     print("Database ready for queries")
            ... else:
            ...     print("Database not available")
        """
        try:
            # Check file exists
            if not Path(self.db_path).exists():
                logger.warning(f"Database file does not exist: {self.db_path}")
                return False

            # Check if table has data
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM indicators")
                count = cursor.fetchone()[0]

                if count > 0:
                    logger.info(f"Database available with {count:,} indicator records")
                    return True
                else:
                    logger.warning("Database exists but contains no records")
                    return False

        except sqlite3.Error as e:
            logger.error(f"Database availability check failed: {e}")
            return False

    def get_last_updated(self) -> int:
        """
        Get the latest updated_at timestamp from the indicators table.

        Returns:
            Unix timestamp of last update, or 0 if unavailable.
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT MAX(updated_at) FROM indicators")
                result = cursor.fetchone()[0]
                return result if result else 0

        except sqlite3.Error as e:
            logger.error(f"Failed to get last updated timestamp: {e}")
            return 0

    def get_entry_candidates(
        self,
        max_rsi: float = 5,
        max_crsi: float = 5,
        min_volume: int = 100000,
        min_price: float = 5.0,
        limit: int = 20
    ) -> List[Dict]:
        """
        Find stocks matching entry criteria for true Connors RSI(2) strategy.

        Entry conditions (all must be true):
        - ConnorsRSI <= max_crsi (oversold on ConnorsRSI composite indicator)
        - Close > SMA200 (in long-term uptrend)
        - Close < SMA5 (pulled back below short-term average)

        Screens with sufficient liquidity, ordered by most oversold first.

        Args:
            max_rsi: Maximum RSI value (default 5, kept for backwards compatibility)
            max_crsi: Maximum ConnorsRSI value (default 5 for extreme oversold)
            min_volume: Minimum daily volume (default 100,000)
            min_price: Minimum stock price (default $5.00)
            limit: Maximum number of results to return (default 20)

        Returns:
            List of dicts containing: symbol, close, rsi, crsi, sma5, sma200, atr, volume.
            Sorted by ConnorsRSI ascending (most oversold first).

        Example:
            >>> db = IndicatorsDB()
            >>> candidates = db.get_entry_candidates(max_crsi=5, limit=10)
            >>> for stock in candidates:
            ...     print(f"{stock['symbol']}: ${stock['close']:.2f}, CRSI={stock['crsi']:.2f}")
        """
        query = """
            SELECT
                symbol,
                close,
                rsi,
                crsi,
                sma5,
                sma200,
                atr,
                volume
            FROM indicators
            WHERE
                rsi IS NOT NULL
                AND crsi IS NOT NULL
                AND sma200 IS NOT NULL
                AND sma5 IS NOT NULL
                AND close IS NOT NULL
                AND volume IS NOT NULL
                AND atr IS NOT NULL
                AND rsi > 0
                AND crsi > 0
                AND crsi <= ?
                AND close > sma200
                AND close < sma5
                AND volume >= ?
                AND close >= ?
            ORDER BY crsi ASC
            LIMIT ?
        """

        try:
            with self._get_conn() as conn:
                cursor = conn.execute(query, (max_crsi, min_volume, min_price, limit))
                rows = cursor.fetchall()

                results = [dict(row) for row in rows]
                logger.info(
                    f"Found {len(results)} entry candidates "
                    f"(max_crsi={max_crsi}, min_volume={min_volume:,}, "
                    f"min_price=${min_price:.2f})"
                )
                return results

        except sqlite3.Error as e:
            logger.error(f"Failed to query entry candidates: {e}")
            return []

    def get_position_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Batch lookup of indicator data for multiple symbols.

        Efficiently retrieves current indicator values for a list of symbols,
        typically used for monitoring existing positions.

        Args:
            symbols: List of stock symbols to lookup

        Returns:
            Dict mapping symbol -> indicator data dict containing:
            close, rsi, sma5, sma200, atr. Symbols not found are omitted.

        Example:
            >>> db = IndicatorsDB()
            >>> positions = db.get_position_data(['AAPL', 'MSFT', 'GOOGL'])
            >>> for symbol, data in positions.items():
            ...     print(f"{symbol}: RSI={data['rsi']:.2f}, Price=${data['close']:.2f}")
        """
        if not symbols:
            return {}

        # Create parameterized query with placeholders
        placeholders = ','.join('?' * len(symbols))
        query = f"""
            SELECT
                symbol,
                close,
                rsi,
                sma5,
                sma200,
                atr
            FROM indicators
            WHERE symbol IN ({placeholders})
                AND rsi IS NOT NULL
                AND sma200 IS NOT NULL
                AND sma5 IS NOT NULL
                AND close IS NOT NULL
                AND atr IS NOT NULL
        """

        try:
            with self._get_conn() as conn:
                cursor = conn.execute(query, symbols)
                rows = cursor.fetchall()

                # Build dict mapping symbol -> data
                results = {row['symbol']: dict(row) for row in rows}

                found_count = len(results)
                missing = set(symbols) - set(results.keys())

                logger.info(
                    f"Position data lookup: {found_count}/{len(symbols)} found"
                )
                if missing:
                    logger.warning(f"Symbols not found in database: {missing}")

                return results

        except sqlite3.Error as e:
            logger.error(f"Failed to query position data: {e}")
            return {}

    def get_indicator(self, symbol: str) -> Optional[Dict]:
        """
        Retrieve indicator data for a single symbol.

        Args:
            symbol: Stock symbol to lookup

        Returns:
            Dict containing all indicator columns, or None if symbol not found.

        Example:
            >>> db = IndicatorsDB()
            >>> data = db.get_indicator('AAPL')
            >>> if data:
            ...     print(f"AAPL: RSI={data['rsi']:.2f}, Price=${data['close']:.2f}")
            ... else:
            ...     print("Symbol not found")
        """
        query = "SELECT * FROM indicators WHERE symbol = ?"

        try:
            with self._get_conn() as conn:
                cursor = conn.execute(query, (symbol,))
                row = cursor.fetchone()

                if row:
                    result = dict(row)
                    logger.debug(f"Found indicator data for {symbol}")
                    return result
                else:
                    logger.debug(f"No indicator data found for {symbol}")
                    return None

        except sqlite3.Error as e:
            logger.error(f"Failed to query indicator for {symbol}: {e}")
            return None

    def get_stats(self) -> Dict:
        """
        Retrieve database statistics.

        Returns:
            Dict containing:
            - record_count: Total number of indicator records
            - latest_timestamp: Most recent timestamp in database (if available)
            - symbol_count: Number of unique symbols

        Example:
            >>> db = IndicatorsDB()
            >>> stats = db.get_stats()
            >>> print(f"Records: {stats['record_count']:,}")
            >>> print(f"Symbols: {stats['symbol_count']:,}")
        """
        try:
            with self._get_conn() as conn:
                # Get record count
                cursor = conn.execute("SELECT COUNT(*) FROM indicators")
                record_count = cursor.fetchone()[0]

                # Get unique symbol count
                cursor = conn.execute("SELECT COUNT(DISTINCT symbol) FROM indicators")
                symbol_count = cursor.fetchone()[0]

                # Get latest timestamp if column exists
                latest_timestamp = None
                try:
                    cursor = conn.execute("SELECT MAX(timestamp) FROM indicators")
                    latest_timestamp = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    # Timestamp column may not exist in all schemas
                    pass

                stats = {
                    'record_count': record_count,
                    'latest_timestamp': latest_timestamp,
                    'symbol_count': symbol_count
                }

                logger.info(
                    f"Database stats: {record_count:,} records, "
                    f"{symbol_count:,} symbols"
                )
                return stats

        except sqlite3.Error as e:
            logger.error(f"Failed to retrieve database stats: {e}")
            return {
                'record_count': 0,
                'latest_timestamp': None,
                'symbol_count': 0
            }
