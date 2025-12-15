"""Data loader for backtesting from Alpaca historical database."""
import sqlite3
from datetime import datetime, date
from typing import List, Optional, Dict
from pathlib import Path
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar


class DataLoader:
    """Load historical data from Alpaca database for backtesting."""

    def __init__(self, db_path: str = None):
        # Default to VV7 project's alpaca_historical.db
        if db_path is None:
            db_path = "C:/Users/User/Documents/AI/VV7/trading_bot/alpaca_historical.db"

        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_symbols(
        self,
        min_bars: int = 200,
        min_avg_volume: float = 100000,
        limit: Optional[int] = None
    ) -> List[str]:
        """Get symbols with sufficient data.

        Returns symbols sorted by bar count descending.
        """
        query = """
            SELECT symbol, COUNT(*) as bar_count, AVG(volume) as avg_vol
            FROM bars
            WHERE timeframe = '5Min'
            GROUP BY symbol
            HAVING bar_count >= ? AND avg_vol >= ?
            ORDER BY bar_count DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        rows = self.conn.execute(query, (min_bars, min_avg_volume)).fetchall()
        return [row["symbol"] for row in rows]

    def get_bars(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        timeframe: str = "5Min"
    ) -> List[Bar]:
        """Get historical bars for a symbol."""
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM bars
            WHERE symbol = ? AND timeframe = ?
        """
        params = [symbol, timeframe]

        if start_date:
            query += " AND date(timestamp) >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND date(timestamp) <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY timestamp ASC"

        rows = self.conn.execute(query, params).fetchall()

        bars = []
        for row in rows:
            try:
                ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            except:
                ts = datetime.strptime(row["timestamp"][:19], "%Y-%m-%d %H:%M:%S")

            bars.append(Bar(
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"])
            ))

        return bars

    def get_spy_bars(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Bar]:
        """Get SPY bars for market regime filter."""
        return self.get_bars("SPY", start_date, end_date)

    def get_bar_count(self, symbol: str) -> int:
        """Get number of bars for a symbol."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM bars WHERE symbol = ? AND timeframe = '5Min'",
            (symbol,)
        ).fetchone()
        return row["cnt"] if row else 0

    def get_date_range(self, symbol: str) -> Optional[tuple]:
        """Get date range for a symbol."""
        row = self.conn.execute("""
            SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
            FROM bars
            WHERE symbol = ? AND timeframe = '5Min'
        """, (symbol,)).fetchone()

        if not row or not row["min_ts"]:
            return None

        return (row["min_ts"], row["max_ts"])

    def get_stats(self) -> Dict:
        """Get database statistics."""
        rows = self.conn.execute("""
            SELECT
                COUNT(DISTINCT symbol) as symbol_count,
                COUNT(*) as total_bars,
                MIN(timestamp) as min_date,
                MAX(timestamp) as max_date
            FROM bars
            WHERE timeframe = '5Min'
        """).fetchone()

        return {
            "symbol_count": rows["symbol_count"],
            "total_bars": rows["total_bars"],
            "date_range": (rows["min_date"], rows["max_date"])
        }
