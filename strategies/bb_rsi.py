"""Bollinger Band + RSI mean reversion strategy."""
from typing import List, Optional
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar, Signal, Action
from strategies.base import BaseStrategy, StrategyConfig
from core.indicators import Indicators


class BollingerRSIStrategy(BaseStrategy):
    """Bollinger Band + RSI mean reversion strategy.

    Entry: Price < Lower BB AND RSI < 30
    Exit: Price > Middle BB OR RSI > 50
    Stop: 2% (FIXED: simple percentage, no complex calculation)
    """

    def __init__(self):
        config = StrategyConfig(
            name="BB_RSI",
            stop_loss_pct=2.0,  # Simple percentage stop
            rsi_period=14,
            rsi_oversold=30.0
        )
        super().__init__(config)
        self.bb_period = 20
        self.bb_std = 2.0
        self.rsi_exit = 50.0

    def on_bar(
        self,
        symbol: str,
        bar: Bar,
        history: List[Bar],
        position_open: bool
    ) -> Optional[Signal]:
        """Process bar and generate signal."""
        min_bars = max(self.bb_period, self.config.rsi_period) + 1
        if len(history) < min_bars:
            return None

        closes = [b.close for b in history]

        # Calculate indicators
        rsi = Indicators.rsi(closes, self.config.rsi_period)
        bb = Indicators.bollinger_bands(closes, self.bb_period, self.bb_std)

        if rsi is None or bb is None:
            return None

        current_close = closes[-1]

        # If we have a position, check exit
        if position_open:
            # Exit: Price > Middle BB OR RSI > 50
            if current_close > bb.middle or rsi > self.rsi_exit:
                return self._create_exit_signal(
                    symbol, bar,
                    reason=f"Price>MidBB" if current_close > bb.middle else f"RSI={rsi:.1f}"
                )
            return None

        # Entry: Price < Lower BB AND RSI < 30
        if current_close < bb.lower and rsi < self.config.rsi_oversold:
            # FIXED: Use simple percentage stop from config
            stop_loss = current_close * (1 - self.config.stop_loss_pct / 100)

            return self._create_entry_signal(
                symbol, bar,
                stop_loss=stop_loss,
                strength=self.config.rsi_oversold - rsi,
                reason=f"RSI={rsi:.1f}, below lower BB"
            )

        return None
