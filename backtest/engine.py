"""Backtest engine with corrected logic."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Type
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar, Signal, Action, Position, TradeResult
from strategies.base import BaseStrategy
from backtest.metrics import calculate_metrics, BacktestMetrics


@dataclass
class BacktestConfig:
    """Backtest configuration."""
    initial_capital: float = 100000
    position_size_pct: float = 10.0
    max_positions: int = 5
    commission_per_trade: float = 0.0


@dataclass
class BacktestResult:
    """Complete backtest result."""
    strategy_name: str
    config: BacktestConfig
    trades: List[TradeResult]
    equity_curve: List[float]
    metrics: BacktestMetrics


class BacktestEngine:
    """Backtest engine with correct capital and gap handling."""

    def __init__(self, strategy: BaseStrategy, config: BacktestConfig = None):
        self.strategy = strategy
        self.config = config or BacktestConfig()

        # State
        self.available_capital = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[TradeResult] = []
        self.equity_curve: List[float] = []

    def reset(self) -> None:
        """Reset engine state."""
        self.available_capital = self.config.initial_capital
        self.positions.clear()
        self.trades.clear()
        self.equity_curve.clear()
        self.strategy.reset()

    def run(
        self,
        symbols: List[str],
        bars_by_symbol: Dict[str, List[Bar]]
    ) -> BacktestResult:
        """Run backtest on multiple symbols.

        Args:
            symbols: List of symbols to test
            bars_by_symbol: Dict mapping symbol to list of bars
        """
        self.reset()

        # Get all unique timestamps across all symbols
        all_timestamps = set()
        for bars in bars_by_symbol.values():
            for bar in bars:
                all_timestamps.add(bar.timestamp)

        sorted_timestamps = sorted(all_timestamps)

        # Process each timestamp
        for timestamp in sorted_timestamps:
            current_prices = {}

            # First pass: collect current prices and check exits
            for symbol in symbols:
                bars = bars_by_symbol.get(symbol, [])
                bar = self._get_bar_at_timestamp(bars, timestamp)
                if bar:
                    current_prices[symbol] = bar.close

                    # Check stops/targets for open positions
                    if symbol in self.positions:
                        self._check_exit_conditions(symbol, bar, bars)

            # Second pass: check for new entries
            for symbol in symbols:
                bars = bars_by_symbol.get(symbol, [])
                bar = self._get_bar_at_timestamp(bars, timestamp)
                if bar and symbol not in self.positions:
                    history = self._get_history_up_to(bars, timestamp)
                    if len(history) > 0:
                        self._check_entry(symbol, bar, history)

            # Record equity at this timestamp
            equity = self._calculate_equity(current_prices)
            self.equity_curve.append(equity)

        # Close any remaining positions at last price
        for symbol in list(self.positions.keys()):
            if symbol in bars_by_symbol and bars_by_symbol[symbol]:
                last_bar = bars_by_symbol[symbol][-1]
                self._close_position(symbol, last_bar.close, last_bar.timestamp, "end_of_test")

        # Calculate metrics
        metrics = calculate_metrics(
            self.trades,
            self.equity_curve,
            self.config.initial_capital
        )

        return BacktestResult(
            strategy_name=self.strategy.name,
            config=self.config,
            trades=self.trades,
            equity_curve=self.equity_curve,
            metrics=metrics
        )

    def _get_bar_at_timestamp(self, bars: List[Bar], timestamp: datetime) -> Optional[Bar]:
        """Get bar at specific timestamp."""
        for bar in bars:
            if bar.timestamp == timestamp:
                return bar
        return None

    def _get_history_up_to(self, bars: List[Bar], timestamp: datetime) -> List[Bar]:
        """Get all bars up to and including timestamp."""
        return [b for b in bars if b.timestamp <= timestamp]

    def _check_entry(self, symbol: str, bar: Bar, history: List[Bar]) -> None:
        """Check if strategy generates entry signal."""
        if len(self.positions) >= self.config.max_positions:
            return

        signal = self.strategy.on_bar(symbol, bar, history, position_open=False)

        if signal and signal.action == Action.BUY:
            self._open_position(symbol, bar, signal)

    def _check_exit_conditions(self, symbol: str, bar: Bar, all_bars: List[Bar]) -> None:
        """Check stop loss, take profit, and strategy exit signals.

        CRITICAL FIXES:
        1. Gap handling: exit at bar.open if gap through level
        2. Same-bar SL/TP: check which hit first based on bar.open
        """
        if symbol not in self.positions:
            return

        position = self.positions[symbol]

        # Check stop loss and take profit
        stop_hit = position.stop_loss and bar.low <= position.stop_loss
        tp_hit = position.take_profit and bar.high >= position.take_profit

        if stop_hit or tp_hit:
            # CRITICAL FIX: Determine exit price considering gaps
            exit_price, reason = self._determine_exit_price(bar, position, stop_hit, tp_hit)
            self._close_position(symbol, exit_price, bar.timestamp, reason)
            return

        # Check strategy exit signal
        history = self._get_history_up_to(all_bars, bar.timestamp)
        signal = self.strategy.on_bar(symbol, bar, history, position_open=True)

        if signal and signal.action == Action.SELL:
            self._close_position(symbol, bar.close, bar.timestamp, signal.reason or "signal")

    def _determine_exit_price(
        self,
        bar: Bar,
        position: Position,
        stop_hit: bool,
        tp_hit: bool
    ) -> tuple:
        """Determine exit price with gap handling.

        CRITICAL FIXES:
        1. If gap through stop: exit at bar.open (not stop price)
        2. If gap through TP: exit at bar.open (not TP price)
        3. If both hit same bar: check which hit first based on bar.open
        """
        # Gap down through stop loss
        if stop_hit and bar.open < position.stop_loss:
            return bar.open, "stop_loss_gap"

        # Gap up through take profit
        if tp_hit and bar.open > position.take_profit:
            return bar.open, "take_profit_gap"

        # Both hit in same bar - determine which first
        if stop_hit and tp_hit:
            # Check if open is closer to stop or TP
            dist_to_stop = abs(bar.open - position.stop_loss)
            dist_to_tp = abs(bar.open - position.take_profit)

            if dist_to_stop < dist_to_tp:
                return position.stop_loss, "stop_loss"
            else:
                return position.take_profit, "take_profit"

        # Normal stop loss hit
        if stop_hit:
            return position.stop_loss, "stop_loss"

        # Normal take profit hit
        if tp_hit:
            return position.take_profit, "take_profit"

        return bar.close, "unknown"

    def _open_position(self, symbol: str, bar: Bar, signal: Signal) -> None:
        """Open a new position.

        CRITICAL FIX: Deduct capital from available.
        """
        # Calculate position size
        position_value = self.available_capital * (self.config.position_size_pct / 100)
        shares = int(position_value / bar.close)

        if shares <= 0:
            return

        cost = shares * bar.close + self.config.commission_per_trade

        if cost > self.available_capital:
            return

        # CRITICAL FIX: Deduct capital
        self.available_capital -= cost

        self.positions[symbol] = Position(
            symbol=symbol,
            shares=shares,
            entry_price=bar.close,
            entry_time=bar.timestamp,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy=signal.strategy
        )

    def _close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_time: datetime,
        reason: str
    ) -> None:
        """Close a position.

        CRITICAL FIX: Return full proceeds to available capital.
        """
        if symbol not in self.positions:
            return

        position = self.positions[symbol]

        # Calculate P&L
        pnl = (exit_price - position.entry_price) * position.shares
        pnl -= self.config.commission_per_trade  # Exit commission
        pnl_pct = ((exit_price - position.entry_price) / position.entry_price) * 100

        # CRITICAL FIX: Return full proceeds (not just PnL)
        proceeds = exit_price * position.shares - self.config.commission_per_trade
        self.available_capital += proceeds

        # Record trade
        self.trades.append(TradeResult(
            symbol=symbol,
            strategy=position.strategy,
            entry_price=position.entry_price,
            entry_time=position.entry_time,
            exit_price=exit_price,
            exit_time=exit_time,
            shares=position.shares,
            pnl=pnl,
            pnl_pct=pnl_pct,
            reason=reason
        ))

        del self.positions[symbol]

    def _calculate_equity(self, current_prices: Dict[str, float]) -> float:
        """Calculate total equity including unrealized P&L.

        CRITICAL: Track equity at every bar for accurate metrics.
        """
        positions_value = sum(
            current_prices.get(p.symbol, p.entry_price) * p.shares
            for p in self.positions.values()
        )
        return self.available_capital + positions_value
