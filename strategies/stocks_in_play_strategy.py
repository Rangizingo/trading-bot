"""
ORB Stocks in Play Strategy

Sharpe Ratio: 2.81
Win Rate: 17-42% (low win rate, high reward/risk)
Total Return: 1,600% over 8 years (top 20 stocks)
Source: SSRN Academic Paper #4729284 (Zarattini, Barbon, Aziz)

Strategy Concept:
- Focus on "Stocks in Play" - high relative volume stocks with momentum
- Trade the first 5-minute candle direction
- Use ATR-based stops for tight risk control

Pre-Market Screening ("Stocks in Play"):
- Price > $5
- Average Volume > 1 million shares (20-day)
- ATR > $0.50 (14-day)
- Ranked by relative volume (top 20)

Entry Conditions:
- Time: 9:35 AM ET (after first 5-min candle)
- LONG: First 5-min candle is bullish (close > open)
- SHORT: First 5-min candle is bearish (close < open)
- NO TRADE: First candle is doji (close ~ open)

Exit Conditions:
- Stop: 10% of 14-day ATR from entry
- EOD: 4:00 PM ET (market close)
- No target (let winners run)

Key Notes:
- Low win rate (17-42%) is EXPECTED
- Profitability comes from risk/reward ratio
- Strategy only works on "Stocks in Play" (not all stocks)
"""

from typing import Dict, List, Optional
from datetime import datetime, time as dt_time
import logging

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .base_strategy import BaseStrategy, EntrySignal, ExitSignal
from data.intraday_indicators import IntradayIndicators
from data.historical_data import HistoricalData

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET = ZoneInfo('America/New_York')


