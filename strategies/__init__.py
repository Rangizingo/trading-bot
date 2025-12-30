"""
Intraday Trading Strategies V2

Three verified true intraday strategies:
- ORBV2Strategy: Simplified ORB (74.56% win rate, 2.51 PF)
- OvernightReversalStrategy: Buy overnight losers (Sharpe 4.44)
- StocksInPlayStrategy: First 5-min candle on high-vol stocks (Sharpe 2.81)

All strategies close positions same-day (no overnight holds).
"""

from .base_strategy import BaseStrategy, EntrySignal, ExitSignal
from .orb_v2_strategy import ORBV2Strategy
from .overnight_reversal_strategy import OvernightReversalStrategy
from .stocks_in_play_strategy import StocksInPlayStrategy

# Legacy imports for backward compatibility (will be removed in Phase 7)
try:
    from .orb_strategy import ORBStrategy
    from .wma_ha_strategy import WMAHAStrategy
    from .hma_ha_strategy import HMAHAStrategy
except ImportError:
    ORBStrategy = None
    WMAHAStrategy = None
    HMAHAStrategy = None

__all__ = [
    'BaseStrategy',
    'EntrySignal',
    'ExitSignal',
    'ORBV2Strategy',
    'OvernightReversalStrategy',
    'StocksInPlayStrategy',
]
