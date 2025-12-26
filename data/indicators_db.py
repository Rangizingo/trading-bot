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


def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol for database lookup (PBR.A -> PBRA).

    VV7 database uses symbols without separators (e.g., PBRA),
    while Alpaca returns symbols with dots (e.g., PBR.A).
    This function removes all common separators for database lookups.

    Args:
        symbol: Stock symbol potentially containing separators

    Returns:
        Normalized symbol with separators removed

    Example:
        >>> normalize_symbol('PBR.A')
        'PBRA'
        >>> normalize_symbol('BRK-B')
        'BRKB'
        >>> normalize_symbol('AAPL')
        'AAPL'
    """
    return symbol.replace('.', '').replace('-', '').replace('/', '')


def calculate_heikin_ashi(
    open_price: float,
    high: float,
    low: float,
    close: float,
    prev_ha_open: Optional[float] = None,
    prev_ha_close: Optional[float] = None
) -> Dict[str, float]:
    """
    Calculate Heikin Ashi bar from OHLC data.

    Heikin Ashi candles smooth price action by averaging values,
    making trends easier to identify. Each candle uses previous
    HA values for continuity.

    Args:
        open_price: Current bar open price
        high: Current bar high price
        low: Current bar low price
        close: Current bar close price
        prev_ha_open: Previous Heikin Ashi open (None for first bar)
        prev_ha_close: Previous Heikin Ashi close (None for first bar)

    Returns:
        Dict containing ha_open, ha_high, ha_low, ha_close

    Example:
        >>> ha = calculate_heikin_ashi(100.0, 105.0, 99.0, 103.0)
        >>> print(f"HA Close: {ha['ha_close']:.2f}")
        HA Close: 101.75
        >>> ha2 = calculate_heikin_ashi(103.0, 108.0, 102.0, 107.0,
        ...                             ha['ha_open'], ha['ha_close'])
    """
    ha_close = (open_price + high + low + close) / 4

    if prev_ha_open is not None and prev_ha_close is not None:
        ha_open = (prev_ha_open + prev_ha_close) / 2
    else:
        ha_open = (open_price + close) / 2

    ha_high = max(high, ha_open, ha_close)
    ha_low = min(low, ha_open, ha_close)

    return {
        'ha_open': ha_open,
        'ha_high': ha_high,
        'ha_low': ha_low,
        'ha_close': ha_close
    }


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


    def get_rsi2_entry_candidates(
        self,
        max_rsi2: float = 15,
        min_volume: int = 100000,
        min_price: float = 5.0,
        limit: int = 20
    ) -> List[Dict]:
        """
        Find stocks matching entry criteria for RSI(2) strategy.

        Entry conditions (all must be true):
        - RSI(2) <= max_rsi2 (oversold on 2-period RSI)
        - Close > SMA200 (in long-term uptrend)
        - No close < sma5 requirement (removed from original CRSI strategy)

        Screens with sufficient liquidity, ordered by most oversold first.

        Args:
            max_rsi2: Maximum RSI(2) value (default 15 for oversold)
            min_volume: Minimum daily volume (default 100,000)
            min_price: Minimum stock price (default $5.00)
            limit: Maximum number of results to return (default 20)

        Returns:
            List of dicts containing: symbol, close, rsi2, sma5, sma200, atr, volume.
            Sorted by RSI(2) ascending (most oversold first).

        Example:
            >>> db = IndicatorsDB()
            >>> candidates = db.get_rsi2_entry_candidates(max_rsi2=15, limit=10)
            >>> for stock in candidates:
            ...     print(f"{stock['symbol']}: ${stock['close']:.2f}, RSI2={stock['rsi2']:.2f}")
        """
        query = """
            SELECT
                symbol,
                close,
                rsi2,
                sma5,
                sma200,
                atr,
                volume
            FROM indicators
            WHERE
                rsi2 IS NOT NULL
                AND sma200 IS NOT NULL
                AND sma5 IS NOT NULL
                AND close IS NOT NULL
                AND volume IS NOT NULL
                AND atr IS NOT NULL
                AND rsi2 > 0
                AND rsi2 <= ?
                AND close > sma200
                AND volume >= ?
                AND close >= ?
            ORDER BY rsi2 ASC
            LIMIT ?
        """

        try:
            with self._get_conn() as conn:
                cursor = conn.execute(query, (max_rsi2, min_volume, min_price, limit))
                rows = cursor.fetchall()

                results = [dict(row) for row in rows]
                logger.info(
                    f"Found {len(results)} RSI(2) entry candidates "
                    f"(max_rsi2={max_rsi2}, min_volume={min_volume:,}, "
                    f"min_price=${min_price:.2f})"
                )
                return results

        except sqlite3.Error as e:
            logger.error(f"Failed to query RSI(2) entry candidates: {e}")
            return []

    def get_position_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Batch lookup of indicator data for multiple symbols.

        Efficiently retrieves current indicator values for a list of symbols,
        typically used for monitoring existing positions.

        Args:
            symbols: List of stock symbols to lookup (e.g., ['PBR.A', 'AAPL'])

        Returns:
            Dict mapping ORIGINAL symbol -> indicator data dict containing:
            close, rsi, rsi2, sma5, sma200, atr. Symbols not found are omitted.
            Keys use original symbols (e.g., 'PBR.A') for Alpaca API compatibility.

        Example:
            >>> db = IndicatorsDB()
            >>> positions = db.get_position_data(['PBR.A', 'MSFT', 'GOOGL'])
            >>> for symbol, data in positions.items():
            ...     print(f"{symbol}: RSI={data['rsi']:.2f}, Price=${data['close']:.2f}")
        """
        if not symbols:
            return {}

        # Create mapping of normalized -> original symbols for result mapping
        symbol_map = {normalize_symbol(s): s for s in symbols}
        normalized_symbols = list(symbol_map.keys())

        # Create parameterized query with placeholders
        placeholders = ','.join('?' * len(normalized_symbols))
        query = f"""
            SELECT
                symbol,
                close,
                rsi,
                rsi2,
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
                cursor = conn.execute(query, normalized_symbols)
                rows = cursor.fetchall()

                # Build dict mapping ORIGINAL symbol -> data
                # DB returns normalized symbols, we map back to original
                results = {}
                for row in rows:
                    db_symbol = row['symbol']  # Normalized symbol from DB (PBRA)
                    original_symbol = symbol_map.get(db_symbol)  # Original symbol (PBR.A)
                    if original_symbol:
                        results[original_symbol] = dict(row)

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
            symbol: Stock symbol to lookup (e.g., 'PBR.A' or 'AAPL')

        Returns:
            Dict containing all indicator columns, or None if symbol not found.
            Symbol is normalized for database lookup (PBR.A -> PBRA).

        Example:
            >>> db = IndicatorsDB()
            >>> data = db.get_indicator('PBR.A')  # Queries DB for 'PBRA'
            >>> if data:
            ...     print(f"PBR.A: RSI={data['rsi']:.2f}, Price=${data['close']:.2f}")
            ... else:
            ...     print("Symbol not found")
        """
        # Normalize symbol for database lookup
        normalized_symbol = normalize_symbol(symbol)
        query = "SELECT * FROM indicators WHERE symbol = ?"

        try:
            with self._get_conn() as conn:
                cursor = conn.execute(query, (normalized_symbol,))
                row = cursor.fetchone()

                if row:
                    result = dict(row)
                    logger.debug(f"Found indicator data for {symbol} (normalized: {normalized_symbol})")
                    return result
                else:
                    logger.debug(f"No indicator data found for {symbol} (normalized: {normalized_symbol})")
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

    def get_all_roc_values(self) -> Dict[str, float]:
        """
        Get ROC (Rate of Change) values for all symbols in the database.

        ROC measures momentum by comparing current price to price N periods ago.
        Useful for screening stocks by momentum across the entire universe.

        Returns:
            Dict mapping symbol -> ROC value. Symbols with NULL ROC are excluded.

        Example:
            >>> db = IndicatorsDB()
            >>> roc_values = db.get_all_roc_values()
            >>> top_momentum = sorted(roc_values.items(), key=lambda x: x[1], reverse=True)[:10]
            >>> for symbol, roc in top_momentum:
            ...     print(f"{symbol}: ROC={roc:.2f}%")
        """
        query = "SELECT symbol, roc FROM indicators WHERE roc IS NOT NULL"

        try:
            with self._get_conn() as conn:
                cursor = conn.execute(query)
                rows = cursor.fetchall()

                results = {row['symbol']: row['roc'] for row in rows}
                logger.info(f"Retrieved ROC values for {len(results):,} symbols")
                return results

        except sqlite3.Error as e:
            logger.error(f"Failed to query ROC values: {e}")
            return {}

    def get_roc_for_symbols(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get ROC (Rate of Change) values for specific symbols.

        Args:
            symbols: List of stock symbols to lookup (e.g., ['PBR.A', 'AAPL'])

        Returns:
            Dict mapping ORIGINAL symbol -> ROC value. Symbols not found
            or with NULL ROC are excluded. Keys use original symbols
            (e.g., 'PBR.A') for Alpaca API compatibility.

        Example:
            >>> db = IndicatorsDB()
            >>> roc = db.get_roc_for_symbols(['AAPL', 'MSFT', 'GOOGL'])
            >>> for symbol, value in roc.items():
            ...     print(f"{symbol}: ROC={value:.2f}%")
        """
        if not symbols:
            return {}

        # Create mapping of normalized -> original symbols for result mapping
        symbol_map = {normalize_symbol(s): s for s in symbols}
        normalized_symbols = list(symbol_map.keys())

        # Create parameterized query with placeholders
        placeholders = ','.join('?' * len(normalized_symbols))
        query = f"""
            SELECT symbol, roc
            FROM indicators
            WHERE symbol IN ({placeholders})
                AND roc IS NOT NULL
        """

        try:
            with self._get_conn() as conn:
                cursor = conn.execute(query, normalized_symbols)
                rows = cursor.fetchall()

                # Build dict mapping ORIGINAL symbol -> ROC value
                results = {}
                for row in rows:
                    db_symbol = row['symbol']
                    original_symbol = symbol_map.get(db_symbol)
                    if original_symbol:
                        results[original_symbol] = row['roc']

                logger.info(
                    f"ROC lookup: {len(results)}/{len(symbols)} symbols found"
                )
                return results

        except sqlite3.Error as e:
            logger.error(f"Failed to query ROC for symbols: {e}")
            return {}

    def get_ohlc_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get OHLC (Open, High, Low, Close) data for Heikin Ashi calculation.

        Retrieves price data needed to compute Heikin Ashi candles using
        the calculate_heikin_ashi() function.

        Args:
            symbols: List of stock symbols to lookup (e.g., ['PBR.A', 'AAPL'])

        Returns:
            Dict mapping ORIGINAL symbol -> dict containing:
            - open: Opening price
            - high: High price
            - low: Low price
            - close: Closing price
            Symbols not found or with incomplete OHLC data are excluded.

        Example:
            >>> db = IndicatorsDB()
            >>> ohlc = db.get_ohlc_data(['AAPL', 'MSFT'])
            >>> for symbol, data in ohlc.items():
            ...     ha = calculate_heikin_ashi(
            ...         data['open'], data['high'], data['low'], data['close']
            ...     )
            ...     print(f"{symbol}: HA Close={ha['ha_close']:.2f}")
        """
        if not symbols:
            return {}

        # Create mapping of normalized -> original symbols for result mapping
        symbol_map = {normalize_symbol(s): s for s in symbols}
        normalized_symbols = list(symbol_map.keys())

        # Create parameterized query with placeholders
        placeholders = ','.join('?' * len(normalized_symbols))
        query = f"""
            SELECT symbol, open, high, low, close
            FROM indicators
            WHERE symbol IN ({placeholders})
                AND open IS NOT NULL
                AND high IS NOT NULL
                AND low IS NOT NULL
                AND close IS NOT NULL
        """

        try:
            with self._get_conn() as conn:
                cursor = conn.execute(query, normalized_symbols)
                rows = cursor.fetchall()

                # Build dict mapping ORIGINAL symbol -> OHLC data
                results = {}
                for row in rows:
                    db_symbol = row['symbol']
                    original_symbol = symbol_map.get(db_symbol)
                    if original_symbol:
                        results[original_symbol] = {
                            'open': row['open'],
                            'high': row['high'],
                            'low': row['low'],
                            'close': row['close']
                        }

                logger.info(
                    f"OHLC data lookup: {len(results)}/{len(symbols)} symbols found"
                )
                return results

        except sqlite3.Error as e:
            logger.error(f"Failed to query OHLC data: {e}")
            return {}
