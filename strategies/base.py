"""Base strategy interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar, Signal, Action


@dataclass
class StrategyConfig:
    """Strategy configuration."""
    name: str
    stop_loss_pct: float = 2.0
    take_profit_pct: Optional[float] = None

    # Indicator parameters
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    ma_period: int = 200
    ma_short_period: int = 5


class BaseStrategy(ABC):
    """Abstract base class for trading strategies.

    CRITICAL: Uses symbol-isolated state to prevent contamination
    between different symbols during backtesting.
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self._symbol_state: Dict[str, Dict[str, Any]] = {}

    @property
    def name(self) -> str:
        """Strategy name."""
        return self.config.name

    def _get_state(self, symbol: str) -> Dict[str, Any]:
        """Get symbol-isolated state dict."""
        if symbol not in self._symbol_state:
            self._symbol_state[symbol] = {}
        return self._symbol_state[symbol]

    def _set_state(self, symbol: str, key: str, value: Any) -> None:
        """Set value in symbol-isolated state."""
        if symbol not in self._symbol_state:
            self._symbol_state[symbol] = {}
        self._symbol_state[symbol][key] = value

    def _clear_state(self, symbol: str) -> None:
        """Clear state for a symbol."""
        if symbol in self._symbol_state:
            del self._symbol_state[symbol]

    def reset(self) -> None:
        """Reset all state (call between backtest runs)."""
        self._symbol_state.clear()

    def reset_symbol(self, symbol: str) -> None:
        """Reset state for a specific symbol."""
        self._clear_state(symbol)

    @abstractmethod
    def on_bar(
        self,
        symbol: str,
        bar: Bar,
        history: List[Bar],
        position_open: bool
    ) -> Optional[Signal]:
        """Process a new bar and optionally generate a signal.

        Args:
            symbol: Stock symbol
            bar: Current bar
            history: Historical bars (including current)
            position_open: Whether we have an open position

        Returns:
            Signal if entry/exit triggered, None otherwise
        """
        pass

    def should_exit(
        self,
        symbol: str,
        bar: Bar,
        history: List[Bar],
        entry_price: float
    ) -> Optional[Signal]:
        """Check if position should be exited.

        Default implementation - override for custom exit logic.
        Returns Signal with SELL action if exit triggered.
        """
        return None

    def _create_entry_signal(
        self,
        symbol: str,
        bar: Bar,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        strength: float = 1.0,
        reason: str = ""
    ) -> Signal:
        """Helper to create entry signal."""
        if stop_loss is None and self.config.stop_loss_pct:
            stop_loss = bar.close * (1 - self.config.stop_loss_pct / 100)

        if take_profit is None and self.config.take_profit_pct:
            take_profit = bar.close * (1 + self.config.take_profit_pct / 100)

        return Signal(
            symbol=symbol,
            action=Action.BUY,
            strategy=self.name,
            entry_price=bar.close,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strength=strength,
            reason=reason,
            timestamp=bar.timestamp
        )

    def _create_exit_signal(
        self,
        symbol: str,
        bar: Bar,
        reason: str = ""
    ) -> Signal:
        """Helper to create exit signal."""
        return Signal(
            symbol=symbol,
            action=Action.SELL,
            strategy=self.name,
            entry_price=bar.close,
            reason=reason,
            timestamp=bar.timestamp
        )
