"""
Gap and Go Strategy (LONG ONLY)

Morning momentum strategy for stocks gapping up with high pre-market volume.
Entry: 9:30-10:00 AM ET
Exit: Target (2:1 R/R), Stop, or 10:00 AM forced

Direction: LONG ONLY (no shorting)

Strategy Rules:
- Universe: Stocks gapping UP > 4% with high pre-market volume
- Entry: Price breaks above pre-market high (or first 1-min candle high)
- Stop: Pre-market low (or first candle low)
- Target: 2:1 R/R based on stop distance
- Time Window: 9:30 AM - 10:00 AM ET only
"""

from typing import Dict, List, Optional, Set
from datetime import datetime, time as dt_time, date
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


class GapAndGoStrategy(BaseStrategy):
    """
    Gap and Go - Morning Momentum (LONG ONLY)

    Trades stocks gapping up with high pre-market volume.
    Entries only 9:30-10:00 AM, all positions closed by 10:00 AM.

    Key characteristics:
    - Very short holding period (max 30 minutes)
    - Capitalizes on morning momentum from gap-up stocks
    - Uses first candle high/low for entry trigger and stop
    - 2:1 reward-to-risk ratio
    """

    # Strategy-specific constants
    MARKET_OPEN = dt_time(9, 30)
    ENTRY_WINDOW_START = dt_time(9, 30)
    ENTRY_WINDOW_END = dt_time(10, 0)
    EOD_EXIT = dt_time(10, 0)
    MIN_GAP_PCT = 4.0  # Minimum 4% gap up
    MIN_PREMARKET_VOLUME = 100_000  # Minimum pre-market volume
    MIN_RELATIVE_VOLUME = 1.5  # Min relative volume vs average
    RR_RATIO = 2.0  # 2:1 reward to risk

    def __init__(
        self,
        indicators: IntradayIndicators,
        max_positions: int = 3,
        position_size_pct: float = 0.15,
        risk_per_trade_pct: float = 0.02,
        eod_exit_time: dt_time = dt_time(10, 0),
        min_price: float = 5.0,
        min_gap_pct: float = 4.0,
        rr_ratio: float = 2.0,
    ):
        """
        Initialize Gap and Go Strategy.

        Args:
            indicators: IntradayIndicators instance for data access
            max_positions: Maximum simultaneous positions (default 3)
            position_size_pct: Position size as % of equity (default 15%)
            risk_per_trade_pct: Max risk per trade (default 2%)
            eod_exit_time: Force exit time (default 10:00 AM)
            min_price: Minimum stock price (default $5)
            min_gap_pct: Minimum gap up percentage (default 4%)
            rr_ratio: Reward to risk ratio (default 2:1)
        """
        super().__init__(
            name="GAP_AND_GO",
            max_positions=max_positions,
            position_size_pct=position_size_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            eod_exit_time=eod_exit_time,
            min_price=min_price,
        )
        self.indicators = indicators
        self.min_gap_pct = min_gap_pct
        self.rr_ratio = rr_ratio

        # Track daily trades to enforce max 1 trade per symbol per day
        self._daily_trades: Dict[date, Set[str]] = {}

        # Cache for first candle data (computed once per day per symbol)
        self._first_candle_cache: Dict[str, Dict] = {}
        self._cache_date: Optional[date] = None

    def _get_current_et(self) -> datetime:
        """Get current time in Eastern Time."""
        return datetime.now(ET)

    def _get_traded_today(self) -> Set[str]:
        """Get set of symbols already traded today."""
        today = self._get_current_et().date()
        return self._daily_trades.get(today, set())

    def _mark_traded(self, symbol: str) -> None:
        """Mark a symbol as traded today."""
        today = self._get_current_et().date()
        if today not in self._daily_trades:
            self._daily_trades = {today: set()}  # Clear old dates
        self._daily_trades[today].add(symbol)

    def _clear_cache_if_new_day(self) -> None:
        """Clear first candle cache if it's a new day."""
        today = self._get_current_et().date()
        if self._cache_date != today:
            self._first_candle_cache = {}
            self._cache_date = today

    def is_entry_window(self) -> bool:
        """Check if we're in the entry window (9:30-10:00 AM ET)."""
        now_et = self._get_current_et().time()
        return self.ENTRY_WINDOW_START <= now_et < self.ENTRY_WINDOW_END

    def _get_overnight_gap(self, symbol: str) -> Optional[Dict]:
        """
        Calculate overnight gap for a symbol.

        Returns:
            Dict with gap_pct, prior_close, today_open, or None if data missing
        """
        now_et = self._get_current_et()

        # Get prior close
        prior_close = self.indicators.get_prior_close(symbol, now_et)
        if prior_close is None or prior_close <= 0:
            return None

        # Get today's open from first bar
        start_ts = self.indicators._et_to_timestamp(
            now_et.date(), self.indicators.MARKET_OPEN
        )
        end_ts = start_ts + 60  # First minute

        bars = self.indicators.get_bars(symbol, start_ts, end_ts)
        if not bars:
            return None

        today_open = bars[0]['open']
        if today_open is None or today_open <= 0:
            return None

        gap_pct = ((today_open - prior_close) / prior_close) * 100

        return {
            'symbol': symbol,
            'gap_pct': gap_pct,
            'prior_close': prior_close,
            'today_open': today_open,
        }

    def _get_first_candle(self, symbol: str) -> Optional[Dict]:
        """
        Get the first 1-minute candle of the day for breakout reference.

        Uses caching to avoid repeated calculations.

        Returns:
            Dict with open, high, low, close, volume
        """
        self._clear_cache_if_new_day()

        # Check cache first
        if symbol in self._first_candle_cache:
            return self._first_candle_cache[symbol]

        now_et = self._get_current_et()

        # Get first 1-minute bar (9:30 AM)
        start_ts = self.indicators._et_to_timestamp(
            now_et.date(), self.indicators.MARKET_OPEN
        )
        end_ts = start_ts + 60  # 1 minute

        bars = self.indicators.get_bars(symbol, start_ts, end_ts)
        if not bars:
            return None

        first_bar = bars[0]
        candle = {
            'symbol': symbol,
            'open': first_bar['open'],
            'high': first_bar['high'],
            'low': first_bar['low'],
            'close': first_bar['close'],
            'volume': first_bar['volume'],
        }

        # Cache it
        self._first_candle_cache[symbol] = candle
        return candle

    def _calculate_target_stop(
        self, entry_price: float, candle_low: float
    ) -> Dict[str, float]:
        """
        Calculate target and stop based on 2:1 R/R.

        Args:
            entry_price: Expected entry price (breakout level)
            candle_low: First candle low (stop level)

        Returns:
            Dict with target, stop, risk_per_share
        """
        risk_per_share = entry_price - candle_low
        target = entry_price + (risk_per_share * self.rr_ratio)

        return {
            'target': target,
            'stop': candle_low,
            'risk_per_share': risk_per_share,
        }

    def check_entry(self, symbol: str) -> Optional[EntrySignal]:
        """
        Check if symbol meets Gap and Go entry criteria.

        Entry Conditions:
        1. In entry window (9:30-10:00 AM ET)
        2. Stock is gapping up > min_gap_pct (default 4%)
        3. Price breaks above first candle high
        4. Symbol not already traded today
        5. Price > min_price

        Returns:
            EntrySignal if all conditions met, None otherwise
        """
        # Time check - must be in entry window
        if not self.is_entry_window():
            return None

        # Check if already traded today
        if symbol in self._get_traded_today():
            return None

        # Get current price
        bars = self.indicators.get_latest_bars(symbol, 5)
        if not bars:
            return None

        current_price = bars[-1]['close']

        # Price filter
        if current_price < self.min_price:
            return None

        # Check overnight gap
        gap_data = self._get_overnight_gap(symbol)
        if gap_data is None:
            return None

        # Must be gapping UP at least min_gap_pct
        if gap_data['gap_pct'] < self.min_gap_pct:
            return None

        # Get first candle for breakout level and stop
        first_candle = self._get_first_candle(symbol)
        if first_candle is None:
            return None

        # Entry trigger: price must break above first candle high
        breakout_level = first_candle['high']
        if current_price <= breakout_level:
            return None

        # Stop is first candle low
        stop_level = first_candle['low']

        # Ensure reasonable risk (stop not too far from entry)
        risk_pct = (current_price - stop_level) / current_price
        if risk_pct > 0.05:  # Max 5% risk from entry to stop
            logger.debug(
                f"[GAP_AND_GO] {symbol}: Risk too high {risk_pct:.2%}, skipping"
            )
            return None

        # Calculate target (2:1 R/R)
        target_stop = self._calculate_target_stop(current_price, stop_level)

        return EntrySignal(
            symbol=symbol,
            price=current_price,
            target=target_stop['target'],
            stop=target_stop['stop'],
            reason=(
                f"Gap and Go: {gap_data['gap_pct']:.1f}% gap, "
                f"breakout above ${breakout_level:.2f}"
            ),
            metadata={
                'direction': 'long',
                'gap_pct': gap_data['gap_pct'],
                'prior_close': gap_data['prior_close'],
                'today_open': gap_data['today_open'],
                'first_candle_high': first_candle['high'],
                'first_candle_low': first_candle['low'],
                'target': target_stop['target'],
                'stop': target_stop['stop'],
                'risk_per_share': target_stop['risk_per_share'],
                'rr_ratio': self.rr_ratio,
            }
        )

    def check_exit(self, symbol: str, position: Dict) -> Optional[ExitSignal]:
        """
        Check if position should be exited.

        Exit Conditions:
        1. Time >= 10:00 AM ET (forced exit)
        2. Price >= target (2:1 R/R achieved)
        3. Price <= stop (first candle low)

        Args:
            position: Dict with keys: entry_price, shares, entry_time, target, stop

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
        pnl_pct = (
            ((current_price - entry_price) / entry_price) * 100
            if entry_price > 0
            else 0
        )

        # Condition 1: EOD exit time (10:00 AM for Gap and Go)
        if now_et.time() >= self.eod_exit_time:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='eod',
                pnl_pct=pnl_pct,
                metadata={
                    'eod_time': str(self.eod_exit_time),
                    'direction': 'long',
                }
            )

        # Get target and stop from position metadata
        target = position.get('target')
        stop = position.get('stop')

        # Condition 2: Target hit (2:1 R/R)
        if target and current_price >= target:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='target',
                pnl_pct=pnl_pct,
                metadata={
                    'target': target,
                    'hit_price': current_price,
                    'direction': 'long',
                }
            )

        # Condition 3: Stop hit (first candle low)
        if stop and current_price <= stop:
            return ExitSignal(
                symbol=symbol,
                price=current_price,
                reason='stop',
                pnl_pct=pnl_pct,
                metadata={
                    'stop': stop,
                    'hit_price': current_price,
                    'direction': 'long',
                }
            )

        return None

    def get_candidates(self) -> List[EntrySignal]:
        """
        Screen all symbols for Gap and Go entry candidates.

        Returns:
            List of EntrySignal objects sorted by gap percentage (highest first)
        """
        if not self.is_entry_window():
            now_et = self._get_current_et().time()
            logger.info(
                f"[GAP_AND_GO] Outside entry window "
                f"(9:30-10:00 AM), current time: {now_et}"
            )
            return []

        symbols = self.indicators.get_all_symbols()
        traded_today = self._get_traded_today()
        candidates = []

        # First pass: identify gap-up stocks
        gap_stocks = []
        for symbol in symbols:
            if symbol in traded_today:
                continue

            try:
                gap_data = self._get_overnight_gap(symbol)
                if gap_data and gap_data['gap_pct'] >= self.min_gap_pct:
                    gap_stocks.append(gap_data)
            except Exception as e:
                logger.debug(f"Error checking gap for {symbol}: {e}")
                continue

        # Sort by gap percentage (highest first) and take top candidates
        gap_stocks.sort(key=lambda x: x['gap_pct'], reverse=True)
        gap_stocks = gap_stocks[:self.max_positions * 5]  # Check top gappers

        logger.info(
            f"[GAP_AND_GO] Found {len(gap_stocks)} stocks gapping up > "
            f"{self.min_gap_pct}%"
        )

        # Second pass: check for breakout on high-gap stocks
        for gap_data in gap_stocks:
            symbol = gap_data['symbol']

            try:
                signal = self.check_entry(symbol)
                if signal:
                    candidates.append(signal)

                    if len(candidates) >= self.max_positions * 2:
                        break

            except Exception as e:
                logger.debug(f"Error checking {symbol} for Gap and Go: {e}")
                continue

        # Sort by gap percentage (highest first)
        candidates.sort(
            key=lambda x: x.metadata.get('gap_pct', 0),
            reverse=True
        )

        logger.info(f"[GAP_AND_GO] Found {len(candidates)} entry candidates")
        return candidates[:self.max_positions * 2]

    def record_entry(self, symbol: str) -> None:
        """Record that a position was entered for this symbol today."""
        self._mark_traded(symbol)
        logger.info(f"[GAP_AND_GO] Recorded entry for {symbol}")

    def __repr__(self) -> str:
        return (
            f"GapAndGoStrategy(min_gap={self.min_gap_pct}%, "
            f"rr_ratio={self.rr_ratio}:1, "
            f"max_pos={self.max_positions}, eod={self.eod_exit_time})"
        )
