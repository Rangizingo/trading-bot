"""
HMA + Heikin Ashi Strategy

Win Rate: 77%
Timeframe: Intraday (same-day entry and exit)

Entry Conditions (All Required):
- Heikin Ashi close crosses ABOVE Hull Moving Average (HMA)
- Current HA candle is GREEN

Exit Conditions (require 2-candle confirmation except stops):
- HA close BELOW HMA for 2 consecutive candles
- 2 consecutive RED Heikin Ashi candles
- Stop loss at -3% (immediate)
- EOD: 3:45 PM ET forced exit (immediate)

HMA Formula:
HMA = WMA(2 * WMA(n/2) - WMA(n), sqrt(n))
Default period = 9
"""

from typing import Dict, List, Optional
from datetime import datetime, time as dt_time
import logging

from .base_strategy import BaseStrategy, EntrySignal, ExitSignal
from data.intraday_indicators import IntradayIndicators

logger = logging.getLogger(__name__)


class HMAHAStrategy(BaseStrategy):
    """
    HMA + Heikin Ashi Momentum Strategy

    Uses Hull Moving Average with Heikin Ashi candles for momentum entries.
    HMA responds faster to price changes than traditional MAs.
    77% win rate with 1.98:1 reward/risk ratio (backtested on 5-minute charts).
    """

    # Strategy-specific constants
    DEFAULT_HMA_PERIOD = 9
    MARKET_OPEN = dt_time(9, 30)

    def __init__(
        self,
        indicators: IntradayIndicators,
        max_positions: int = 5,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(15, 45),  # 3:45 PM
        min_price: float = 5.0,
        hma_period: int = 9,
    ):
        """
        Initialize HMA+HA Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            max_positions: Maximum simultaneous positions (default 5)
            position_size_pct: Position size as % of equity (default 10%)
            risk_per_trade_pct: Max risk per trade (default 2%)
            eod_exit_time: Force exit time (default 3:45 PM)
            min_price: Minimum stock price (default $5)
            hma_period: HMA period (default 9)
        """
        super().__init__(
            name="HMA_HA",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.hma_period = hma_period

    def is_trading_time(self) -> bool:
        """Check if we're in the valid trading window"""
        now = datetime.now().time()
        # Allow entries from 9:35 AM (after first few candles) until EOD
        return now >= dt_time(9, 35) and now < self.eod_exit_time

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets HMA+HA entry criteria.

        Entry Conditions:
        1. HA close crossed above HMA
        2. Current HA candle is green

        Returns:
            EntrySignal if all conditions met, None otherwise
        """
        now = datetime.now()

        # Time check
        if not self.is_trading_time():
            return None

        # Get bars for calculations
        bars = self.indicators.get_latest_bars(symbol, 50)
        if len(bars) < 20:
            return None

        current_price = bars[-1]['close']
        if current_price < self.min_price:
            return None

        # Calculate HMA
        prices = [b['close'] for b in bars]
        hma_values = self.indicators.calculate_hma(prices, self.hma_period)

        if len(hma_values) < 3:
            return None

        current_hma = hma_values[-1]
        prev_hma = hma_values[-2]

        if current_hma is None or prev_hma is None:
            return None

        # Calculate Heikin Ashi
        ha_candles = self.indicators.calculate_heikin_ashi(bars)
        if len(ha_candles) < 3:
            return None

        ha_current = ha_candles[-1]
        ha_prev = ha_candles[-2]

        # Condition 1: Current HA must be green
        if not self.indicators.is_green_ha(ha_current):
            return None

        # Condition 2: HA close crossed above HMA
        # Current: HA close > HMA
        if ha_current['ha_close'] <= current_hma:
            return None

        # Crossover check: previous HA close was at or below HMA
        if ha_prev['ha_close'] > prev_hma:
            return None  # Already above, not a fresh crossover

        return EntrySignal(
            symbol=symbol,
            price=current_price,
            target=None,  # HMA+HA uses signal-based exits
            stop=None,    # No fixed stop, exit on signal
            reason="HMA + HA crossover with green confirmation",
            metadata={
                'hma': current_hma,
                'ha_close': ha_current['ha_close'],
                'is_green': True,
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions (require 2 consecutive candle confirmation):
        1. HA close < HMA for 2 candles
        2. 2 consecutive red HA candles
        3. Time >= 3:45 PM ET (immediate)
        4. Stop loss at -3% (immediate)

        Args:
            position: Dict with keys: entry_price, shares, entry_time

        Returns:
            ExitSignal if exit condition met, None otherwise
        """
        now = datetime.now()

        # Get bars for calculations
        bars = self.indicators.get_latest_bars(symbol, 50)
        if len(bars) < 20:
            return None

        current_price = bars[-1]['close']
        entry_price = position.get('entry_price', 0)
        pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

        # Condition 1: EOD exit time (immediate)
        if now.time() >= self.eod_exit_time:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={'eod_time': str(self.eod_exit_time)}
            )

        # Condition 2: Stop loss at -3% (immediate)
        if pnl_pct <= -3.0:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='stop',
                pnl_pct=pnl_pct,
                metadata={'reason': 'Stop loss triggered at -3%'}
            )

        # Calculate HMA
        prices = [b['close'] for b in bars]
        hma_values = self.indicators.calculate_hma(prices, self.hma_period)

        if len(hma_values) < 2:
            return None

        current_hma = hma_values[-1]
        prev_hma = hma_values[-2]

        if current_hma is None or prev_hma is None:
            return None

        # Calculate Heikin Ashi
        ha_candles = self.indicators.calculate_heikin_ashi(bars)
        if len(ha_candles) < 2:
            return None

        ha_current = ha_candles[-1]
        ha_prev = ha_candles[-2]

        # Condition 3: HA close < HMA for 2 consecutive candles
        if (ha_current['ha_close'] < current_hma and
            ha_prev['ha_close'] < prev_hma):
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='signal',
                pnl_pct=pnl_pct,
                metadata={'reason': 'HA close below HMA for 2 candles', 'hma': current_hma}
            )

        # Condition 4: 2 consecutive red HA candles
        if (self.indicators.is_red_ha(ha_current) and
            self.indicators.is_red_ha(ha_prev)):
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='signal',
                pnl_pct=pnl_pct,
                metadata={'reason': '2 consecutive red HA candles'}
            )

        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen all symbols for HMA+HA entry candidates.

        Uses the bulk screening query from IntradayIndicators for efficiency.

        Returns:
            List of EntrySignal objects
        """
        now = datetime.now()

        if not self.is_trading_time():
            logger.info(f"[HMA_HA] Outside trading window")
            return []

        # Use bulk screening
        raw_candidates = self.indicators.get_hma_ha_candidates(
            min_price=self.min_price,
            hma_period=self.hma_period,
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
                reason="HMA + HA crossover",
                metadata={
                    'hma': candidate['hma'],
                    'ha_close': candidate['ha_close'],
                    'is_green': candidate['is_green'],
                }
            ))

        logger.info(f"[HMA_HA] Found {len(signals)} entry candidates")
        return signals

    def __repr__(self) -> str:
        return (f"HMAHAStrategy(hma_period={self.hma_period}, "
                f"max_pos={self.max_positions}, eod={self.eod_exit_time})")
