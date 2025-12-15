"""Cumulative RSI mean reversion strategy."""
from typing import List, Optional
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar, Signal, Action
from strategies.base import BaseStrategy, StrategyConfig
from core.indicators import Indicators


class CumulativeRSIStrategy(BaseStrategy):
    """Cumulative RSI(2) mean reversion strategy.

    Entry: Sum of RSI(2) over last 2 bars < 10
    Exit: Cumulative RSI > 65
    Stop: 3%

    CRITICAL FIX: Recalculates fresh each bar, no persistent state.
    """

    def __init__(self):
        config = StrategyConfig(
            name="CumulativeRSI",
            stop_loss_pct=3.0,
            rsi_period=2,
            ma_period=200
        )
        super().__init__(config)
        self.cumulative_bars = 2
        self.entry_threshold = 10.0
        self.exit_threshold = 65.0

    def _calculate_cumulative_rsi(self, closes: List[float]) -> Optional[float]:
        """Calculate sum of RSI(2) over last N bars.

        FIXED: Recalculates fresh from closes, no persistent state.
        """
        if len(closes) < self.config.rsi_period + self.cumulative_bars + 1:
            return None

        rsi_values = []
        for i in range(self.cumulative_bars):
            # Calculate RSI at each of the last N bars
            end_idx = len(closes) - i
            if end_idx < self.config.rsi_period + 1:
                return None
            rsi = Indicators.rsi(closes[:end_idx], self.config.rsi_period)
            if rsi is None:
                return None
            rsi_values.append(rsi)

        return sum(rsi_values)

    def on_bar(
        self,
        symbol: str,
        bar: Bar,
        history: List[Bar],
        position_open: bool
    ) -> Optional[Signal]:
        """Process bar and generate signal."""
        if len(history) < self.config.ma_period + 1:
            return None

        closes = [b.close for b in history]

        # Calculate indicators
        cumulative_rsi = self._calculate_cumulative_rsi(closes)
        ma_200 = Indicators.sma(closes, self.config.ma_period)

        if cumulative_rsi is None or ma_200 is None:
            return None

        current_close = closes[-1]

        # If we have a position, check exit
        if position_open:
            if cumulative_rsi > self.exit_threshold:
                return self._create_exit_signal(
                    symbol, bar,
                    reason=f"CumRSI={cumulative_rsi:.1f}"
                )
            return None

        # Entry: Cumulative RSI < 10 AND Close > 200 MA
        if cumulative_rsi < self.entry_threshold and current_close > ma_200:
            return self._create_entry_signal(
                symbol, bar,
                strength=self.entry_threshold - cumulative_rsi,
                reason=f"CumRSI={cumulative_rsi:.1f}, above 200MA"
            )

        return None
