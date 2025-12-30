"""
Alpaca API client for executing trades and managing positions.

Uses the alpaca-py library to interact with Alpaca's trading API.
Supports both paper and live trading environments.
"""

import logging
import time
from typing import Dict, List, Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType, QueryOrderStatus
from alpaca.common.exceptions import APIError

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

# Configure logging
logger = logging.getLogger(__name__)


class AlpacaClient:
    """
    Client for interacting with Alpaca's trading API.

    Provides methods for account management, position tracking, and order execution.
    All API errors are caught and logged, with graceful fallbacks.
    """

    def __init__(self, paper: bool = True, api_key: str = None, secret_key: str = None, name: str = None) -> None:
        """
        Initialize Alpaca trading client.

        Args:
            paper: If True, use paper trading environment. If False, use live trading.
            api_key: Optional API key. If not provided, uses ALPACA_API_KEY from config.
            secret_key: Optional secret key. If not provided, uses ALPACA_SECRET_KEY from config.
            name: Optional name for this client instance (for logging).

        Raises:
            ValueError: If API credentials are missing or invalid.
        """
        # Use provided credentials or fall back to defaults
        self.api_key = api_key or ALPACA_API_KEY
        self.secret_key = secret_key or ALPACA_SECRET_KEY
        self.name = name or "default"

        if not self.api_key or not self.secret_key:
            raise ValueError(
                "Alpaca API credentials are not configured. "
                "Provide api_key/secret_key or set ALPACA_API_KEY and ALPACA_SECRET_KEY in environment variables."
            )

        try:
            self.client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=paper
            )
            self.paper = paper
            logger.info(f"Alpaca client '{self.name}' initialized (paper={paper})")
        except Exception as e:
            logger.error(f"Failed to initialize Alpaca client '{self.name}': {e}")
            raise

    def get_account(self) -> Dict:
        """
        Get current account information.

        Returns:
            Dictionary with account details:
                - equity: Total account value (float)
                - cash: Available cash (float)
                - buying_power: Buying power (float)

        Raises:
            APIError: If API request fails.
        """
        try:
            account = self.client.get_account()

            result = {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power)
            }

            logger.info(
                f"Account info: equity=${result['equity']:.2f}, "
                f"cash=${result['cash']:.2f}, "
                f"buying_power=${result['buying_power']:.2f}"
            )

            return result

        except APIError as e:
            logger.error(f"Failed to get account info: {e}")
            raise

    def get_positions(self) -> List[Dict]:
        """
        Get all open positions.

        Returns:
            List of dictionaries, each containing:
                - symbol: Stock symbol (str)
                - qty: Number of shares (float)
                - market_value: Current market value (float)
                - current_price: Current price per share (float)
                - avg_entry_price: Average entry price (float)
                - unrealized_pl: Unrealized profit/loss (float)
        """
        try:
            positions = self.client.get_all_positions()

            result = []
            for pos in positions:
                result.append({
                    "symbol": pos.symbol,
                    "qty": float(pos.qty),
                    "market_value": float(pos.market_value),
                    "current_price": float(pos.current_price),
                    "avg_entry_price": float(pos.avg_entry_price),
                    "unrealized_pl": float(pos.unrealized_pl)
                })

            logger.info(f"Retrieved {len(result)} open positions")
            return result

        except APIError as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Stock symbol to query.

        Returns:
            Dictionary with position details, or None if no position exists.
            Dictionary contains same fields as get_positions().
        """
        try:
            pos = self.client.get_open_position(symbol)

            result = {
                "symbol": pos.symbol,
                "qty": float(pos.qty),
                "market_value": float(pos.market_value),
                "current_price": float(pos.current_price),
                "avg_entry_price": float(pos.avg_entry_price),
                "unrealized_pl": float(pos.unrealized_pl)
            }

            logger.info(f"Position for {symbol}: {result['qty']} shares @ ${result['current_price']:.2f}")
            return result

        except APIError as e:
            # Position not found is expected, don't log as error
            if "position does not exist" in str(e).lower():
                logger.debug(f"No position found for {symbol}")
                return None
            else:
                logger.error(f"Failed to get position for {symbol}: {e}")
                return None

    def is_market_open(self) -> bool:
        """
        Check if the market is currently open.

        Returns:
            True if market is open, False otherwise.
        """
        try:
            clock = self.client.get_clock()
            is_open = clock.is_open

            logger.debug(f"Market is {'open' if is_open else 'closed'}")
            return is_open

        except APIError as e:
            logger.error(f"Failed to get market clock: {e}")
            return False

    def submit_buy(self, symbol: str, qty: int) -> Optional[Dict]:
        """
        Submit a market buy order.

        Args:
            symbol: Stock symbol to buy.
            qty: Number of shares to buy.

        Returns:
            Dictionary with order details if successful:
                - id: Order ID (str)
                - symbol: Stock symbol (str)
                - qty: Number of shares (int)
                - side: Order side ("buy")
                - status: Order status (str)
            Returns None if order fails.
        """
        try:
            # Ensure qty is integer
            qty = int(qty)

            # Create market order request
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )

            # Submit order
            order = self.client.submit_order(order_data)

            result = {
                "id": order.id,
                "symbol": order.symbol,
                "qty": int(order.qty),
                "side": order.side.value,
                "status": order.status.value
            }

            logger.info(f"Buy order submitted: {symbol} x {qty}, order_id={order.id}, status={order.status}")
            return result

        except APIError as e:
            logger.error(f"Failed to submit buy order for {symbol} x {qty}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error submitting buy order for {symbol}: {e}")
            return None

    def submit_sell(self, symbol: str, qty: int) -> Optional[Dict]:
        """
        Submit a market sell order.

        Args:
            symbol: Stock symbol to sell.
            qty: Number of shares to sell.

        Returns:
            Dictionary with order details if successful:
                - id: Order ID (str)
                - symbol: Stock symbol (str)
                - qty: Number of shares (int)
                - side: Order side ("sell")
                - status: Order status (str)
            Returns None if order fails.
        """
        try:
            # Ensure qty is integer
            qty = int(qty)

            # Create market order request
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )

            # Submit order
            order = self.client.submit_order(order_data)

            result = {
                "id": order.id,
                "symbol": order.symbol,
                "qty": int(order.qty),
                "side": order.side.value,
                "status": order.status.value
            }

            logger.info(f"Sell order submitted: {symbol} x {qty}, order_id={order.id}, status={order.status}")
            return result

        except APIError as e:
            logger.error(f"Failed to submit sell order for {symbol} x {qty}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error submitting sell order for {symbol}: {e}")
            return None

    def close_position(self, symbol: str) -> bool:
        """
        Close entire position for a symbol.

        Automatically cancels any open orders (stop losses) before closing
        to free up shares that may be held by those orders.

        Args:
            symbol: Stock symbol to close.

        Returns:
            True if position was successfully closed, False otherwise.
        """
        try:
            # First, cancel any existing orders for this symbol to free up shares
            cancelled_count = self.cancel_orders_for_symbol(symbol)

            # If we cancelled orders, wait for Alpaca to process the cancellation
            if cancelled_count > 0:
                logger.info(f"Waiting 1 second for order cancellations to process...")
                time.sleep(1.0)

            # Now close the position
            self.client.close_position(symbol)

            logger.info(f"Position closed successfully: {symbol}")
            return True

        except APIError as e:
            logger.error(f"Failed to close position for {symbol}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error closing position for {symbol}: {e}")
            return False

    def submit_simple_order(self, symbol: str, qty: int, side: str = 'buy') -> Optional[Dict]:
        """
        Submit a simple market order without stop loss.

        This submits a market order and waits for it to fill.
        No stop loss order is created.

        Args:
            symbol: Stock symbol to trade.
            qty: Number of shares.
            side: 'buy' for long entry, 'sell' for short entry.

        Returns:
            Dictionary with order details if successful:
                - order_id: Order ID (str)
                - fill_price: Actual fill price (float)
                - symbol: Stock symbol (str)
                - qty: Number of shares actually filled (int)
            Returns None if order fails.
        """
        try:
            # Ensure qty is integer
            qty = int(qty)

            # Cancel any existing orders for this symbol to prevent wash trade errors
            self.cancel_orders_for_symbol(symbol)

            # Determine order side
            order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL

            # Submit the market order with GTC
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.GTC
            )
            buy_order = self.client.submit_order(order_data)

            logger.info(
                f"Simple order - {side.upper()} order submitted: {symbol} x {qty}, "
                f"order_id={buy_order.id}, status={buy_order.status}"
            )

            # Poll for fill status (up to 60 seconds, checking every 0.5 seconds)
            max_wait_time = 60.0  # seconds
            poll_interval = 0.5  # seconds
            elapsed_time = 0.0
            filled_order = None

            while elapsed_time < max_wait_time:
                # Get current order status
                current_order = self.client.get_order_by_id(buy_order.id)

                if current_order.status.value in ['filled', 'partially_filled']:
                    filled_order = current_order
                    logger.info(
                        f"Simple order - {side.upper()} order filled: {symbol} x {current_order.filled_qty} "
                        f"@ ${float(current_order.filled_avg_price):.2f}"
                    )
                    break
                elif current_order.status.value in ['cancelled', 'expired', 'rejected']:
                    logger.error(
                        f"Simple order - {side.upper()} order {current_order.status.value}: {symbol}, "
                        f"order_id={buy_order.id}"
                    )
                    return None

                # Wait before next poll
                time.sleep(poll_interval)
                elapsed_time += poll_interval

            # Check if we got a fill
            if filled_order is None:
                logger.error(
                    f"Simple order - {side.upper()} order did not fill within {max_wait_time}s: "
                    f"{symbol}, order_id={buy_order.id}"
                )
                # Attempt to cancel the unfilled order
                self.cancel_order(buy_order.id)
                return None

            # Get actual fill price and quantity
            actual_fill_price = float(filled_order.filled_avg_price)
            actual_qty = int(filled_order.filled_qty)

            logger.info(
                f"Simple order completed: {symbol} x {actual_qty} @ ${actual_fill_price:.2f}"
            )

            result = {
                "order_id": filled_order.id,
                "fill_price": actual_fill_price,
                "symbol": symbol,
                "qty": actual_qty
            }

            return result

        except APIError as e:
            logger.error(f"Failed to submit simple order for {symbol} x {qty}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error submitting simple order for {symbol}: {e}")
            return None

    def submit_stop_order(self, symbol: str, qty: int, stop_price: float) -> Optional[str]:
        """
        Submit a stop loss sell order for an existing position.

        Used to add stop loss protection to positions that don't have one
        (e.g., when switching from Classic to Safe mode).

        Args:
            symbol: Stock symbol to create stop for.
            qty: Number of shares (should match position size).
            stop_price: Price at which to trigger the stop sell.

        Returns:
            Stop order ID on success, None on failure.
        """
        try:
            logger.info(f"Creating stop order for {symbol}: {qty} shares @ ${stop_price:.2f}")

            stop_request = StopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                type=OrderType.STOP,
                stop_price=round(stop_price, 2),
                time_in_force=TimeInForce.GTC
            )

            stop_order = self.client.submit_order(stop_request)
            logger.info(f"Stop order created for {symbol}: order_id={stop_order.id}, stop_price=${stop_price:.2f}")

            return str(stop_order.id)

        except APIError as e:
            logger.error(f"Failed to create stop order for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating stop order for {symbol}: {e}")
            return None

    def submit_bracket_order(self, symbol: str, qty: int, stop_loss_pct: float) -> Optional[Dict]:
        """
        Submit a bracket order that includes buy + stop loss.

        This submits two separate orders:
        1. A market buy order
        2. Wait for the buy order to fill (up to 60 seconds)
        3. A stop loss sell order calculated from ACTUAL fill price

        Args:
            symbol: Stock symbol to buy.
            qty: Number of shares to buy.
            stop_loss_pct: Stop loss percentage (e.g., 0.03 for 3% stop).

        Returns:
            Dictionary with bracket order details if successful:
                - buy_order: Buy order details dict
                - stop_order: Stop order details dict
                - fill_price: Actual fill price from buy order (float)
                - symbol: Stock symbol (str)
                - qty: Number of shares actually filled (int)
                - stop_price: Stop loss price calculated from actual fill (float)
            Returns None if either order fails.
        """
        try:
            # Ensure qty is integer
            qty = int(qty)

            # Cancel any existing orders for this symbol to prevent wash trade errors
            self.cancel_orders_for_symbol(symbol)

            # First, submit the market buy order with GTC for consistency
            buy_order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC  # Use GTC for consistency with stop order
            )
            buy_order = self.client.submit_order(buy_order_data)

            logger.info(
                f"Bracket order - Buy order submitted: {symbol} x {qty}, "
                f"order_id={buy_order.id}, status={buy_order.status}"
            )

            # Poll for fill status (up to 60 seconds, checking every 0.5 seconds)
            max_wait_time = 60.0  # seconds
            poll_interval = 0.5  # seconds
            elapsed_time = 0.0
            filled_order = None

            while elapsed_time < max_wait_time:
                # Get current order status
                current_order = self.client.get_order_by_id(buy_order.id)

                if current_order.status.value in ['filled', 'partially_filled']:
                    filled_order = current_order
                    logger.info(
                        f"Bracket order - Buy order filled: {symbol} x {current_order.filled_qty} "
                        f"@ ${float(current_order.filled_avg_price):.2f}"
                    )
                    break
                elif current_order.status.value in ['cancelled', 'expired', 'rejected']:
                    logger.error(
                        f"Bracket order - Buy order {current_order.status.value}: {symbol}, "
                        f"order_id={buy_order.id}"
                    )
                    return None

                # Wait before next poll
                time.sleep(poll_interval)
                elapsed_time += poll_interval

            # Check if we got a fill
            if filled_order is None:
                logger.error(
                    f"Bracket order - Buy order did not fill within {max_wait_time}s: "
                    f"{symbol}, order_id={buy_order.id}"
                )
                # Attempt to cancel the unfilled order
                self.cancel_order(buy_order.id)
                return None

            # Get actual fill price and quantity
            actual_fill_price = float(filled_order.filled_avg_price)
            actual_qty = int(filled_order.filled_qty)

            # Handle partial fills - cancel unfilled portion to prevent unprotected shares
            if filled_order.status.value == 'partially_filled':
                unfilled_qty = qty - actual_qty
                logger.warning(
                    f"Bracket order - PARTIAL FILL detected: {symbol} got {actual_qty}/{qty} shares. "
                    f"Canceling unfilled {unfilled_qty} shares to prevent unprotected position."
                )
                self.cancel_order(filled_order.id)

            # Calculate stop price from ACTUAL fill price (not expected price)
            stop_price = round(actual_fill_price * (1 - stop_loss_pct), 2)

            logger.info(
                f"Bracket order - Using actual fill price ${actual_fill_price:.2f} "
                f"and quantity {actual_qty} for stop order @ ${stop_price:.2f} "
                f"({stop_loss_pct*100:.1f}% stop)"
            )

            # Now submit the stop loss sell order with GTC and actual quantity
            stop_order_data = StopOrderRequest(
                symbol=symbol,
                qty=actual_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,  # Good-til-cancelled for stop loss
                stop_price=stop_price
            )
            stop_order = self.client.submit_order(stop_order_data)

            logger.info(
                f"Bracket order - Stop loss submitted: {symbol} x {actual_qty} @ ${stop_price:.2f}, "
                f"stop_order_id={stop_order.id}, status={stop_order.status}"
            )

            result = {
                "buy_order": {
                    "id": filled_order.id,
                    "symbol": filled_order.symbol,
                    "qty": actual_qty,
                    "side": filled_order.side.value,
                    "status": filled_order.status.value
                },
                "stop_order": {
                    "id": stop_order.id,
                    "symbol": stop_order.symbol,
                    "qty": int(stop_order.qty),
                    "side": stop_order.side.value,
                    "status": stop_order.status.value,
                    "stop_price": stop_price
                },
                "fill_price": actual_fill_price,
                "symbol": symbol,
                "qty": actual_qty,
                "stop_price": stop_price,
                # Legacy fields for backward compatibility
                "order_id": filled_order.id,
                "stop_order_id": stop_order.id
            }

            logger.info(f"Bracket order completed: {result}")
            return result

        except APIError as e:
            logger.error(f"Failed to submit bracket order for {symbol} x {qty}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error submitting bracket order for {symbol}: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order by ID.

        Args:
            order_id: The order ID to cancel.

        Returns:
            True if order was successfully cancelled, False otherwise.
            Returns True even if order was already filled or not found (graceful handling).
        """
        try:
            self.client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled successfully: {order_id}")
            return True

        except APIError as e:
            error_msg = str(e).lower()
            # Gracefully handle expected cases
            if "order not found" in error_msg or "order is not cancelable" in error_msg:
                logger.debug(f"Order {order_id} not found or already filled: {e}")
                return True  # Consider this success - order is not active
            else:
                logger.error(f"Failed to cancel order {order_id}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error cancelling order {order_id}: {e}")
            return False

    def cancel_orders_for_symbol(self, symbol: str) -> int:
        """
        Cancel all open orders for a specific symbol.

        Used before placing new orders to prevent wash trade errors.

        Args:
            symbol: Stock symbol to cancel orders for.

        Returns:
            Number of orders cancelled.
        """
        try:
            # Get open orders for this symbol
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
            orders = self.client.get_orders(filter=request)

            cancelled_count = 0
            for order in orders:
                try:
                    self.client.cancel_order_by_id(order.id)
                    logger.info(f"Cancelled existing order for {symbol}: {order.side.value} {order.qty} @ {order.type.value} (id={order.id})")
                    cancelled_count += 1
                except APIError as e:
                    logger.warning(f"Could not cancel order {order.id} for {symbol}: {e}")

            if cancelled_count > 0:
                logger.info(f"Cancelled {cancelled_count} existing order(s) for {symbol}")

            return cancelled_count

        except Exception as e:
            logger.error(f"Error cancelling orders for {symbol}: {e}")
            return 0

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """
        Get all open/pending orders.

        Args:
            symbol: Optional stock symbol to filter by. If None, returns all open orders.

        Returns:
            List of dictionaries, each containing:
                - id: Order ID (str)
                - symbol: Stock symbol (str)
                - qty: Number of shares (int)
                - side: Order side ("buy" or "sell")
                - type: Order type (str)
                - stop_price: Stop price if stop order, None otherwise (Optional[float])
            Returns empty list on error.
        """
        try:
            # Get all open orders
            request = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[symbol] if symbol else None
            )
            orders = self.client.get_orders(filter=request)

            result = []
            for order in orders:
                order_dict = {
                    "id": order.id,
                    "symbol": order.symbol,
                    "qty": int(order.qty),
                    "side": order.side.value,
                    "type": order.type.value,
                    "stop_price": float(order.stop_price) if order.stop_price else None
                }
                result.append(order_dict)

            logger.info(
                f"Retrieved {len(result)} open orders"
                + (f" for {symbol}" if symbol else "")
            )
            return result

        except APIError as e:
            logger.error(f"Failed to get open orders: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting open orders: {e}")
            return []

    def get_order(self, order_id: str) -> Optional[Dict]:
        """
        Get a specific order by ID.

        Args:
            order_id: The order ID to retrieve.

        Returns:
            Dictionary with order details:
                - id: Order ID (str)
                - symbol: Stock symbol (str)
                - qty: Number of shares (int)
                - side: Order side ("buy" or "sell")
                - type: Order type (str)
                - status: Order status (str)
                - stop_price: Stop price if stop order, None otherwise (Optional[float])
            Returns None if order not found.
        """
        try:
            order = self.client.get_order_by_id(order_id)

            result = {
                "id": order.id,
                "symbol": order.symbol,
                "qty": int(order.qty),
                "side": order.side.value,
                "type": order.type.value,
                "status": order.status.value,
                "stop_price": float(order.stop_price) if order.stop_price else None
            }

            logger.debug(f"Order {order_id}: {result}")
            return result

        except APIError as e:
            error_msg = str(e).lower()
            if "order not found" in error_msg:
                logger.debug(f"Order not found: {order_id}")
                return None
            else:
                logger.error(f"Failed to get order {order_id}: {e}")
                return None
        except Exception as e:
            logger.error(f"Unexpected error getting order {order_id}: {e}")
            return None
