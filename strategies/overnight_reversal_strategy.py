"""
Overnight-Intraday Reversal Strategy

Sharpe Ratio: 4.44 (up to 9.0+ on financial ETFs)
Source: SSRN Academic Paper #2730304 (Liu, Liu, Wang, Zhou, Zhu)

Strategy Concept:
- Exploit mean reversion: stocks that gap down overnight tend to recover during the day
- Buy the biggest overnight LOSERS at market open
- Sell all positions at market close
- NO stops, NO targets - pure time-based exits

Entry Conditions:
- Time: Market open (9:30-9:35 AM ET window)
- Signal: Buy bottom decile of overnight returns (biggest losers)
- Overnight return = (Open - Previous Close) / Previous Close

Exit Conditions:
- Time Exit: 4:00 PM ET (market close)
- NO stop loss (per strategy specification)
- NO target (per strategy specification)

Risk Management:
- Max 10 positions (spread across bottom decile)
- 10% of equity per position
- Daily portfolio turnover: 100%

Why "Overnight" is Confusing:
- "Overnight" refers to the SIGNAL (overnight returns used to select stocks)
- "Intraday" refers to the HOLDING PERIOD (hold only during the day)
- You are NEVER holding overnight - this is 100% intraday
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

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET = ZoneInfo('America/New_York')


class OvernightReversalStrategy(BaseStrategy):
    """
    Overnight-Intraday Reversal Strategy.

    Buy stocks with worst overnight returns at market open.
    Sell all positions at market close. No stops, no targets.
    """

    # Strategy-specific constants
    MARKET_OPEN = dt_time(9, 30)
    ENTRY_WINDOW_END = dt_time(9, 35)  # 5-minute window for entries
    MARKET_CLOSE = dt_time(16, 0)  # 4:00 PM ET

    def __init__(
        self,
        indicators: IntradayIndicators,
        max_positions: int = 10,
        position_size_pct: float = 0.10,
        risk_per_trade_pct: float = 0.10,  # Higher since no stops
        eod_exit_time: dt_time = dt_time(16, 0),
        min_price: float = 5.0,
    ):
        """
        Initialize Overnight Reversal Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            max_positions: Maximum positions (default 10 for diversification)
            position_size_pct: Position size as % of equity (default 10%)
            risk_per_trade_pct: Max risk per trade (default 10% - no stops)
            eod_exit_time: Force exit time (default 4:00 PM - market close)
            min_price: Minimum stock price (default $5)
        """
        super().__init__(
            name="OVERNIGHT_REVERSAL",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators

        # Cache bottom decile at market open
        self._cached_bottom_decile: List[Dict] = []
        self._cache_date: Optional[datetime] = None

    def _get_current_et(self) -> datetime:
        """Get current time in Eastern Time."""
        return datetime.now(ET)

    def _is_entry_window(self) -> bool:
        """Check if we're in the entry window (9:30-9:35 AM ET)"""
        now_et = self._get_current_et().time()
        return now_et >= self.MARKET_OPEN and now_et < self.ENTRY_WINDOW_END

    def is_trading_time(self) -> bool:
        """
        Check if we're in the valid trading window.

        For this strategy, entries only happen at market open.
        After 9:35 AM, no new entries are allowed.
        """
        return self._is_entry_window()

    def _get_bottom_decile(self) -> List[Dict]:
        """
        Get bottom decile of overnight returns (biggest losers).

        Caches result for the trading day to avoid recalculation.
        """
        now_et = self._get_current_et()
        today = now_et.date()

        # Return cached if same day
        if self._cache_date and self._cache_date.date() == today and self._cached_bottom_decile:
            return self._cached_bottom_decile

        # Calculate fresh deciles
        bottom_decile, _ = self.indicators.get_overnight_return_deciles(
            min_price=self.min_price
        )

        self._cached_bottom_decile = bottom_decile
        self._cache_date = now_et

        logger.info(f"[OVERNIGHT_REVERSAL] Cached {len(bottom_decile)} bottom decile stocks")
        return bottom_decile

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets entry criteria.

        Entry Conditions:
        1. Time is 9:30-9:35 AM (entry window)
        2. Symbol is in bottom decile of overnight returns

        Returns:
            EntrySignal if conditions met, None otherwise
        """
        # Time check - entries only at market open
        if not self._is_entry_window():
            return None

        # Get bottom decile
        bottom_decile = self._get_bottom_decile()

        # Check if symbol is in bottom decile
        stock_data = None
        for stock in bottom_decile:
            if stock['symbol'] == symbol:
                stock_data = stock
                break

        if not stock_data:
            return None

        overnight_return = stock_data['overnight_return']
        today_open = stock_data['today_open']

        return EntrySignal(
            symbol=symbol,
            price=today_open,
            target=None,  # No target - time-based exit only
            stop=None,    # No stop - per strategy spec
            reason=f"Overnight Reversal: Gap down {overnight_return:.2%}",
            metadata={
                'overnight_return': overnight_return,
                'prior_close': stock_data['prior_close'],
                'today_open': today_open,
                'strategy': 'overnight_reversal',
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions:
        1. Time >= 4:00 PM ET (market close) - ONLY exit condition

        NOTE: This strategy has NO stop loss and NO target.
        All risk is controlled by position size and same-day exit.

        Args:
            position: Dict with keys: entry_price, shares, entry_time

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
        pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

        # ONLY exit condition: EOD at market close
        if now_et.time() >= self.eod_exit_time:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={
                    'eod_time': str(self.eod_exit_time),
                    'strategy': 'overnight_reversal',
                    'note': 'No stops per strategy spec'
                }
            )

        # No other exit conditions - hold until close
        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Get entry candidates from bottom decile of overnight returns.

        Only returns candidates during the entry window (9:30-9:35 AM).

        Returns:
            List of EntrySignal objects for bottom decile stocks
        """
        now_et = self._get_current_et()

        # Only return candidates during entry window
        if not self._is_entry_window():
            if now_et.time() > self.ENTRY_WINDOW_END:
                logger.debug(f"[OVERNIGHT_REVERSAL] Past entry window (ends 9:35 AM)")
            else:
                logger.debug(f"[OVERNIGHT_REVERSAL] Before entry window (starts 9:30 AM)")
            return []

        # Get bottom decile
        bottom_decile = self._get_bottom_decile()

        if not bottom_decile:
            logger.warning("[OVERNIGHT_REVERSAL] No bottom decile stocks found")
            return []

        # Convert to EntrySignals
        candidates = []
        for stock in bottom_decile[:self.max_positions]:
            signal = EntrySignal(
                symbol=stock['symbol'],
                price=stock['today_open'],
                target=None,
                stop=None,
                reason=f"Overnight Reversal: Gap down {stock['overnight_return']:.2%}",
                metadata={
                    'overnight_return': stock['overnight_return'],
                    'prior_close': stock['prior_close'],
                    'today_open': stock['today_open'],
                }
            )
            candidates.append(signal)

        logger.info(f"[OVERNIGHT_REVERSAL] Found {len(candidates)} entry candidates (bottom decile)")
        return candidates

    def clear_cache(self) -> None:
        """Clear the cached bottom decile (useful for testing)"""
        self._cached_bottom_decile = []
        self._cache_date = None

    def __repr__(self) -> str:
        return (f"OvernightReversalStrategy(max_pos={self.max_positions}, "
                f"entry_window=9:30-9:35, eod={self.eod_exit_time}, "
                f"no_stops=True)")
