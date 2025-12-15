"""VWAP + RSI mean reversion strategy."""
from typing import List, Optional
from datetime import date
import sys
sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')
from data.models import Bar, Signal, Action
from strategies.base import BaseStrategy, StrategyConfig
from core.indicators import Indicators


class VWAPRSIStrategy(BaseStrategy):
    """VWAP + RSI mean reversion strategy.

    Entry: Price < VWAP AND RSI < 35
    Exit: Price > VWAP OR RSI > 55
    Stop: 1.5%

    CRITICAL FIX: Resets VWAP at each new trading day.
    """

    def __init__(self):
        config = StrategyConfig(
            name="VWAP_RSI",
            stop_loss_pct=1.5,
            rsi_period=14,
            rsi_oversold=35.0,
            rsi_overbought=55.0
        )
        super().__init__(config)

    def _calculate_daily_vwap(self, symbol: str, history: List[Bar]) -> Optional[float]:
        """Calculate VWAP for current day only.

        FIXED: Resets VWAP at each new trading day.
        """
        if not history:
            return None

        current_bar = history[-1]
        current_date = current_bar.timestamp.date()

        # Get only bars from today
        today_bars = [b for b in history if b.timestamp.date() == current_date]

        if not today_bars:
            return None

        highs = [b.high for b in today_bars]
        lows = [b.low for b in today_bars]
        closes = [b.close for b in today_bars]
        volumes = [b.volume for b in today_bars]

        return Indicators.vwap(highs, lows, closes, volumes)

    def on_bar(
        self,
        symbol: str,
        bar: Bar,
        history: List[Bar],
        position_open: bool
    ) -> Optional[Signal]:
        """Process bar and generate signal."""
        if len(history) < self.config.rsi_period + 1:
            return None

        closes = [b.close for b in history]

        # Calculate indicators
        rsi = Indicators.rsi(closes, self.config.rsi_period)
        vwap = self._calculate_daily_vwap(symbol, history)

        if rsi is None or vwap is None:
            return None

        current_close = closes[-1]

        # If we have a position, check exit
        if position_open:
            # Exit: Price > VWAP OR RSI > 55
            if current_close > vwap or rsi > self.config.rsi_overbought:
                return self._create_exit_signal(
                    symbol, bar,
                    reason=f"Price>VWAP" if current_close > vwap else f"RSI={rsi:.1f}"
                )
            return None

        # Entry: Price < VWAP AND RSI < 35
        if current_close < vwap and rsi < self.config.rsi_oversold:
            return self._create_entry_signal(
                symbol, bar,
                strength=(vwap - current_close) / vwap * 100,  # % below VWAP
                reason=f"RSI={rsi:.1f}, {((vwap-current_close)/vwap*100):.1f}% below VWAP"
            )

        return None
