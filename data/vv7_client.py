"""VV7 API client for fetching market data."""
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar, Stock, Technicals
from config import TRADING


class VV7Client:
    """HTTP client for VV7 API."""

    def __init__(
        self,
        base_url: str = TRADING.vv7_api_url,
        timeout: float = 60.0,
        retries: int = 3
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retries = retries
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-init HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client

    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make HTTP request with retries."""
        last_error = None
        for attempt in range(self.retries):
            try:
                response = self.client.request(method, endpoint, **kwargs)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < self.retries - 1:
                    continue
        raise last_error

    def health_check(self) -> bool:
        """Check if API is responsive."""
        try:
            self._request("GET", "/api/health")
            return True
        except Exception:
            return False

    def get_bulk_ratings(self) -> Dict[str, Stock]:
        """Fetch ratings for all ~9,850 stocks.

        Returns dict mapping symbol to Stock object.
        """
        data = self._request("POST", "/api/stocks/bulk/ratings")

        stocks = {}
        for symbol, info in data.items():
            stocks[symbol] = Stock(
                symbol=symbol,
                name=info.get("name", ""),
                sector=info.get("sector", ""),
                vst=info.get("vst", 0.0),
                rs=info.get("rs", 0.0),
                rv=info.get("rv", 0.0),
                rt=info.get("rt", 0.0),
                price=info.get("price", 0.0),
                volume=info.get("volume", 0),
                avg_volume=info.get("avg_vol", 0)
            )
        return stocks

    def get_bulk_technicals(self) -> Dict[str, Technicals]:
        """Fetch technical indicators for all stocks.

        Returns dict mapping symbol to Technicals object.
        """
        data = self._request("POST", "/api/stocks/bulk/technicals")

        technicals = {}
        for symbol, info in data.items():
            technicals[symbol] = Technicals(
                symbol=symbol,
                rsi=info.get("rsi", {}).get("value"),
                macd=info.get("macd", {}).get("macd"),
                macd_signal=info.get("macd", {}).get("signal"),
                macd_histogram=info.get("macd", {}).get("histogram"),
                bb_upper=info.get("bollinger", {}).get("upper"),
                bb_middle=info.get("bollinger", {}).get("middle"),
                bb_lower=info.get("bollinger", {}).get("lower"),
                atr=info.get("atr", {}).get("value"),
                adx=info.get("adx", {}).get("adx"),
                vwap=info.get("vwap")
            )
        return technicals

    def get_stock(self, symbol: str) -> Optional[Stock]:
        """Fetch data for a single stock."""
        try:
            data = self._request("GET", f"/api/stocks/{symbol}")
            return Stock(
                symbol=symbol,
                name=data.get("name", ""),
                sector=data.get("sector", ""),
                vst=data.get("vst", 0.0),
                rs=data.get("rs", 0.0),
                rv=data.get("rv", 0.0),
                rt=data.get("rt", 0.0),
                price=data.get("price", 0.0),
                volume=data.get("volume", 0),
                avg_volume=data.get("avg_vol", 0)
            )
        except Exception:
            return None

    def get_stock_history(
        self,
        symbol: str,
        days: int = 200
    ) -> List[Bar]:
        """Fetch historical bars for a symbol."""
        try:
            data = self._request(
                "GET",
                f"/api/stocks/{symbol}/history",
                params={"days": days}
            )

            bars = []
            for bar_data in data.get("bars", []):
                bars.append(Bar(
                    timestamp=datetime.fromisoformat(bar_data["timestamp"]),
                    open=bar_data["open"],
                    high=bar_data["high"],
                    low=bar_data["low"],
                    close=bar_data["close"],
                    volume=bar_data.get("volume", 0)
                ))
            return bars
        except Exception:
            return []

    def get_market_timing(self) -> Dict[str, Any]:
        """Get market timing indicators (SPY > 200 MA, etc.)."""
        try:
            data = self._request("GET", "/api/market/timing")
            return {
                "bullish": data.get("bullish", False),
                "spy_above_200ma": data.get("spy_above_200ma", False),
                "mti": data.get("mti"),
                "vvc": data.get("vvc")
            }
        except Exception:
            return {"bullish": True, "spy_above_200ma": True}  # Default bullish

    def get_spy_price(self) -> Optional[float]:
        """Get current SPY price."""
        stock = self.get_stock("SPY")
        return stock.price if stock else None
