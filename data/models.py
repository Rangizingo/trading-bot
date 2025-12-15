"""Data models for trading bot."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class Action(Enum):
    """Trade action types."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Bar:
    """OHLCV price bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @property
    def typical_price(self) -> float:
        """(High + Low + Close) / 3"""
        return (self.high + self.low + self.close) / 3


@dataclass
class Stock:
    """Stock with VectorVest ratings."""
    symbol: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    # VectorVest ratings
    vst: float = 0.0  # Master rating
    rs: float = 0.0   # Relative Safety
    rv: float = 0.0   # Relative Value
    rt: float = 0.0   # Relative Timing
    # Price data
    price: float = 0.0
    volume: int = 0
    avg_volume: int = 0


@dataclass
class Technicals:
    """Technical indicators for a stock."""
    symbol: str
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    atr: Optional[float] = None
    adx: Optional[float] = None
    vwap: Optional[float] = None


@dataclass
class Signal:
    """Trading signal from a strategy."""
    symbol: str
    action: Action
    strategy: str
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strength: float = 0.0  # For ranking signals
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    """Open position."""
    symbol: str
    shares: int
    entry_price: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strategy: str = ""

    @property
    def cost_basis(self) -> float:
        """Total cost of position."""
        return self.shares * self.entry_price

    def unrealized_pnl(self, current_price: float) -> float:
        """Unrealized profit/loss."""
        return (current_price - self.entry_price) * self.shares

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Unrealized P&L as percentage."""
        return ((current_price - self.entry_price) / self.entry_price) * 100


@dataclass
class TradeResult:
    """Completed trade result."""
    symbol: str
    strategy: str
    entry_price: float
    entry_time: datetime
    exit_price: float
    exit_time: datetime
    shares: int
    pnl: float
    pnl_pct: float
    reason: str  # "stop_loss", "take_profit", "signal", "manual"

    @property
    def is_winner(self) -> bool:
        """Trade was profitable."""
        return self.pnl > 0
