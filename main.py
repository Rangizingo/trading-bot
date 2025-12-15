"""Main trading bot orchestrator."""
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
from data.models import Signal, Action
from core.position import PositionManager
from core.risk import RiskManager
from execution.alpaca import AlpacaClient

# Import strategies
from strategies.connors_rsi import ConnorsRSI2Strategy
from strategies.cumulative_rsi import CumulativeRSIStrategy
from strategies.vwap_rsi import VWAPRSIStrategy
from strategies.keltner_rsi import KeltnerRSIStrategy
from strategies.bb_rsi import BollingerRSIStrategy


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Main trading bot orchestrator."""

    def __init__(
        self,
        paper: bool = True,
        use_cache: bool = True
    ):
        self.paper = paper
        self.use_cache = use_cache

        # Initialize components
        self.vv7 = VV7Client()
        self.cache = BulkCache() if use_cache else None
        self.alpaca = AlpacaClient(paper=paper)
        self.position_manager = PositionManager(TRADING.capital)
        self.risk_manager = RiskManager()

        # Initialize strategies
        self.strategies = [
            ConnorsRSI2Strategy(),
            CumulativeRSIStrategy(),
            VWAPRSIStrategy(),
            KeltnerRSIStrategy(),
            BollingerRSIStrategy(),
        ]

        # State
        self.running = False
        self.cycle_count = 0

    def is_market_hours(self) -> bool:
        """Check if within market hours (9:30 AM - 4:00 PM ET)."""
        now = datetime.now(ET)
        current_time = now.time()

        # Check if weekday
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        return TRADING.market_open <= current_time <= TRADING.market_close

    def is_pre_market(self) -> bool:
        """Check if in pre-market buffer period."""
        now = datetime.now(ET)
        current_time = now.time()

        if now.weekday() >= 5:
            return False

        pre_market_start = dt_time(
            TRADING.market_open.hour,
            TRADING.market_open.minute - TRADING.pre_market_buffer_minutes
        )
        return pre_market_start <= current_time < TRADING.market_open

    def startup_checks(self) -> bool:
        """Run pre-market startup checks."""
        logger.info("Running startup checks...")

        # Check VV7 API
        if not self.vv7.health_check():
            logger.error("VV7 API not responding")
            return False
        logger.info("✓ VV7 API healthy")

        # Check Alpaca
        try:
            account = self.alpaca.get_account()
            logger.info(f"✓ Alpaca connected - Equity: ${account.equity:,.2f}")
        except Exception as e:
            logger.error(f"Alpaca connection failed: {e}")
            return False

        # Set daily start equity
        self.risk_manager.set_daily_start(account.equity)

        logger.info("All startup checks passed")
        return True

    def fetch_data(self) -> Dict:
        """Fetch bulk data from VV7 API."""
        logger.info("Fetching bulk data...")

        # Check cache freshness
        if self.cache and not self.cache.is_stale("ratings"):
            logger.info("Using cached data")
            stocks = self.cache.get_all_stocks()
            technicals = self.cache.get_all_technicals()
        else:
            # Fetch fresh
            stocks = self.vv7.get_bulk_ratings()
            technicals = self.vv7.get_bulk_technicals()

            # Update cache
            if self.cache:
                self.cache.sync_ratings(stocks)
                self.cache.sync_technicals(technicals)

        logger.info(f"Fetched {len(stocks)} stocks, {len(technicals)} technicals")
        return {"stocks": stocks, "technicals": technicals}

    def generate_signals(self, data: Dict) -> List[Signal]:
        """Run all strategies and collect signals."""
        signals = []
        stocks = data["stocks"]
        technicals = data["technicals"]

        # For live trading, we'd need bar history
        # This is a simplified version using cached data
        logger.info(f"Running {len(self.strategies)} strategies...")

        # In live mode, signals would come from real-time bar processing
        # For now, return empty (actual implementation would query bar history)

        return signals

    def rank_signals(self, signals: List[Signal]) -> List[Signal]:
        """Rank signals by strength, return top N."""
        # Sort by strength descending
        ranked = sorted(signals, key=lambda s: s.strength, reverse=True)

        # Limit by remaining position slots
        current_positions = self.position_manager.position_count()
        available_slots = TRADING.max_positions - current_positions

        return ranked[:available_slots]

    def execute_signals(self, signals: List[Signal]) -> None:
        """Execute top signals via Alpaca."""
        for signal in signals:
            if signal.action == Action.BUY:
                self._execute_buy(signal)
            elif signal.action == Action.SELL:
                self._execute_sell(signal)

    def _execute_buy(self, signal: Signal) -> None:
        """Execute buy signal."""
        # Check risk limits
        current_prices = {signal.symbol: signal.entry_price}
        equity = self.position_manager.get_equity(current_prices)
        limits = self.risk_manager.check_limits(
            equity,
            self.position_manager.position_count()
        )

        if not limits.can_trade:
            logger.warning(f"Cannot trade: {limits.reason}")
            return

        # Calculate position size
        shares = self.risk_manager.calculate_position_size(
            self.position_manager.get_available_capital(),
            signal.entry_price,
            signal.stop_loss
        )

        if shares <= 0:
            return

        # Submit order
        order = self.alpaca.submit_market_order(
            signal.symbol,
            shares,
            "buy"
        )

        if order:
            logger.info(f"BUY {shares} {signal.symbol} @ ~${signal.entry_price:.2f} ({signal.strategy})")

            # Track in position manager (will update when filled)
            self.position_manager.open_position(
                signal.symbol,
                shares,
                signal.entry_price,
                signal.stop_loss,
                signal.take_profit,
                signal.strategy
            )

    def _execute_sell(self, signal: Signal) -> None:
        """Execute sell/close signal."""
        position = self.position_manager.get_position(signal.symbol)
        if not position:
            return

        order = self.alpaca.close_position(signal.symbol)

        if order:
            logger.info(f"SELL {signal.symbol} ({signal.reason})")
            self.position_manager.close_position(signal.symbol, signal.entry_price, signal.reason)

    def check_exits(self) -> None:
        """Check stop loss and take profit for open positions."""
        positions = self.alpaca.get_positions()

        for pos in positions:
            local_pos = self.position_manager.get_position(pos.symbol)
            if not local_pos:
                continue

            # Check stop loss
            if local_pos.stop_loss and pos.current_price <= local_pos.stop_loss:
                logger.info(f"Stop loss hit for {pos.symbol}")
                self.alpaca.close_position(pos.symbol)
                self.position_manager.close_position(
                    pos.symbol, pos.current_price, "stop_loss"
                )

            # Check take profit
            elif local_pos.take_profit and pos.current_price >= local_pos.take_profit:
                logger.info(f"Take profit hit for {pos.symbol}")
                self.alpaca.close_position(pos.symbol)
                self.position_manager.close_position(
                    pos.symbol, pos.current_price, "take_profit"
                )

    def log_status(self) -> None:
        """Log current status."""
        account = self.alpaca.get_account()
        positions = self.alpaca.get_positions()

        logger.info(
            f"Cycle {self.cycle_count} | "
            f"Equity: ${account.equity:,.2f} | "
            f"Positions: {len(positions)} | "
            f"Realized P&L: ${self.position_manager.get_realized_pnl():,.2f}"
        )

    def run_cycle(self) -> None:
        """Run one trading cycle."""
        self.cycle_count += 1

        try:
            # Fetch data
            data = self.fetch_data()

            # Generate signals
            signals = self.generate_signals(data)

            # Rank and filter
            top_signals = self.rank_signals(signals)

            # Execute
            if top_signals:
                self.execute_signals(top_signals)

            # Check exits
            self.check_exits()

            # Log status
            self.log_status()

        except Exception as e:
            logger.error(f"Cycle error: {e}")

    def run(self) -> None:
        """Main run loop."""
        logger.info("=" * 50)
        logger.info("Trading Bot Starting")
        logger.info("=" * 50)

        self.running = True

        # Wait for pre-market
        while self.running and not self.is_pre_market() and not self.is_market_hours():
            logger.info("Waiting for pre-market...")
            time.sleep(60)

        # Run startup checks
        if not self.startup_checks():
            logger.error("Startup checks failed, exiting")
            return

        # Wait for market open
        while self.running and not self.is_market_hours():
            logger.info("Waiting for market open...")
            time.sleep(30)

        logger.info("Market open - starting trading loop")

        # Main trading loop
        while self.running and self.is_market_hours():
            self.run_cycle()

            # Wait for next cycle
            time.sleep(TRADING.cycle_interval_minutes * 60)

        logger.info("Market closed - shutting down")
        self.shutdown()

    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down...")
        self.running = False

        # Log final status
        self.log_status()

        # Close connections
        self.vv7.close()
        if self.cache:
            self.cache.close()

        logger.info("Shutdown complete")


def main():
    """Entry point."""
    bot = TradingBot(paper=True)

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        bot.shutdown()


if __name__ == "__main__":
    main()
