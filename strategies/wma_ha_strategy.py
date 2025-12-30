"""
WMA(20) + Heikin Ashi Strategy

Win Rate: 83%
Timeframe: Intraday (same-day entry and exit)

Entry Conditions (All Required):
- Heikin Ashi close crosses ABOVE WMA(20)
- Last 2 HA candles are GREEN
- Last 2 HA candles are "flat-bottomed" (no lower wick)

Exit Conditions (First Triggered):
- Heikin Ashi close crosses BELOW WMA(20)
- Color change (green -> red Heikin Ashi)
- Lower wick appears on HA candle
- EOD: 3:45 PM ET forced exit
"""

from typing import Dict, List, Optional
from datetime import datetime, time as dt_time
import logging

from .base_strategy import BaseStrategy, EntrySignal, ExitSignal
from data.intraday_indicators import IntradayIndicators

logger = logging.getLogger(__name__)


class WMAHAStrategy(BaseStrategy):
    """
    WMA(20) + Heikin Ashi Trend Following Strategy

    Uses Heikin Ashi candles with WMA(20) crossover for trend entries.
    Flat-bottomed green HA candles confirm strong upward momentum.
    83% win rate (backtested on 5-minute charts).
    """

    # Strategy-specific constants
    WMA_PERIOD = 20
    REQUIRED_GREEN_CANDLES = 2
    MARKET_OPEN = dt_time(9, 30)

    def __init__(
        self,
        indicators: IntradayIndicators,
        max_positions: int = 5,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(15, 45),  # 3:45 PM
        min_price: float = 5.0,
        wma_period: int = 20,
    ):
        """
        Initialize WMA+HA Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            max_positions: Maximum simultaneous positions (default 5)
            position_size_pct: Position size as % of equity (default 10%)
            risk_per_trade_pct: Max risk per trade (default 2%)
            eod_exit_time: Force exit time (default 3:45 PM)
            min_price: Minimum stock price (default $5)
            wma_period: WMA period (default 20)
        """
        super().__init__(
            name="WMA20_HA",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.wma_period = wma_period

    def is_trading_time(self) -> bool:
        """Check if we're in the valid trading window"""
        now = datetime.now().time()
        # Allow entries from 9:35 AM (after first few candles) until EOD
        return now >= dt_time(9, 35) and now < self.eod_exit_time

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets WMA+HA entry criteria.

        Entry Conditions:
        1. HA close crossed above WMA(20)
        2. Last 2 HA candles are green
        3. Last 2 HA candles are flat-bottomed

        Returns:
            EntrySignal if all conditions met, None otherwise
        """
        now = datetime.now()

        # Time check
        if not self.is_trading_time():
            return None

        # Get bars for calculations
        bars = self.indicators.get_latest_bars(symbol, 50)
        if len(bars) < 25:
            return None

        current_price = bars[-1]['close']
        if current_price < self.min_price:
            return None

        # Calculate WMA(20)
        prices = [b['close'] for b in bars]
        wma_values = self.indicators.calculate_wma(prices, self.wma_period)

        if len(wma_values) < 3:
            return None

        current_wma = wma_values[-1]
        prev_wma = wma_values[-2]

        if current_wma is None or prev_wma is None:
            return None

        # Calculate Heikin Ashi
        ha_candles = self.indicators.calculate_heikin_ashi(bars)
        if len(ha_candles) < 3:
            return None

        ha_current = ha_candles[-1]
        ha_prev = ha_candles[-2]
        ha_prev2 = ha_candles[-3]

        # Condition 1: Last 2 HA candles must be green
        if not (self.indicators.is_green_ha(ha_current) and
                self.indicators.is_green_ha(ha_prev)):
            return None

        # Condition 2: Last 2 HA candles must be flat-bottomed
        if not (self.indicators.is_flat_bottom_ha(ha_current) and
                self.indicators.is_flat_bottom_ha(ha_prev)):
            return None

        # Condition 3: HA close crossed above WMA(20)
        # Current: HA close > WMA
        if ha_current['ha_close'] <= current_wma:
            return None

        # Crossover check: previous HA close was at or below WMA (fresh crossover)
        if ha_prev2['ha_close'] > wma_values[-3] if wma_values[-3] else False:
            return None  # Already above, not a fresh crossover

        return EntrySignal(
            symbol=symbol,
            price=current_price,
            target=None,  # WMA+HA uses signal-based exits, not fixed targets
            stop=None,    # No fixed stop, exit on signal
            reason="WMA(20) + HA crossover with 2 green flat-bottom candles",
            metadata={
                'wma20': current_wma,
                'ha_close': ha_current['ha_close'],
                'consecutive_green': 2,
                'flat_bottom': True,
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions:
        1. HA close < WMA(20)
        2. HA color changed to red
        3. Lower wick appeared on HA candle
        4. Time >= 3:45 PM ET

        Args:
            position: Dict with keys: entry_price, shares, entry_time

        Returns:
            ExitSignal if exit condition met, None otherwise
        """
        now = datetime.now()

        # Get bars for calculations
        bars = self.indicators.get_latest_bars(symbol, 50)
        if len(bars) < 25:
            return None

        current_price = bars[-1]['close']
        entry_price = position.get('entry_price', 0)
        pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

        # Condition 1: EOD exit time
        if now.time() >= self.eod_exit_time:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={'eod_time': str(self.eod_exit_time)}
            )

        # Calculate WMA(20)
        prices = [b['close'] for b in bars]
        wma_values = self.indicators.calculate_wma(prices, self.wma_period)
        current_wma = wma_values[-1] if wma_values else None

        if current_wma is None:
            return None

        # Calculate Heikin Ashi
        ha_candles = self.indicators.calculate_heikin_ashi(bars)
        if not ha_candles:
            return None

        ha_current = ha_candles[-1]

        # Condition 2: HA close < WMA(20)
        if ha_current['ha_close'] < current_wma:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='signal',
                pnl_pct=pnl_pct,
                metadata={'reason': 'HA close below WMA(20)', 'wma20': current_wma}
            )

        # Condition 3: HA color changed to red
        if self.indicators.is_red_ha(ha_current):
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='signal',
                pnl_pct=pnl_pct,
                metadata={'reason': 'HA color changed to red'}
            )

        # Condition 4: Lower wick appeared (no longer flat-bottomed)
        if not self.indicators.is_flat_bottom_ha(ha_current):
            # Only exit if we previously had flat-bottom candles
            # Check if previous candle was flat-bottom (momentum fading)
            if len(ha_candles) >= 2:
                ha_prev = ha_candles[-2]
                if self.indicators.is_flat_bottom_ha(ha_prev):
                    return ExitSignal(
                        symbol=symbol,
                        price=current_price,
                        reason='signal',
                        pnl_pct=pnl_pct,
                        metadata={'reason': 'Lower wick appeared (momentum fading)'}
                    )

        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen all symbols for WMA+HA entry candidates.

        Uses the bulk screening query from IntradayIndicators for efficiency.

        Returns:
            List of EntrySignal objects
        """
        now = datetime.now()

        if not self.is_trading_time():
            logger.info(f"[WMA20_HA] Outside trading window")
            return []

        # Use bulk screening
        raw_candidates = self.indicators.get_wma_ha_candidates(
            min_price=self.min_price,
            max_candidates=self.max_positions * 3,
        )

        # Convert to EntrySignal objects
        signals = []
        for candidate in raw_candidates:
            signals.append(EntrySignal(
                symbol=candidate['symbol'],
                price=candidate['price'],
                target=None,
                stop=None,
                reason="WMA(20) + HA crossover",
                metadata={
                    'wma20': candidate['wma20'],
                    'ha_close': candidate['ha_close'],
                    'consecutive_green': candidate['consecutive_green'],
                    'flat_bottom': candidate['flat_bottom'],
                }
            ))

        logger.info(f"[WMA20_HA] Found {len(signals)} entry candidates")
        return signals

    def __repr__(self) -> str:
        return (f"WMAHAStrategy(wma_period={self.wma_period}, "
                f"max_pos={self.max_positions}, eod={self.eod_exit_time})")
