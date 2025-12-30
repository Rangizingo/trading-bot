"""
Base Strategy Interface

Abstract base class defining the interface for all intraday trading strategies.
Each strategy must implement entry/exit logic and candidate screening.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import time as dt_time
from dataclasses import dataclass


@dataclass
class EntrySignal:
    """Represents an entry signal from a strategy"""
    symbol: str
    price: float
    target: Optional[float] = None
    stop: Optional[float] = None
    reason: str = ""
    metadata: Optional[Dict] = None


@dataclass
class ExitSignal:
    """Represents an exit signal from a strategy"""
    symbol: str
    price: float
    reason: str  # 'target', 'stop', 'signal', 'eod'
    pnl_pct: Optional[float] = None
    metadata: Optional[Dict] = None


class BaseStrategy(ABC):
    """
    Abstract base class for intraday trading strategies.

    Each strategy defines:
    - Entry conditions
    - Exit conditions
    - Position sizing
    - EOD exit time
    """

    def __init__(
        self,
        name: str,
        max_positions: int = 5,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(15, 45),
        min_price: float = 5.0,
    ):
        """
        Initialize base strategy.

        Args:
            name: Strategy name (e.g., 'ORB', 'WMA20_HA')
            max_positions: Maximum simultaneous positions
            position_size_pct: Position size as % of equity (e.g., 0.10 = 10%)
            risk_per_trade_pct: Max risk per trade as % of equity (e.g., 0.02 = 2%)
            eod_exit_time: Time to force-close all positions (Eastern Time)
            min_price: Minimum stock price filter
        """
        self.name = name
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct
        self.risk_per_trade_pct = risk_per_trade_pct
        self.eod_exit_time = eod_exit_time
        self.min_price = min_price

    @abstractmethod
    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if a symbol meets entry criteria.

        Args:
            symbol: Stock symbol to check

        Returns:
            EntrySignal if entry conditions met, None otherwise
        """
        pass

    @abstractmethod
    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if a position should be exited.

        Args:
            symbol: Stock symbol
            position: Position dict with keys: entry_price, shares, entry_time, etc.

        Returns:
            ExitSignal if exit conditions met, None otherwise
        """
        pass

    @abstractmethod
    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen all symbols for entry candidates.

        Returns:
            List of EntrySignal objects for symbols meeting entry criteria
        """
        pass

    def calculate_position_size(self, equity: float, entry_price: float,
                                 stop_price: Optional[float] = None) -> int:
        """
        Calculate number of shares to buy based on position sizing rules.

        Uses the smaller of:
        1. Position size % of equity
        2. Risk % of equity / (entry - stop)

        Args:
            equity: Account equity
            entry_price: Expected entry price
            stop_price: Stop loss price (if applicable)

        Returns:
            Number of shares to buy
        """
        # Method 1: Position size as % of equity
        position_value = equity * self.position_size_pct
        shares_by_position = int(position_value / entry_price)

        # Method 2: Risk-based sizing (if stop provided)
        if stop_price and stop_price < entry_price:
            risk_per_share = entry_price - stop_price
            max_risk = equity * self.risk_per_trade_pct
            shares_by_risk = int(max_risk / risk_per_share)

            # Use the more conservative (smaller) size
            return min(shares_by_position, shares_by_risk)

        return shares_by_position

    def is_eod_exit_time(self, current_time: dt_time) -> bool:
        """Check if current time is at or past EOD exit time"""
        return current_time >= self.eod_exit_time

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}(name='{self.name}', "
                f"max_positions={self.max_positions}, "
                f"eod_exit='{self.eod_exit_time}')")
