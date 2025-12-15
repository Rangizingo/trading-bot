"""Trading bot configuration."""
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

# Time zone
ET = ZoneInfo("America/New_York")

@dataclass
class TradingConfig:
    """Core trading parameters."""
    # Capital
    capital: float = 100_000
    position_size_pct: float = 10.0  # % of capital per trade
    max_positions: int = 5

    # Risk management
    risk_per_trade_pct: float = 2.0  # Max loss per trade
    daily_drawdown_limit_pct: float = 5.0  # Pause trading
    total_drawdown_limit_pct: float = 15.0  # Full stop
    kelly_fraction: float = 0.5  # Half-Kelly sizing

    # Market hours (Eastern Time)
    market_open: time = time(9, 30)
    market_close: time = time(16, 0)
    pre_market_buffer_minutes: int = 15

    # API endpoints
    vv7_api_url: str = "http://localhost:5000"

    # Trading cycle
    cycle_interval_minutes: int = 5

    # Caching
    cache_stale_seconds: int = 300  # 5 minutes


@dataclass
class AlpacaConfig:
    """Alpaca API configuration."""
    api_key: str = ""
    secret_key: str = ""
    paper: bool = True
    base_url: str = "https://paper-api.alpaca.markets"


# Default instances
TRADING = TradingConfig()
ALPACA = AlpacaConfig()
