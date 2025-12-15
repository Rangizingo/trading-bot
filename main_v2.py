"""Main trading bot orchestrator - v2 with intraday cache."""
import sys
import time
import logging
from datetime import datetime, time as dt_time
from typing import List, Dict, Optional
from pathlib import Path

sys.path.insert(0, 'C:/Users/User/Documents/AI/trading_bot')

from config import TRADING, ET
from data.vv7_client import VV7Client
from data.cache import BulkCache
from data.intraday_bridge import IntradayBridge
from data.models import Signal, Action, Bar
from core.position import PositionManager
from core.risk import RiskManager
from execution.alpaca import AlpacaClient

# Import strategies
from strategies.connors_rsi import ConnorsRSI2Strategy
from strategies.cumulative_rsi import CumulativeRSIStrategy
from strategies.keltner_rsi import KeltnerRSIStrategy
from strategies.bb_rsi import BollingerRSIStrategy

# Configure logging
LOG_DIR = Path('C:/Users/User/Documents/AI/trading_bot/logs')
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Trading bot using VV7 intraday cache + Alpaca execution."""

    def __init__(self, paper: bool = True):
        self.paper = paper
        
        # Components
        self.vv7 = VV7Client()
        self.intraday = IntradayBridge()
        self.alpaca = AlpacaClient(paper=paper)
        self.position_manager = PositionManager(TRADING.capital)
        self.risk_manager = RiskManager()
        
        # Strategies (skip VWAP - needs true intraday)
        self.strategies = [
            ConnorsRSI2Strategy(),
            CumulativeRSIStrategy(),
            KeltnerRSIStrategy(),
            BollingerRSIStrategy(),
        ]
        
        self.running = False
        self.cycle_count = 0

    def is_market_hours(self) -> bool:
        now = datetime.now(ET)
        if now.weekday() >= 5:
            return False
        return TRADING.market_open <= now.time() <= TRADING.market_close

    def sync_positions_from_alpaca(self) -> None:
        """Load existing Alpaca positions into position manager."""
        try:
            positions = self.alpaca.get_positions()
            for pos in positions:
                self.position_manager.open_position(
                    symbol=pos.symbol,
                    shares=int(pos.qty),
                    entry_price=float(pos.current_price),
                    stop_loss=None,
                    take_profit=None,
                    strategy="existing"
                )
            logger.info(f"Loaded {len(positions)} existing positions from Alpaca")
        except Exception as e:
            logger.error(f"Failed to sync positions from Alpaca: {e}")

    def startup_checks(self) -> bool:
        logger.info("Running startup checks...")
        
        # VV7 API
        if not self.vv7.health_check():
            logger.error("VV7 API not responding")
            return False
        logger.info("[OK] VV7 API healthy")
        
        # Intraday cache
        if self.intraday.is_cache_available():
            stats = self.intraday.get_cache_stats()
            logger.info(f"[OK] Intraday cache: {stats['symbol_count']} symbols")
        else:
            logger.warning("[WARN] Intraday cache empty - will continue without cache")

        # Alpaca (critical)
        try:
            account = self.alpaca.get_account()
            logger.info(f"[OK] Alpaca: ${account.equity:,.2f}")
            self.risk_manager.set_daily_start(account.equity)

            # Sync existing positions
            self.sync_positions_from_alpaca()
        except Exception as e:
            logger.error(f"Alpaca failed: {e}")
            return False

        return True

    def smart_sync(self) -> bool:
        """Disabled - external cache sync handles this via --loop flag."""
        # Bot is read-only, cache sync is handled by:
        # python vv7_data_cache/intraday_cache.py smart --days 0 --loop 5
        return True

    def delta_sync(self) -> None:
        """Disabled - external cache sync handles this."""
        pass

    def get_candidates(self) -> List[str]:
        if self.intraday.is_cache_available():
            rsi = self.intraday.get_candidates_by_rsi(max_rsi=35, min_volume=100000)
            bb = self.intraday.get_candidates_by_bb(min_volume=100000)
            candidates = list(set(rsi + bb))
            logger.info(f"Candidates: {len(candidates)} (RSI:{len(rsi)}, BB:{len(bb)})")
            return candidates[:100]
        return []

    def generate_signals(self, candidates: List[str]) -> List[Signal]:
        signals = []
        for symbol in candidates:
            bars = self.intraday.get_bar_history(symbol, limit=250)
            if len(bars) < 50:
                continue
            
            has_position = self.position_manager.get_position(symbol) is not None
            
            for strategy in self.strategies:
                try:
                    signal = strategy.on_bar(symbol, bars[-1], bars, has_position)
                    if signal:
                        signals.append(signal)
                except Exception:
                    pass
        
        logger.info(f"Signals: {len(signals)}")
        return signals

    def execute_buy(self, signal: Signal) -> None:
        limits = self.risk_manager.check_limits(
            self.position_manager.get_equity({signal.symbol: signal.entry_price}),
            self.position_manager.position_count()
        )
        if not limits.can_trade:
            return
        
        shares = self.risk_manager.calculate_position_size(
            self.position_manager.get_available_capital(),
            signal.entry_price,
            signal.stop_loss
        )
        if shares <= 0:
            return
        
        order = self.alpaca.submit_market_order(signal.symbol, shares, "buy")
        if order:
            logger.info(f"BUY {shares} {signal.symbol} @ ${signal.entry_price:.2f}")
            self.position_manager.open_position(
                signal.symbol, shares, signal.entry_price,
                signal.stop_loss, signal.take_profit, signal.strategy
            )

    def check_exits(self) -> None:
        for pos in self.alpaca.get_positions():
            local = self.position_manager.get_position(pos.symbol)
            if not local:
                continue
            
            if local.stop_loss and pos.current_price <= local.stop_loss:
                logger.info(f"STOP {pos.symbol}")
                self.alpaca.close_position(pos.symbol)
                self.position_manager.close_position(pos.symbol, pos.current_price, "stop")
            elif local.take_profit and pos.current_price >= local.take_profit:
                logger.info(f"TP {pos.symbol}")
                self.alpaca.close_position(pos.symbol)
                self.position_manager.close_position(pos.symbol, pos.current_price, "tp")

    def log_heartbeat(self) -> None:
        """Log heartbeat with key metrics."""
        try:
            account = self.alpaca.get_account()
            positions = len(self.alpaca.get_positions())
            now = datetime.now(ET).strftime("%H:%M:%S")
            logger.info(f"HEARTBEAT | Cycle {self.cycle_count} | Equity: ${account.equity:,.2f} | Positions: {positions} | Time: {now}")
        except Exception as e:
            logger.warning(f"Failed to log heartbeat: {e}")

    def log_daily_summary(self) -> None:
        """Log daily trading summary."""
        logger.info("=" * 40)
        logger.info("=== DAILY SUMMARY ===")
        try:
            account = self.alpaca.get_account()
            positions = self.alpaca.get_positions()

            # Get closed positions from position manager
            closed_positions = [p for p in self.position_manager.positions.values() if p.exit_price is not None]
            wins = len([p for p in closed_positions if p.exit_price > p.entry_price])
            losses = len([p for p in closed_positions if p.exit_price <= p.entry_price])

            logger.info(f"Trades: {len(closed_positions)} | Wins: {wins} | Losses: {losses}")
            logger.info(f"Daily P&L: ${float(account.equity) - self.risk_manager.daily_start_equity:,.2f}")
            logger.info(f"Open Positions: {len(positions)}")
            logger.info(f"Final Equity: ${account.equity:,.2f}")
        except Exception as e:
            logger.warning(f"Failed to generate daily summary: {e}")
        logger.info("=" * 40)

    def run_cycle(self) -> None:
        self.cycle_count += 1
        logger.info(f"--- Cycle {self.cycle_count} ---")

        # Sync positions from Alpaca each cycle (handles manual trades/liquidations)
        self.position_manager.positions.clear()
        self.sync_positions_from_alpaca()

        self.delta_sync()
        candidates = self.get_candidates()
        signals = self.generate_signals(candidates)

        # Execute top BUY signals
        buy_signals = sorted(
            [s for s in signals if s.action == Action.BUY],
            key=lambda s: s.strength, reverse=True
        )
        slots = TRADING.max_positions - self.position_manager.position_count()
        for signal in buy_signals[:slots]:
            self.execute_buy(signal)

        self.check_exits()

        # Log heartbeat
        self.log_heartbeat()

    def run(self) -> None:
        logger.info("=" * 40)
        logger.info("Trading Bot Starting")
        logger.info("=" * 40)

        if not self.startup_checks():
            return

        # Sync cache first
        logger.info("Syncing cache...")
        self.smart_sync()
        logger.info("Cache synced, waiting for market...")

        self.running = True
        while self.running and not self.is_market_hours():
            logger.info("Waiting for market...")
            time.sleep(30)

        logger.info("Market open - trading loop")
        while self.running and self.is_market_hours():
            self.run_cycle()
            time.sleep(TRADING.cycle_interval_minutes * 60)

        logger.info("Market closed")
        self.log_daily_summary()


def main():
    bot = TradingBot(paper=True)
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Stopped")


if __name__ == "__main__":
    main()
