"""Connors RSI(2) mean reversion strategy."""
from typing import List, Optional
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar, Signal, Action
from strategies.base import BaseStrategy, StrategyConfig
from core.indicators import Indicators


class ConnorsRSI2Strategy(BaseStrategy):
    """RSI(2) mean reversion strategy.

    Entry: RSI(2) < 5 AND Close > 200 MA
    Exit: RSI(2) > 60 OR Close > 5 MA
    Stop: 3%

    Based on Larry Connors research showing 75-83% win rate.
    """

    def __init__(self):
        config = StrategyConfig(
            name="ConnorsRSI2",
            stop_loss_pct=3.0,
            rsi_period=2,
            rsi_oversold=5.0,
            ma_period=200,
            ma_short_period=5
        )
        super().__init__(config)
        self.rsi_exit = 60.0

    def on_bar(
        self,
        symbol: str,
        bar: Bar,
        history: List[Bar],
        position_open: bool
    ) -> Optional[Signal]:
        """Process bar and generate signal."""
        # Need enough history for 200 MA
        if len(history) < self.config.ma_period + 1:
            return None

        closes = [b.close for b in history]

        # Calculate indicators
        rsi = Indicators.rsi(closes, self.config.rsi_period)
        ma_200 = Indicators.sma(closes, self.config.ma_period)
        ma_5 = Indicators.sma(closes, self.config.ma_short_period)

        if rsi is None or ma_200 is None or ma_5 is None:
            return None

        current_close = closes[-1]

        # If we have a position, check exit
        if position_open:
            # Exit: RSI > 60 OR Close > 5 MA
            if rsi > self.rsi_exit or current_close > ma_5:
                return self._create_exit_signal(
                    symbol, bar,
                    reason=f"RSI={rsi:.1f}" if rsi > self.rsi_exit else "Close > 5MA"
                )
            return None

        # Entry: RSI(2) < 5 AND Close > 200 MA (uptrend filter)
        if rsi < self.config.rsi_oversold and current_close > ma_200:
            return self._create_entry_signal(
                symbol, bar,
                strength=self.config.rsi_oversold - rsi,  # Lower RSI = stronger signal
                reason=f"RSI(2)={rsi:.1f}, above 200MA"
            )

        return None