class StocksInPlayStrategy(BaseStrategy):
    """
    ORB on Stocks in Play Strategy.

    Trade the first 5-minute candle direction on high-volume stocks.
    Use ATR-based stops. Supports both long and short positions.
    """

    # Strategy-specific constants
    MARKET_OPEN = dt_time(9, 30)
    ENTRY_WINDOW_START = dt_time(9, 35)  # After first 5-min candle
    ENTRY_WINDOW_END = dt_time(9, 40)    # 5-minute window for entries
    MARKET_CLOSE = dt_time(16, 0)
    ATR_STOP_MULTIPLIER = 0.10  # 10% of ATR

    def __init__(
        self,
        indicators: IntradayIndicators,
        historical_data: Optional[HistoricalData] = None,
        max_positions: int = 5,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(16, 0),
        min_price: float = 5.0,
        min_avg_volume: int = 1_000_000,
        min_atr: float = 0.50,
        atr_stop_pct: float = 0.10,
        top_n_stocks: int = 20,
    ):
        """
        Initialize Stocks in Play Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            historical_data: HistoricalData instance for ATR/volume (optional)
            max_positions: Maximum positions (default 5)
            position_size_pct: Position size as % of equity (default 10%)
            risk_per_trade_pct: Max risk per trade (default 2%)
            eod_exit_time: Force exit time (default 4:00 PM)
            min_price: Minimum stock price (default $5)
            min_avg_volume: Minimum 20-day average volume (default 1M)
            min_atr: Minimum 14-day ATR (default $0.50)
            atr_stop_pct: Stop distance as % of ATR (default 10%)
            top_n_stocks: Number of stocks to screen (default 20)
        """
        super().__init__(
            name="STOCKS_IN_PLAY",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.historical_data = historical_data
        self.min_avg_volume = min_avg_volume
        self.min_atr = min_atr
        self.atr_stop_pct = atr_stop_pct
        self.top_n_stocks = top_n_stocks

        # Cache stocks in play for the day
        self._cached_stocks_in_play: List[Dict] = []
        self._cache_date: Optional[datetime] = None

    def _get_current_et(self) -> datetime:
        """Get current time in Eastern Time."""
        return datetime.now(ET)

    def _is_entry_window(self) -> bool:
        """Check if we're in the entry window (9:35-9:40 AM ET)"""
        now_et = self._get_current_et().time()
        return now_et >= self.ENTRY_WINDOW_START and now_et < self.ENTRY_WINDOW_END

    def is_trading_time(self) -> bool:
        """
        Check if we're in the valid trading window.

        For this strategy, entries only happen 9:35-9:40 AM.
        """
        return self._is_entry_window()

    def _refresh_stocks_in_play(self) -> List[Dict]:
        """
        Refresh the stocks in play list for today.

        Returns cached list if same day.
        """
        now_et = self._get_current_et()
        today = now_et.date()

        # Return cached if same day
        if self._cache_date and self._cache_date.date() == today and self._cached_stocks_in_play:
            return self._cached_stocks_in_play

        # Get stocks in play with first candle analysis
        stocks_in_play = self.indicators.get_stocks_in_play_with_candles(
            top_n=self.top_n_stocks,
            min_price=self.min_price,
            for_date=now_et
        )

        # If historical_data available, filter by ATR and volume
        if self.historical_data and stocks_in_play:
            filtered = []
            for stock in stocks_in_play:
                try:
                    atr = self.historical_data.get_atr(stock['symbol'], period=14)
                    avg_vol = self.historical_data.get_average_volume(stock['symbol'], period=20)

                    if atr is not None and atr < self.min_atr:
                        continue
                    if avg_vol is not None and avg_vol < self.min_avg_volume:
                        continue

                    stock['atr'] = atr
                    stock['avg_volume'] = avg_vol
                    filtered.append(stock)

                except Exception as e:
                    logger.debug(f"Error getting historical data for {stock['symbol']}: {e}")
                    filtered.append(stock)  # Include without ATR filtering

            stocks_in_play = filtered

        self._cached_stocks_in_play = stocks_in_play
        self._cache_date = now_et

        logger.info(f"[STOCKS_IN_PLAY] Cached {len(stocks_in_play)} stocks in play")
        return stocks_in_play

    def _calculate_stop(self, entry_price: float, direction: str, atr: Optional[float]) -> float:
        """
        Calculate stop price based on ATR.

        Stop = entry +/- (ATR * 0.10)
        """
        if atr is None:
            # Fallback: use 1% of entry price if no ATR
            atr = entry_price * 0.01

        stop_distance = atr * self.atr_stop_pct

        if direction == 'long':
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets entry criteria.

        Entry Conditions:
        1. Time is 9:35-9:40 AM (entry window)
        2. Symbol is in Stocks in Play list
        3. First 5-min candle is bullish (long) or bearish (short)
        4. Not a doji candle

        Returns:
            EntrySignal if conditions met, None otherwise
        """
        # Time check
        if not self._is_entry_window():
            return None

        # Get stocks in play
        stocks_in_play = self._refresh_stocks_in_play()

        # Find this symbol in the list
        stock_data = None
        for stock in stocks_in_play:
            if stock['symbol'] == symbol:
                stock_data = stock
                break

        if not stock_data:
            return None

        first_candle = stock_data.get('first_candle')
        if not first_candle:
            return None

        # Skip doji candles (no clear direction)
        if first_candle.get('is_doji', True):
            return None

        direction = stock_data.get('direction', 'long')
        entry_price = first_candle['close']
        atr = stock_data.get('atr')

        # Calculate stop
        stop = self._calculate_stop(entry_price, direction, atr)

        return EntrySignal(
            symbol=symbol,
            price=entry_price,
            target=None,  # No target - let winners run
            stop=stop,
            reason=f"Stocks in Play: First candle {direction} (rel_vol={stock_data.get('relative_volume', 0):.1f}x)",
            metadata={
                'direction': direction,
                'relative_volume': stock_data.get('relative_volume'),
                'atr': atr,
                'first_candle_open': first_candle['open'],
                'first_candle_close': first_candle['close'],
                'first_candle_range': first_candle.get('range_size'),
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions:
        1. Price hits stop (10% of ATR from entry)
        2. Time >= 4:00 PM ET (EOD)

        Args:
            position: Dict with keys: entry_price, shares, entry_time, stop, direction

        Returns:
            ExitSignal if exit condition met, None otherwise
        """
        now_et = self._get_current_et()

        # Get current price
        bars = self.indicators.get_latest_bars(symbol, 5)
        if not bars:
            return None

        current_price = bars[-1]['close']
        entry_price = position.get('entry_price', 0)
        direction = position.get('direction', 'long')

        # Calculate P&L based on direction
        if direction == 'long':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100 if entry_price > 0 else 0

        # Condition 1: EOD exit time
        if now_et.time() >= self.eod_exit_time:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={'eod_time': str(self.eod_exit_time), 'direction': direction}
            )

        # Condition 2: Stop hit
        stop = position.get('stop')
        if stop:
            if direction == 'long' and current_price <= stop:
                return ExitSignal(
                    symbol=symbol,
                    price=current_price,
                    reason='stop',
                    pnl_pct=pnl_pct,
                    metadata={'stop': stop, 'direction': direction}
                )
            elif direction == 'short' and current_price >= stop:
                return ExitSignal(
                    symbol=symbol,
                    price=current_price,
                    reason='stop',
                    pnl_pct=pnl_pct,
                    metadata={'stop': stop, 'direction': direction}
                )

        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Get entry candidates from Stocks in Play with first candle signals.

        Only returns candidates during the entry window (9:35-9:40 AM).

        Returns:
            List of EntrySignal objects
        """
        now_et = self._get_current_et()

        # Only return candidates during entry window
        if not self._is_entry_window():
            if now_et.time() > self.ENTRY_WINDOW_END:
                logger.debug(f"[STOCKS_IN_PLAY] Past entry window (ends 9:40 AM)")
            else:
                logger.debug(f"[STOCKS_IN_PLAY] Before entry window (starts 9:35 AM)")
            return []

        # Get stocks in play with candle analysis
        stocks_in_play = self._refresh_stocks_in_play()

        if not stocks_in_play:
            logger.warning("[STOCKS_IN_PLAY] No stocks in play found")
            return []

        # Convert to EntrySignals
        candidates = []
        for stock in stocks_in_play:
            first_candle = stock.get('first_candle')
            if not first_candle:
                continue

            # Skip doji
            if first_candle.get('is_doji', True):
                continue

            direction = stock.get('direction', 'long')
            entry_price = first_candle['close']
            atr = stock.get('atr')
            stop = self._calculate_stop(entry_price, direction, atr)

            signal = EntrySignal(
                symbol=stock['symbol'],
                price=entry_price,
                target=None,
                stop=stop,
                reason=f"Stocks in Play: {direction} (rel_vol={stock.get('relative_volume', 0):.1f}x)",
                metadata={
                    'direction': direction,
                    'relative_volume': stock.get('relative_volume'),
                    'atr': atr,
                    'stop': stop,
                }
            )
            candidates.append(signal)

            if len(candidates) >= self.max_positions:
                break

        logger.info(f"[STOCKS_IN_PLAY] Found {len(candidates)} entry candidates")
        return candidates

    def clear_cache(self) -> None:
        """Clear the cached stocks in play (useful for testing)"""
        self._cached_stocks_in_play = []
        self._cache_date = None

    def __repr__(self) -> str:
        return (f"StocksInPlayStrategy(top_n={self.top_n_stocks}, "
                f"entry_window=9:35-9:40, atr_stop={self.atr_stop_pct:.0%}, "
                f"max_pos={self.max_positions}, eod={self.eod_exit_time})")
