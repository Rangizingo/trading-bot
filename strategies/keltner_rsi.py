"""Keltner Channel + RSI mean reversion strategy."""
from typing import List, Optional
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar, Signal, Action
from strategies.base import BaseStrategy, StrategyConfig
from core.indicators import Indicators


class KeltnerRSIStrategy(BaseStrategy):
    """Keltner Channel + RSI mean reversion strategy.

    Entry: Price < Lower KC AND RSI < 30
    Exit: Price > Middle KC (EMA) OR RSI > 50
    Stop: 2%
    """

    def __init__(self):
        config = StrategyConfig(
            name="Keltner_RSI",
            stop_loss_pct=2.0,
            rsi_period=14,
            rsi_oversold=30.0
        )
        super().__init__(config)
        self.kc_period = 20
        self.kc_multiplier = 2.0
        self.rsi_exit = 50.0

    def on_bar(
        self,
        symbol: str,
        bar: Bar,
        history: List[Bar],
        position_open: bool
    ) -> Optional[Signal]:
        """Process bar and generate signal."""
        min_bars = max(self.kc_period, self.config.rsi_period) + 1
        if len(history) < min_bars:
            return None

        closes = [b.close for b in history]
        highs = [b.high for b in history]
        lows = [b.low for b in history]

        # Calculate indicators
        rsi = Indicators.rsi(closes, self.config.rsi_period)
        kc = Indicators.keltner_channels(
            closes, highs, lows,
            self.kc_period, self.kc_multiplier
        )

        if rsi is None or kc is None:
            return None

        current_close = closes[-1]

        # If we have a position, check exit
        if position_open:
            # Exit: Price > Middle KC (EMA) OR RSI > 50
            if current_close > kc.middle or rsi > self.rsi_exit:
                return self._create_exit_signal(
                    symbol, bar,
                    reason=f"Price>EMA" if current_close > kc.middle else f"RSI={rsi:.1f}"
                )
            return None

        # Entry: Price < Lower KC AND RSI < 30
        if current_close < kc.lower and rsi < self.config.rsi_oversold:
            return self._create_entry_signal(
                symbol, bar,
                strength=self.config.rsi_oversold - rsi,
                reason=f"RSI={rsi:.1f}, below lower KC"
            )

        return None
