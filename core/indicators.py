"""Technical indicators with correct implementations."""
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass


@dataclass
class MACDResult:
    """MACD calculation result."""
    macd: float
    signal: float
    histogram: float


@dataclass
class BollingerResult:
    """Bollinger Bands result."""
    upper: float
    middle: float
    lower: float
    percent_b: float  # Where price is relative to bands (0-1)


@dataclass
class KeltnerResult:
    """Keltner Channel result."""
    upper: float
    middle: float
    lower: float


class Indicators:
    """Technical indicator calculations."""

    @staticmethod
    def sma(values: List[float], period: int) -> Optional[float]:
        """Simple Moving Average."""
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def ema(values: List[float], period: int) -> Optional[float]:
        """Exponential Moving Average."""
        if len(values) < period:
            return None

        multiplier = 2 / (period + 1)

        # Start with SMA for first EMA value
        ema_val = sum(values[:period]) / period

        # Calculate EMA for remaining values
        for price in values[period:]:
            ema_val = (price * multiplier) + (ema_val * (1 - multiplier))

        return ema_val

    @staticmethod
    def rsi(closes: List[float], period: int = 14) -> Optional[float]:
        """Relative Strength Index using Wilder's smoothing."""
        if len(closes) < period + 1:
            return None

        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]

        # Separate gains and losses
        gains = [max(0, c) for c in changes]
        losses = [abs(min(0, c)) for c in changes]

        # First average (SMA)
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's smoothing for remaining
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def macd(
        closes: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Optional[MACDResult]:
        """MACD with EMA signal line (CORRECT implementation)."""
        if len(closes) < slow + signal:
            return None

        # Calculate MACD line values for signal EMA
        macd_values = []
        for i in range(slow, len(closes) + 1):
            subset = closes[:i]
            fast_ema = Indicators.ema(subset, fast)
            slow_ema = Indicators.ema(subset, slow)
            if fast_ema and slow_ema:
                macd_values.append(fast_ema - slow_ema)

        if len(macd_values) < signal:
            return None

        # Current MACD line
        macd_line = macd_values[-1]

        # CRITICAL: Signal line is EMA of MACD (not SMA!)
        signal_line = Indicators.ema(macd_values, signal)

        if signal_line is None:
            return None

        histogram = macd_line - signal_line

        return MACDResult(
            macd=macd_line,
            signal=signal_line,
            histogram=histogram
        )

    @staticmethod
    def bollinger_bands(
        closes: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Optional[BollingerResult]:
        """Bollinger Bands."""
        if len(closes) < period:
            return None

        # Middle band is SMA
        middle = sum(closes[-period:]) / period

        # Standard deviation
        variance = sum((x - middle) ** 2 for x in closes[-period:]) / period
        std = variance ** 0.5

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)

        # Percent B: where current price is relative to bands
        current = closes[-1]
        if upper != lower:
            percent_b = (current - lower) / (upper - lower)
        else:
            percent_b = 0.5

        return BollingerResult(
            upper=upper,
            middle=middle,
            lower=lower,
            percent_b=percent_b
        )

    @staticmethod
    def atr(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> Optional[float]:
        """Average True Range."""
        if len(closes) < period + 1:
            return None

        true_ranges = []
        for i in range(1, len(closes)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            true_ranges.append(max(high_low, high_close, low_close))

        if len(true_ranges) < period:
            return None

        # First ATR is SMA
        atr_val = sum(true_ranges[:period]) / period

        # Wilder's smoothing
        for tr in true_ranges[period:]:
            atr_val = (atr_val * (period - 1) + tr) / period

        return atr_val

    @staticmethod
    def keltner_channels(
        closes: List[float],
        highs: List[float],
        lows: List[float],
        period: int = 20,
        multiplier: float = 2.0
    ) -> Optional[KeltnerResult]:
        """Keltner Channels (EMA ± ATR * multiplier)."""
        middle = Indicators.ema(closes, period)
        atr_val = Indicators.atr(highs, lows, closes, period)

        if middle is None or atr_val is None:
            return None

        upper = middle + (multiplier * atr_val)
        lower = middle - (multiplier * atr_val)

        return KeltnerResult(
            upper=upper,
            middle=middle,
            lower=lower
        )

    @staticmethod
    def vwap(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        volumes: List[int]
    ) -> Optional[float]:
        """Volume Weighted Average Price."""
        if not volumes or len(volumes) != len(closes):
            return None

        total_volume = sum(volumes)
        if total_volume == 0:
            return None

        # Typical price * volume
        cum_pv = sum(
            ((h + l + c) / 3) * v
            for h, l, c, v in zip(highs, lows, closes, volumes)
        )

        return cum_pv / total_volume

    @staticmethod
    def adx(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> Optional[float]:
        """Average Directional Index (CORRECT: smoothed DX)."""
        if len(closes) < period * 2:
            return None

        # Calculate +DM and -DM
        plus_dm = []
        minus_dm = []
        for i in range(1, len(highs)):
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]

            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)

            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)

        # Calculate True Range
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)

        if len(tr_list) < period:
            return None

        # Smooth +DM, -DM, TR using Wilder's smoothing
        def wilder_smooth(values: List[float], period: int) -> List[float]:
            smoothed = [sum(values[:period])]
            for val in values[period:]:
                smoothed.append(smoothed[-1] - (smoothed[-1] / period) + val)
            return smoothed

        smooth_plus_dm = wilder_smooth(plus_dm, period)
        smooth_minus_dm = wilder_smooth(minus_dm, period)
        smooth_tr = wilder_smooth(tr_list, period)

        # Calculate DX values
        dx_values = []
        for i in range(len(smooth_tr)):
            if smooth_tr[i] == 0:
                continue
            plus_di = 100 * smooth_plus_dm[i] / smooth_tr[i]
            minus_di = 100 * smooth_minus_dm[i] / smooth_tr[i]

            di_sum = plus_di + minus_di
            if di_sum == 0:
                dx_values.append(0)
            else:
                dx = 100 * abs(plus_di - minus_di) / di_sum
                dx_values.append(dx)

        if len(dx_values) < period:
            return None

        # CRITICAL: ADX is smoothed DX (not raw DX!)
        adx_val = sum(dx_values[:period]) / period
        for dx in dx_values[period:]:
            adx_val = (adx_val * (period - 1) + dx) / period

        return adx_val

    @staticmethod
    def stochastic(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        k_period: int = 14,
        d_period: int = 3
    ) -> Optional[Tuple[float, float]]:
        """Stochastic Oscillator (%K and %D)."""
        if len(closes) < k_period + d_period:
            return None

        # Calculate %K values
        k_values = []
        for i in range(k_period - 1, len(closes)):
            period_high = max(highs[i-k_period+1:i+1])
            period_low = min(lows[i-k_period+1:i+1])

            if period_high == period_low:
                k_values.append(50.0)
            else:
                k = 100 * (closes[i] - period_low) / (period_high - period_low)
                k_values.append(k)

        if len(k_values) < d_period:
            return None

        # %D is SMA of %K
        d = sum(k_values[-d_period:]) / d_period
        k = k_values[-1]

        return (k, d)
