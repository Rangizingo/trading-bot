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
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path="C:/Users/User/Documents/AI/VV7/.env")

# =============================================================================
# Database Configuration
# =============================================================================

# Expand Windows environment variable to full path
INTRADAY_DB_PATH = os.path.expandvars(r"%LOCALAPPDATA%\VV7SimpleBridge\intraday.db")

# =============================================================================
# Alpaca API Credentials
# =============================================================================

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")

# Validate credentials are loaded
if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    raise ValueError(
        "Alpaca credentials not found. Ensure ALPACA_API_KEY and ALPACA_SECRET_KEY "
        "are set in environment variables or .env file."
    )

# =============================================================================
# Trading Parameters
# =============================================================================

# Capital allocation
CAPITAL = 100000
POSITION_SIZE_PCT = 0.10  # 10% per position
MAX_POSITIONS = 5

# Risk management
STOP_LOSS_PCT = 0.03  # 3% stop loss

# Connors RSI strategy parameters
ENTRY_RSI = 5   # Enter when RSI drops to this level
EXIT_RSI = 60   # Exit when RSI rises to this level

# Stock filtering criteria
MIN_VOLUME = 100000  # Minimum daily volume
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

    if EXIT_RSI <= 0 or EXIT_RSI >= 100:
        raise ValueError(f"EXIT_RSI must be between 0 and 100, got {EXIT_RSI}")

    if EXIT_RSI <= ENTRY_RSI:
        raise ValueError(f"EXIT_RSI ({EXIT_RSI}) must be greater than ENTRY_RSI ({ENTRY_RSI})")


# Validate on import
validate_config()
