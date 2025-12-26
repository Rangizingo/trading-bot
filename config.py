"""
Configuration module for Connors RSI Trading Bot.

Centralizes all configuration parameters including:
- Database paths
- Alpaca API credentials
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
# Trading Mode Configuration
# =============================================================================

class TradingMode(Enum):
    """Trading mode selection for entry and exit behavior."""
    SAFE = "safe"
    CLASSIC = "classic"


MODE_INFO = {
    TradingMode.SAFE: {
        "name": "SAFE MODE",
        "subtitle": "Recommended for beginners",
        "features": [
            ("Entry", "Bracket order (BUY + STOP)"),
            ("Stop Loss", "3% below entry"),
            ("Exit", "Price > SMA5 OR stop triggered"),
            ("Max Loss", "3% per position"),
            ("Risk", "Lower (capped losses)"),
        ]
    },
    TradingMode.CLASSIC: {
        "name": "CLASSIC MODE",
        "subtitle": "Larry Connors original",
        "features": [
            ("Entry", "Simple BUY order"),
            ("Stop Loss", "None"),
            ("Exit", "Price > SMA5 only"),
            ("Max Loss", "Unlimited (ride the dip)"),
            ("Risk", "Higher (but 75% win rate historically)"),
        ]
    }
}

# =============================================================================
# Database Configuration
# =============================================================================

# Expand Windows environment variable to full path
INTRADAY_DB_PATH = os.path.expandvars(r"%LOCALAPPDATA%\VV7SimpleBridge\intraday.db")

# Sync completion marker file (written by VV7 main.py after sync completes)
SYNC_COMPLETE_FILE = os.path.expandvars(r"%LOCALAPPDATA%\VV7SimpleBridge\sync_complete.txt")

# =============================================================================
# Alpaca API Credentials
# =============================================================================

# Legacy credentials (kept for backward compatibility)
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")

# CRSI-SAFE account (bracket orders with stop losses)
ALPACA_SAFE_API_KEY = os.environ.get("ALPACA_SAFE_API_KEY", "")
ALPACA_SAFE_SECRET_KEY = os.environ.get("ALPACA_SAFE_SECRET_KEY", "")

# CRSI-CLASSIC account (simple orders, no stops)
ALPACA_CLASSIC_API_KEY = os.environ.get("ALPACA_CLASSIC_API_KEY", "")
ALPACA_CLASSIC_SECRET_KEY = os.environ.get("ALPACA_CLASSIC_SECRET_KEY", "")

# Validate dual-account credentials are loaded
if not ALPACA_SAFE_API_KEY or not ALPACA_SAFE_SECRET_KEY:
    raise ValueError(
        "SAFE account credentials not found. Ensure ALPACA_SAFE_API_KEY and "
        "ALPACA_SAFE_SECRET_KEY are set in environment variables or .env file."
    )

if not ALPACA_CLASSIC_API_KEY or not ALPACA_CLASSIC_SECRET_KEY:
    raise ValueError(
        "CLASSIC account credentials not found. Ensure ALPACA_CLASSIC_API_KEY and "
        "ALPACA_CLASSIC_SECRET_KEY are set in environment variables or .env file."
    )

# =============================================================================
# Trading Parameters
# =============================================================================

# Capital allocation
CAPITAL = 100000
POSITION_SIZE_PCT = 0.10  # 10% per position
MAX_POSITIONS = 5  # Default fallback
MAX_POSITIONS_SAFE = 10  # More positions allowed with stop protection
MAX_POSITIONS_CLASSIC = 7  # Fewer positions without stops (higher risk per position)

# Risk management
STOP_LOSS_PCT = 0.03  # 3% stop loss

# Connors RSI strategy parameters
ENTRY_RSI = 10  # Enter when RSI drops below this level (65-75% win rate) - DEPRECATED, use ENTRY_CRSI
ENTRY_CRSI = 10  # Enter when ConnorsRSI drops below this level (true Connors strategy)
# EXIT: Close > SMA5 (true Connors exit - no RSI exit threshold)

# Stock filtering criteria
MIN_VOLUME = 1000    # Minimum per-bar volume (filters out illiquid stocks like BBP)
MIN_PRICE = 5.00     # Minimum stock price

# =============================================================================
# Market Hours and Scheduling
# =============================================================================

# Eastern Time timezone
ET = ZoneInfo("America/New_York")

# Market session times (ET)
MARKET_OPEN = time(9, 30)   # 9:30 AM ET
MARKET_CLOSE = time(16, 0)  # 4:00 PM ET

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
# Derived Configuration
# =============================================================================

# Position sizing
POSITION_SIZE_DOLLARS = CAPITAL * POSITION_SIZE_PCT

# Validate configuration
def validate_config() -> None:
    """Validate configuration parameters."""
    if not Path(INTRADAY_DB_PATH).parent.exists():
        raise FileNotFoundError(
            f"Database directory does not exist: {Path(INTRADAY_DB_PATH).parent}"
        )

    if MAX_POSITIONS <= 0:
        raise ValueError(f"MAX_POSITIONS must be positive, got {MAX_POSITIONS}")

    if POSITION_SIZE_PCT <= 0 or POSITION_SIZE_PCT > 1:
        raise ValueError(f"POSITION_SIZE_PCT must be between 0 and 1, got {POSITION_SIZE_PCT}")

    if STOP_LOSS_PCT <= 0 or STOP_LOSS_PCT >= 1:
        raise ValueError(f"STOP_LOSS_PCT must be between 0 and 1, got {STOP_LOSS_PCT}")

    if ENTRY_RSI <= 0 or ENTRY_RSI >= 100:
        raise ValueError(f"ENTRY_RSI must be between 0 and 100, got {ENTRY_RSI}")

    if ENTRY_CRSI <= 0 or ENTRY_CRSI >= 100:
        raise ValueError(f"ENTRY_CRSI must be between 0 and 100, got {ENTRY_CRSI}")


# Validate on import
validate_config()
