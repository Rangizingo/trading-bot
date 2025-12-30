"""
Configuration module for Intraday Trading Bot.

Centralizes all configuration parameters including:
- Database paths
- Alpaca API credentials (3 accounts for 3 strategies)
- Trading parameters
- Market hours and scheduling
"""

import os
from pathlib import Path
from datetime import time
from zoneinfo import ZoneInfo
from enum import Enum
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path="C:/Users/User/Documents/AI/VV7/.env")

# =============================================================================
# Strategy Configuration
# =============================================================================

class StrategyType(Enum):
    """Intraday trading strategies (V2 - verified true intraday)."""
    ORB_V2 = "orb_v2"                       # Simplified ORB (74.56% win rate, 2.51 PF)
    OVERNIGHT_REVERSAL = "overnight_reversal"  # Buy overnight losers (Sharpe 4.44)
    STOCKS_IN_PLAY = "stocks_in_play"       # First 5-min candle on high-vol stocks (Sharpe 2.81)


# Strategy-specific configurations
STRATEGY_CONFIG = {
    StrategyType.ORB_V2: {
        "name": "ORB V2 (Simplified)",
        "win_rate": "74.56%",
        "profit_factor": 2.51,
        "max_positions": 5,
        "position_size_pct": 0.10,
        "risk_per_trade_pct": 0.02,
        "eod_exit_time": time(15, 0),  # 3:00 PM ET
        "max_range_width_pct": 0.008,  # 0.8% max range width
        "target_multiplier": 0.50,     # 50% of range
        "description": "Breakout above 60-min range (simplified, no VWAP/EMA required)",
    },
    StrategyType.OVERNIGHT_REVERSAL: {
        "name": "Overnight-Intraday Reversal",
        "sharpe_ratio": 4.44,
        "max_positions": 10,
        "position_size_pct": 0.10,
        "risk_per_trade_pct": 0.10,  # No stops, higher risk allocation
        "eod_exit_time": time(16, 0),  # 4:00 PM ET (market close)
        "entry_window_end": time(9, 35),  # Entries only 9:30-9:35 AM
        "no_stops": True,  # Strategy has no stop loss
        "description": "Buy bottom decile of overnight losers at open, sell at close",
    },
    StrategyType.STOCKS_IN_PLAY: {
        "name": "ORB Stocks in Play",
        "sharpe_ratio": 2.81,
        "win_rate": "17-42%",
        "max_positions": 5,
        "position_size_pct": 0.10,
        "risk_per_trade_pct": 0.02,
        "eod_exit_time": time(16, 0),  # 4:00 PM ET
        "entry_window_start": time(9, 35),  # After first 5-min candle
        "entry_window_end": time(9, 40),
        "atr_stop_pct": 0.10,  # 10% of ATR for stops
        "min_avg_volume": 1_000_000,
        "min_atr": 0.50,
        "top_n_stocks": 20,
        "description": "Trade first 5-min candle direction on high-volume stocks",
    },
}

# =============================================================================
# Database Configuration
# =============================================================================

# Expand Windows environment variable to full path
INTRADAY_DB_PATH = os.path.expandvars(r"%LOCALAPPDATA%\VV7SimpleBridge\intraday.db")

# Sync completion marker file (written by VV7 main.py after sync completes)
SYNC_COMPLETE_FILE = os.path.expandvars(r"%LOCALAPPDATA%\VV7SimpleBridge\sync_complete.txt")

# =============================================================================
# Alpaca API Credentials - 3 Accounts for 3 Strategies
# =============================================================================

# ORB Strategy Account (60-min Opening Range Breakout)
ALPACA_ORB_API_KEY = os.environ.get(
    "ALPACA_ORB_API_KEY",
    "PKUWXI5LD5GMPQTLHTGZLJMHMA"
)
ALPACA_ORB_SECRET_KEY = os.environ.get(
    "ALPACA_ORB_SECRET_KEY",
    "9xjaaU9RLuS1TXZ3niVCKdKd14Xm7MVSatkkkUGsFvoH"
)

# WMA20+HA Strategy Account
ALPACA_WMA_API_KEY = os.environ.get(
    "ALPACA_WMA_API_KEY",
    "PKEWDBHRFW7RMW2YXXRCAGE6ZJ"
)
ALPACA_WMA_SECRET_KEY = os.environ.get(
    "ALPACA_WMA_SECRET_KEY",
    "8dYkVbFmJdN3t53bf1dsGv6pZRhRCTffTLR5mLGG1bNn"
)

