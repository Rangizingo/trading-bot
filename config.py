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
    """Intraday trading strategies."""
    ORB = "orb"           # 60-min Opening Range Breakout (89.4% win rate)
    WMA20_HA = "wma20_ha" # WMA(20) + Heikin Ashi (83% win rate)
    HMA_HA = "hma_ha"     # HMA + Heikin Ashi (77% win rate)


# Strategy-specific configurations
STRATEGY_CONFIG = {
    StrategyType.ORB: {
        "name": "60-Min Opening Range Breakout",
        "win_rate": "89.4%",
        "max_positions": 5,
        "position_size_pct": 0.10,
        "risk_per_trade_pct": 0.02,
        "eod_exit_time": time(14, 0),  # 2:00 PM ET
        "description": "Breakout above 60-min range with volume + VWAP + EMA confirmation",
    },
    StrategyType.WMA20_HA: {
        "name": "WMA(20) + Heikin Ashi",
        "win_rate": "83%",
        "max_positions": 5,
        "position_size_pct": 0.10,
        "risk_per_trade_pct": 0.02,
        "eod_exit_time": time(15, 45),  # 3:45 PM ET
        "description": "WMA crossover with 2 green flat-bottom HA candles",
    },
    StrategyType.HMA_HA: {
        "name": "HMA + Heikin Ashi",
        "win_rate": "77%",
        "max_positions": 5,
        "position_size_pct": 0.10,
        "risk_per_trade_pct": 0.02,
        "eod_exit_time": time(15, 45),  # 3:45 PM ET
        "description": "HMA crossover with green HA confirmation",
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
    StrategyType.ORB: {
        "api_key": ALPACA_ORB_API_KEY,
        "secret_key": ALPACA_ORB_SECRET_KEY,
        "name": "ORB",
    },
    StrategyType.WMA20_HA: {
        "api_key": ALPACA_WMA_API_KEY,
        "secret_key": ALPACA_WMA_SECRET_KEY,
        "name": "WMA20_HA",
    },
    StrategyType.HMA_HA: {
        "api_key": ALPACA_HMA_API_KEY,
        "secret_key": ALPACA_HMA_SECRET_KEY,
        "name": "HMA_HA",
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
