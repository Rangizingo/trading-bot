"""SQLite cache for VV7 bulk data."""
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Stock, Technicals


class BulkCache:
    """SQLite cache for VV7 bulk data."""

    def __init__(self, db_path: str = "bulk_cache.db"):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """Create tables if not exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS ratings_cache (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT,
                industry TEXT,
                vst REAL,
                rs REAL,
                rv REAL,
                rt REAL,
                price REAL,
                volume INTEGER,
                avg_volume INTEGER,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS technicals_cache (
                symbol TEXT PRIMARY KEY,
                rsi REAL,
                macd REAL,
                macd_signal REAL,
                macd_histogram REAL,
                bb_upper REAL,
                bb_middle REAL,
                bb_lower REAL,
                atr REAL,
                adx REAL,
                vwap REAL,
                raw_json TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_metadata (
                data_type TEXT PRIMARY KEY,
                last_sync TEXT,
                record_count INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_ratings_vst ON ratings_cache(vst);
            CREATE INDEX IF NOT EXISTS idx_ratings_rs ON ratings_cache(rs);
            CREATE INDEX IF NOT EXISTS idx_technicals_rsi ON technicals_cache(rsi);
        """)
        self.conn.commit()

    def close(self) -> None:
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def sync_ratings(self, stocks: Dict[str, Stock]) -> int:
        """Bulk insert/update ratings.

        Returns number of records synced.
        """
        now = datetime.now().isoformat()

        data = [
            (s.symbol, s.name, s.sector, "", s.vst, s.rs, s.rv, s.rt,
             s.price, s.volume, s.avg_volume, now)
            for s in stocks.values()
        ]

        self.conn.executemany("""
            INSERT OR REPLACE INTO ratings_cache
            (symbol, name, sector, industry, vst, rs, rv, rt, price, volume, avg_volume, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)

        self.conn.execute("""
            INSERT OR REPLACE INTO sync_metadata (data_type, last_sync, record_count)
            VALUES ('ratings', ?, ?)
        """, (now, len(data)))

        self.conn.commit()
        return len(data)

    def sync_technicals(self, technicals: Dict[str, Technicals]) -> int:
        """Bulk insert/update technicals.

        Returns number of records synced.
        """
        now = datetime.now().isoformat()

        data = [
            (t.symbol, t.rsi, t.macd, t.macd_signal, t.macd_histogram,
             t.bb_upper, t.bb_middle, t.bb_lower, t.atr, t.adx, t.vwap,
             None, now)
            for t in technicals.values()
        ]

        self.conn.executemany("""
            INSERT OR REPLACE INTO technicals_cache
            (symbol, rsi, macd, macd_signal, macd_histogram, bb_upper, bb_middle,
             bb_lower, atr, adx, vwap, raw_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)

        self.conn.execute("""
            INSERT OR REPLACE INTO sync_metadata (data_type, last_sync, record_count)
            VALUES ('technicals', ?, ?)
        """, (now, len(data)))

        self.conn.commit()
        return len(data)

    def get_stock(self, symbol: str) -> Optional[Stock]:
        """Get cached stock data."""
        row = self.conn.execute(
            "SELECT * FROM ratings_cache WHERE symbol = ?", (symbol,)
        ).fetchone()

        if not row:
            return None

        return Stock(
            symbol=row["symbol"],
            name=row["name"],
            sector=row["sector"],
            vst=row["vst"],
            rs=row["rs"],
            rv=row["rv"],
            rt=row["rt"],
            price=row["price"],
            volume=row["volume"],
            avg_volume=row["avg_volume"]
        )

    def get_technicals(self, symbol: str) -> Optional[Technicals]:
        """Get cached technicals."""
        row = self.conn.execute(
            "SELECT * FROM technicals_cache WHERE symbol = ?", (symbol,)
        ).fetchone()

        if not row:
            return None

        return Technicals(
            symbol=row["symbol"],
            rsi=row["rsi"],
            macd=row["macd"],
            macd_signal=row["macd_signal"],
            macd_histogram=row["macd_histogram"],
            bb_upper=row["bb_upper"],
            bb_middle=row["bb_middle"],
            bb_lower=row["bb_lower"],
            atr=row["atr"],
            adx=row["adx"],
            vwap=row["vwap"]
        )

    def get_all_stocks(self) -> Dict[str, Stock]:
        """Get all cached stocks."""
        rows = self.conn.execute("SELECT * FROM ratings_cache").fetchall()
        return {
            row["symbol"]: Stock(
                symbol=row["symbol"],
                name=row["name"],
                sector=row["sector"],
                vst=row["vst"],
                rs=row["rs"],
                rv=row["rv"],
                rt=row["rt"],
                price=row["price"],
                volume=row["volume"],
                avg_volume=row["avg_volume"]
            )
            for row in rows
        }

    def get_all_technicals(self) -> Dict[str, Technicals]:
        """Get all cached technicals."""
        rows = self.conn.execute("SELECT * FROM technicals_cache").fetchall()
        return {
            row["symbol"]: Technicals(
                symbol=row["symbol"],
                rsi=row["rsi"],
                macd=row["macd"],
                macd_signal=row["macd_signal"],
                macd_histogram=row["macd_histogram"],
                bb_upper=row["bb_upper"],
                bb_middle=row["bb_middle"],
                bb_lower=row["bb_lower"],
                atr=row["atr"],
                adx=row["adx"],
                vwap=row["vwap"]
            )
            for row in rows
        }

    def is_stale(self, data_type: str, max_age_seconds: int = 300) -> bool:
        """Check if cached data is stale."""
        row = self.conn.execute(
            "SELECT last_sync FROM sync_metadata WHERE data_type = ?",
            (data_type,)
        ).fetchone()

        if not row:
            return True

        last_sync = datetime.fromisoformat(row["last_sync"])
        age = (datetime.now() - last_sync).total_seconds()
        return age > max_age_seconds

    def get_symbols_by_criteria(
        self,
        min_vst: Optional[float] = None,
        min_rs: Optional[float] = None,
        min_volume: Optional[int] = None,
        max_rsi: Optional[float] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> List[str]:
        """Get symbols matching criteria."""
        conditions = []
        params = []

        if min_vst is not None:
            conditions.append("r.vst >= ?")
            params.append(min_vst)
        if min_rs is not None:
            conditions.append("r.rs >= ?")
            params.append(min_rs)
        if min_volume is not None:
            conditions.append("r.avg_volume >= ?")
            params.append(min_volume)
        if max_rsi is not None:
            conditions.append("t.rsi <= ?")
            params.append(max_rsi)
        if min_price is not None:
            conditions.append("r.price >= ?")
            params.append(min_price)
        if max_price is not None:
            conditions.append("r.price <= ?")
            params.append(max_price)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT r.symbol FROM ratings_cache r
            LEFT JOIN technicals_cache t ON r.symbol = t.symbol
            WHERE {where_clause}
        """

        rows = self.conn.execute(query, params).fetchall()
        return [row["symbol"] for row in rows]
