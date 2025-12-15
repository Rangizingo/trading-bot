"""Position and capital management."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Position, TradeResult


class PositionManager:
    """Manages positions and tracks capital correctly."""

    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.available_capital = initial_capital  # Cash not in positions
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeResult] = []
        self.peak_equity = initial_capital

    def open_position(
        self,
        symbol: str,
        shares: int,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        strategy: str = ""
    ) -> Optional[Position]:
        """Open a new position, deducting capital."""
        if symbol in self.positions:
            return None  # Already have position

        cost = shares * entry_price
        if cost > self.available_capital:
            return None  # Not enough capital

        # CRITICAL: Deduct capital
        self.available_capital -= cost

        position = Position(
            symbol=symbol,
            shares=shares,
            entry_price=entry_price,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy
        )
        self.positions[symbol] = position
        return position

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "signal"
    ) -> Optional[TradeResult]:
        """Close position and return full proceeds to capital."""
        if symbol not in self.positions:
            return None

        position = self.positions[symbol]

        # Calculate P&L
        pnl = (exit_price - position.entry_price) * position.shares
        pnl_pct = ((exit_price - position.entry_price) / position.entry_price) * 100

        # CRITICAL: Return full proceeds (not just PnL)
        proceeds = exit_price * position.shares
        self.available_capital += proceeds

        # Record trade
        trade = TradeResult(
            symbol=symbol,
            strategy=position.strategy,
            entry_price=position.entry_price,
            entry_time=position.entry_time,
            exit_price=exit_price,
            exit_time=datetime.now(),
            shares=position.shares,
            pnl=pnl,
            pnl_pct=pnl_pct,
            reason=reason
        )
        self.trade_history.append(trade)

        # Remove position
        del self.positions[symbol]

        # Update peak equity
        current_equity = self.get_equity({symbol: exit_price})
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        return trade

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol if exists."""
        return self.positions.get(symbol)

    def get_all_positions(self) -> List[Position]:
        """Get all open positions."""
        return list(self.positions.values())

    def get_available_capital(self) -> float:
        """Get cash available for new positions."""
        return self.available_capital

    def get_allocated_capital(self) -> float:
        """Get capital currently in positions (at entry prices)."""
        return sum(p.cost_basis for p in self.positions.values())

    def get_equity(self, current_prices: Dict[str, float]) -> float:
        """Get total equity (cash + positions at current prices)."""
        positions_value = sum(
            current_prices.get(p.symbol, p.entry_price) * p.shares
            for p in self.positions.values()
        )
        return self.available_capital + positions_value

    def get_unrealized_pnl(self, current_prices: Dict[str, float]) -> float:
        """Get total unrealized P&L across all positions."""
        return sum(
            p.unrealized_pnl(current_prices.get(p.symbol, p.entry_price))
            for p in self.positions.values()
        )

    def get_realized_pnl(self) -> float:
        """Get total realized P&L from closed trades."""
        return sum(t.pnl for t in self.trade_history)

    def position_count(self) -> int:
        """Number of open positions."""
        return len(self.positions)
