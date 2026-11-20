"""Core domain models for the trading bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Bar:
    """A single OHLCV price bar."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def price(self) -> float:
        """Most recent price (close of the bar)."""
        return self.close


@dataclass
class Signal:
    """A trading decision produced by a strategy."""

    symbol: str
    side: Side
    strength: float = 1.0  # 0.0 ~ 1.0
    reason: str = ""


@dataclass
class Position:
    """A currently held position in a single symbol."""

    symbol: str
    quantity: int
    avg_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.avg_price


@dataclass
class AccountState:
    """Broker account summary."""

    cash: float
    equity: float
    currency: str = "USD"


@dataclass
class Order:
    """An order to be (or already) placed with a broker."""

    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    error: Optional[str] = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
