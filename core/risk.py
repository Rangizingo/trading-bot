"""Risk management and position sizing."""
from dataclasses import dataclass
from typing import Optional
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from config import TRADING


@dataclass
class RiskLimits:
    """Current risk status."""
    can_trade: bool
    reason: str = ""
    daily_drawdown_pct: float = 0.0
    total_drawdown_pct: float = 0.0


class RiskManager:
    """Manages risk limits and position sizing."""

    def __init__(
        self,
        daily_drawdown_limit_pct: float = TRADING.daily_drawdown_limit_pct,
        total_drawdown_limit_pct: float = TRADING.total_drawdown_limit_pct,
        max_positions: int = TRADING.max_positions,
        risk_per_trade_pct: float = TRADING.risk_per_trade_pct,
        kelly_fraction: float = TRADING.kelly_fraction
    ):
        self.daily_drawdown_limit_pct = daily_drawdown_limit_pct
        self.total_drawdown_limit_pct = total_drawdown_limit_pct
        self.max_positions = max_positions
        self.risk_per_trade_pct = risk_per_trade_pct
        self.kelly_fraction = kelly_fraction

        # Track daily starting equity
        self.daily_start_equity: Optional[float] = None
        self.peak_equity: Optional[float] = None

    def set_daily_start(self, equity: float) -> None:
        """Set starting equity for the day."""
        self.daily_start_equity = equity
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

    def update_peak(self, equity: float) -> None:
        """Update peak equity if new high."""
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

    def check_limits(
        self,
        current_equity: float,
        current_positions: int
    ) -> RiskLimits:
        """Check all risk limits."""
        # Check max positions
        if current_positions >= self.max_positions:
            return RiskLimits(
                can_trade=False,
                reason=f"Max positions reached ({self.max_positions})"
            )

        # Check daily drawdown
        if self.daily_start_equity:
            daily_dd = ((self.daily_start_equity - current_equity) / self.daily_start_equity) * 100
            if daily_dd >= self.daily_drawdown_limit_pct:
                return RiskLimits(
                    can_trade=False,
                    reason=f"Daily drawdown limit hit ({daily_dd:.1f}%)",
                    daily_drawdown_pct=daily_dd
                )

        # Check total drawdown
        if self.peak_equity:
            total_dd = ((self.peak_equity - current_equity) / self.peak_equity) * 100
            if total_dd >= self.total_drawdown_limit_pct:
                return RiskLimits(
                    can_trade=False,
                    reason=f"Total drawdown limit hit ({total_dd:.1f}%)",
                    total_drawdown_pct=total_dd
                )

        return RiskLimits(can_trade=True)

    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None
    ) -> int:
        """Calculate position size using Half-Kelly or fixed percentage.

        Returns number of shares to buy.
        """
        # If we have stats, use Half-Kelly
        if win_rate and avg_win and avg_loss and avg_loss > 0:
            # Kelly formula: K = W - (1-W)/R where R = avg_win/avg_loss
            r = avg_win / avg_loss
            kelly = win_rate - ((1 - win_rate) / r)
            kelly = max(0, kelly)  # Don't go negative

            # Apply fraction (Half-Kelly)
            position_pct = kelly * self.kelly_fraction * 100
        else:
            # Fall back to config position size
            position_pct = TRADING.position_size_pct

        # Cap at max risk per trade if stop loss provided
        if stop_loss and entry_price > stop_loss:
            risk_per_share = entry_price - stop_loss
            max_loss = capital * (self.risk_per_trade_pct / 100)
            max_shares_by_risk = int(max_loss / risk_per_share)
        else:
            max_shares_by_risk = float('inf')

        # Calculate shares from position percentage
        position_value = capital * (position_pct / 100)
        shares_by_pct = int(position_value / entry_price)

        # Take minimum of the two
        shares = min(shares_by_pct, max_shares_by_risk)

        return max(0, shares)

    def calculate_stop_loss(
        self,
        entry_price: float,
        stop_pct: float
    ) -> float:
        """Calculate stop loss price."""
        return entry_price * (1 - stop_pct / 100)

    def calculate_take_profit(
        self,
        entry_price: float,
        target_pct: float
    ) -> float:
        """Calculate take profit price."""
        return entry_price * (1 + target_pct / 100)