# HMA+HA Strategy Account
ALPACA_HMA_API_KEY = os.environ.get(
    "ALPACA_HMA_API_KEY",
    "PKTGRHXB4LUKDH7T4PK3SOZIPX"
)
ALPACA_HMA_SECRET_KEY = os.environ.get(
    "ALPACA_HMA_SECRET_KEY",
    "9dCHV3gRciNXFduiQXdvxkV12cUKNmVgM8VGBRGyMEL5"
)

# Account configurations with credentials
ACCOUNTS = {
    StrategyType.ORB_V2: {
        "api_key": ALPACA_ORB_API_KEY,
        "secret_key": ALPACA_ORB_SECRET_KEY,
        "name": "ORB_V2",
    },
    StrategyType.OVERNIGHT_REVERSAL: {
        "api_key": ALPACA_WMA_API_KEY,
        "secret_key": ALPACA_WMA_SECRET_KEY,
        "name": "OVERNIGHT_REVERSAL",
    },
    StrategyType.STOCKS_IN_PLAY: {
        "api_key": ALPACA_HMA_API_KEY,
        "secret_key": ALPACA_HMA_SECRET_KEY,
        "name": "STOCKS_IN_PLAY",
    },
}

# Legacy credentials (backward compatibility)
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_SAFE_API_KEY = os.environ.get("ALPACA_SAFE_API_KEY", ALPACA_ORB_API_KEY)
ALPACA_SAFE_SECRET_KEY = os.environ.get("ALPACA_SAFE_SECRET_KEY", ALPACA_ORB_SECRET_KEY)
ALPACA_CLASSIC_API_KEY = os.environ.get("ALPACA_CLASSIC_API_KEY", ALPACA_WMA_API_KEY)
ALPACA_CLASSIC_SECRET_KEY = os.environ.get("ALPACA_CLASSIC_SECRET_KEY", ALPACA_WMA_SECRET_KEY)

# =============================================================================
# Trading Parameters
# =============================================================================

# Default position sizing
POSITION_SIZE_PCT = 0.10  # 10% per position
RISK_PER_TRADE_PCT = 0.02  # 2% max risk per trade
MAX_POSITIONS = 5  # Per strategy

# Stock filtering criteria
MIN_VOLUME = 1000    # Minimum per-bar volume
MIN_PRICE = 5.00     # Minimum stock price

# ORB-specific parameters
ORB_MIN_RELATIVE_VOLUME = 1.5  # Minimum relative volume for ORB entries

# =============================================================================
# Market Hours and Scheduling
# =============================================================================

# Eastern Time timezone
ET = ZoneInfo("America/New_York")

# Market session times (ET)
MARKET_OPEN = time(9, 30)   # 9:30 AM ET
MARKET_CLOSE = time(16, 0)  # 4:00 PM ET

# Opening range window
OPENING_RANGE_END = time(10, 30)  # 60-min opening range ends at 10:30 AM

# Trading cycle frequency
CYCLE_INTERVAL_MINUTES = 5  # Run strategy every 5 minutes

# =============================================================================
# Logging Configuration
# =============================================================================

# Project root directory
PROJECT_ROOT = Path(__file__).parent

# Logs directory
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# =============================================================================
# Validation
# =============================================================================

def validate_config() -> None:
    """Validate configuration parameters."""
    if not Path(INTRADAY_DB_PATH).parent.exists():
        raise FileNotFoundError(
            f"Database directory does not exist: {Path(INTRADAY_DB_PATH).parent}"
        )

    # Validate all account credentials
    for strategy, account in ACCOUNTS.items():
        if not account["api_key"] or not account["secret_key"]:
            raise ValueError(
                f"{strategy.value} account credentials not found. "
                f"Ensure ALPACA_{strategy.value.upper()}_API_KEY and "
                f"ALPACA_{strategy.value.upper()}_SECRET_KEY are set."
            )

    if MAX_POSITIONS <= 0:
        raise ValueError(f"MAX_POSITIONS must be positive, got {MAX_POSITIONS}")

    if POSITION_SIZE_PCT <= 0 or POSITION_SIZE_PCT > 1:
        raise ValueError(f"POSITION_SIZE_PCT must be between 0 and 1, got {POSITION_SIZE_PCT}")


# Validate on import
validate_config()
