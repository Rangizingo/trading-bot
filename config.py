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
    """Trading strategies (V3 - LONG ONLY)."""
    VWAP_RSI2_SWING = "vwap_rsi2_swing"  # VWAP + RSI(2) swing (holds overnight)
    VWAP_PULLBACK = "vwap_pullback"       # Mid-day mean reversion (10 AM - 2 PM)
    ORB_15MIN = "orb_15min"               # 15-min ORB breakout (9:45-11 AM)


# Strategy-specific configurations
STRATEGY_CONFIG = {
    StrategyType.VWAP_RSI2_SWING: {
        "name": "VWAP + RSI(2) Swing (Overnight Hold)",
        "max_positions": 5,
        "position_size_pct": 0.20,
        "risk_per_trade_pct": 0.02,
        "eod_exit_time": time(15, 55),  # 3:55 PM ET (trend check, not forced exit)
        "min_rvol": 1.5,               # Minimum relative volume
        "min_adx": 20.0,               # Minimum ADX for trend strength
        "holds_overnight": True,       # This strategy holds overnight
        "description": "VWAP + RSI(2) swing: buy oversold above VWAP, hold overnight",
    },
    StrategyType.VWAP_PULLBACK: {
        "name": "VWAP Pullback (Mean Reversion)",
        "max_positions": 5,
        "position_size_pct": 0.10,
        "risk_per_trade_pct": 0.015,
        "eod_exit_time": time(14, 0),  # 2:00 PM ET
        "min_price": 10.0,             # $10 minimum for this strategy
        "min_avg_volume": 500_000,     # 500k minimum volume
        "description": "Buy pullbacks to VWAP from above (10 AM - 2 PM, LONG ONLY)",
    },
    StrategyType.ORB_15MIN: {
        "name": "ORB 15-Min (Opening Range Breakout)",
        "max_positions": 3,
        "position_size_pct": 0.10,
        "risk_per_trade_pct": 0.02,
        "eod_exit_time": time(11, 0),  # 11:00 AM ET
        "min_range_pct": 0.003,        # 0.3% minimum range
        "max_range_pct": 0.015,        # 1.5% maximum range
        "min_relative_volume": 1.5,    # 1.5x RVOL required
        "description": "15-min ORB breakout above range high (9:45-11 AM, LONG ONLY)",
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
# Account mapping: Gap and Go -> ORB account, VWAP Pullback -> WMA account, ORB 15-Min -> HMA account
ACCOUNTS = {
    StrategyType.VWAP_RSI2_SWING: {
        "api_key": ALPACA_ORB_API_KEY,
        "secret_key": ALPACA_ORB_SECRET_KEY,
        "name": "VWAP_RSI2_SWING",
    },
    StrategyType.VWAP_PULLBACK: {
        "api_key": ALPACA_WMA_API_KEY,
        "secret_key": ALPACA_WMA_SECRET_KEY,
        "name": "VWAP_PULLBACK",
    },
    StrategyType.ORB_15MIN: {
        "api_key": ALPACA_HMA_API_KEY,
        "secret_key": ALPACA_HMA_SECRET_KEY,
        "name": "ORB_15MIN",
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
