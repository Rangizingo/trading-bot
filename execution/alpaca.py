"""Alpaca trading client."""
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

# Load .env from VV7 project (where keys are stored)
load_dotenv("C:/Users/User/Documents/AI/VV7/.env")

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False


@dataclass
class AlpacaPosition:
    """Alpaca position info."""
    symbol: str
    qty: int
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float


@dataclass
class AlpacaOrder:
    """Alpaca order info."""
    id: str
    symbol: str
    qty: int
    side: str
    status: str
    filled_qty: int
    filled_avg_price: Optional[float]
    submitted_at: datetime


@dataclass
class AlpacaAccount:
    """Alpaca account info."""
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float


class AlpacaClient:
    """Client for Alpaca paper/live trading."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True
    ):
        if not ALPACA_AVAILABLE:
            raise ImportError("alpaca-py not installed. Run: pip install alpaca-py")

        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        self.paper = paper

        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca API keys not found. Set ALPACA_API_KEY and ALPACA_SECRET_KEY")

        self.client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=paper
        )

    def get_account(self) -> AlpacaAccount:
        """Get account information."""
        account = self.client.get_account()
        return AlpacaAccount(
            equity=float(account.equity),
            cash=float(account.cash),
            buying_power=float(account.buying_power),
            portfolio_value=float(account.portfolio_value)
        )

    def get_positions(self) -> List[AlpacaPosition]:
        """Get all open positions."""
        positions = self.client.get_all_positions()
        return [
            AlpacaPosition(
                symbol=p.symbol,
                qty=int(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                market_value=float(p.market_value),
                unrealized_pl=float(p.unrealized_pl),
                unrealized_plpc=float(p.unrealized_plpc)
            )
            for p in positions
        ]

    def get_position(self, symbol: str) -> Optional[AlpacaPosition]:
        """Get position for a symbol."""
        try:
            p = self.client.get_open_position(symbol)
            return AlpacaPosition(
                symbol=p.symbol,
                qty=int(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                market_value=float(p.market_value),
                unrealized_pl=float(p.unrealized_pl),
                unrealized_plpc=float(p.unrealized_plpc)
            )
        except Exception:
            return None

    def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: str = "buy"
    ) -> Optional[AlpacaOrder]:
        """Submit a market order."""
        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY
            )

            order = self.client.submit_order(order_data)

            return AlpacaOrder(
                id=str(order.id),
                symbol=order.symbol,
                qty=int(order.qty),
                side=order.side.value,
                status=order.status.value,
                filled_qty=int(order.filled_qty) if order.filled_qty else 0,
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
                submitted_at=order.submitted_at
            )
        except Exception as e:
            print(f"Order failed: {e}")
            return None

    def close_position(self, symbol: str) -> Optional[AlpacaOrder]:
        """Close position for a symbol."""
        try:
            order = self.client.close_position(symbol)
            return AlpacaOrder(
                id=str(order.id),
                symbol=order.symbol,
                qty=int(order.qty),
                side=order.side.value,
                status=order.status.value,
                filled_qty=int(order.filled_qty) if order.filled_qty else 0,
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
                submitted_at=order.submitted_at
            )
        except Exception as e:
            print(f"Close position failed: {e}")
            return None

    def close_all_positions(self) -> bool:
        """Close all open positions."""
        try:
            self.client.close_all_positions(cancel_orders=True)
            return True
        except Exception as e:
            print(f"Close all failed: {e}")
            return False

    def get_order(self, order_id: str) -> Optional[AlpacaOrder]:
        """Get order by ID."""
        try:
            order = self.client.get_order_by_id(order_id)
            return AlpacaOrder(
                id=str(order.id),
                symbol=order.symbol,
                qty=int(order.qty),
                side=order.side.value,
                status=order.status.value,
                filled_qty=int(order.filled_qty) if order.filled_qty else 0,
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
                submitted_at=order.submitted_at
            )
        except Exception:
            return None

    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        try:
            clock = self.client.get_clock()
            return clock.is_open
        except Exception:
            return False
