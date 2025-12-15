"""Backtest metrics calculation."""
from dataclasses import dataclass
from typing import List, Optional
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import TradeResult


@dataclass
class BacktestMetrics:
    """Backtest performance metrics."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    sharpe_ratio: float

    def __str__(self) -> str:
        return (
            f"Trades: {self.total_trades} | "
            f"Win Rate: {self.win_rate:.1f}% | "
            f"PF: {self.profit_factor:.2f} | "
            f"PnL: ${self.total_pnl:,.2f} | "
            f"Max DD: {self.max_drawdown:.1f}%"
        )


def calculate_metrics(
    trades: List[TradeResult],
    equity_curve: Optional[List[float]] = None,
    initial_capital: float = 100000
) -> BacktestMetrics:
    """Calculate backtest metrics from trade results.

    Args:
        trades: List of completed trades
        equity_curve: Equity at each point (for Sharpe/drawdown)
        initial_capital: Starting capital
    """
    if not trades:
        return BacktestMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            total_pnl=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0
        )

    # Separate winners and losers
    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]

    total_trades = len(trades)
    winning_trades = len(winners)
    losing_trades = len(losers)

    # Win rate
    win_rate = (winning_trades / total_trades) * 100

    # Profit factor
    gross_profit = sum(t.pnl for t in winners)
    gross_loss = abs(sum(t.pnl for t in losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Total P&L
    total_pnl = sum(t.pnl for t in trades)

    # Average win/loss
    avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
    avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0

    # Max drawdown from equity curve
    max_drawdown = 0.0
    if equity_curve and len(equity_curve) > 1:
        max_drawdown = calculate_max_drawdown(equity_curve)

    # Sharpe ratio
    sharpe_ratio = 0.0
    if equity_curve and len(equity_curve) > 1:
        sharpe_ratio = calculate_sharpe_ratio(equity_curve)

    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_pnl=total_pnl,
        avg_win=avg_win,
        avg_loss=avg_loss,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio
    )


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """Calculate maximum drawdown percentage from equity curve."""
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for equity in equity_curve:
        if equity > peak:
            peak = equity

        if peak > 0:
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

    return max_dd


def calculate_sharpe_ratio(
    equity_curve: List[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252 * 78  # 5-min bars per year
) -> float:
    """Calculate annualized Sharpe ratio.

    Args:
        equity_curve: Equity at each point
        risk_free_rate: Annual risk-free rate (default 0)
        periods_per_year: Number of periods per year (for annualization)
    """
    if len(equity_curve) < 2:
        return 0.0

    # Calculate returns
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i-1] > 0:
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            returns.append(ret)

    if not returns:
        return 0.0

    # Mean and std of returns
    mean_return = sum(returns) / len(returns)

    if len(returns) < 2:
        return 0.0

    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_return = variance ** 0.5

    if std_return == 0:
        return 0.0

    # Annualize
    annual_return = mean_return * periods_per_year
    annual_std = std_return * (periods_per_year ** 0.5)

    sharpe = (annual_return - risk_free_rate) / annual_std

    return sharpe


def calculate_calmar_ratio(
    equity_curve: List[float],
    periods_per_year: int = 252 * 78
) -> float:
    """Calculate Calmar ratio (annual return / max drawdown)."""
    if len(equity_curve) < 2:
        return 0.0

    # Annual return
    total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
    periods = len(equity_curve)
    annual_return = total_return * (periods_per_year / periods)

    # Max drawdown
    max_dd = calculate_max_drawdown(equity_curve) / 100  # Convert to decimal

    if max_dd == 0:
        return float('inf')

    return annual_return / max_dd
