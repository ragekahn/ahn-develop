"""In-memory paper broker for simulation & testing."""
from __future__ import annotations

from typing import Callable, Dict, Optional

from ..models import AccountState, Order, OrderStatus, Position, Side
from .base import Broker


class PaperBroker(Broker):
    """A fully functional simulated broker.

    Fills are executed at a reference price supplied via ``price_source``
    (or at the order's ``limit_price`` when it is a limit order). Cash and
    positions are tracked in memory.
    """

    def __init__(
        self,
        initial_cash: float,
        price_source: Optional[Callable[[str], Optional[float]]] = None,
    ) -> None:
        self._cash = float(initial_cash)
        self._positions: Dict[str, Position] = {}
        self._price_source = price_source
        self._order_seq = 0

    # -- helpers ---------------------------------------------------------
    def _reference_price(self, order: Order) -> Optional[float]:
        if order.limit_price is not None:
            return order.limit_price
        if self._price_source is not None:
            price = self._price_source(order.symbol)
            if price is not None:
                return float(price)
        pos = self._positions.get(order.symbol)
        return pos.avg_price if pos else None

    # -- Broker API ------------------------------------------------------
    def get_account(self) -> AccountState:
        positions_value = sum(
            p.quantity * (self._reference_price_for_symbol(p.symbol))
            for p in self._positions.values()
        )
        equity = self._cash + positions_value
        return AccountState(cash=self._cash, equity=equity)

    def get_positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    def place_order(self, order: Order) -> Order:
        self._order_seq += 1
        order.order_id = f"PAPER-{self._order_seq:06d}"

        price = self._reference_price(order)
        if price is None or price <= 0:
            order.status = OrderStatus.REJECTED
            order.error = "no reference price available"
            return order

        cost = price * order.quantity

        if order.side is Side.BUY:
            if cost > self._cash:
                order.status = OrderStatus.REJECTED
                order.error = "insufficient cash"
                return order
            self._cash -= cost
            pos = self._positions.get(order.symbol)
            if pos is None:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol, quantity=order.quantity, avg_price=price
                )
            else:
                new_qty = pos.quantity + order.quantity
                pos.avg_price = (
                    pos.avg_price * pos.quantity + price * order.quantity
                ) / new_qty
                pos.quantity = new_qty
        else:  # SELL
            pos = self._positions.get(order.symbol)
            if pos is None or pos.quantity < order.quantity:
                order.status = OrderStatus.REJECTED
                order.error = "insufficient position"
                return order
            self._cash += cost
            pos.quantity -= order.quantity
            if pos.quantity == 0:
                del self._positions[order.symbol]

        order.status = OrderStatus.FILLED
        order.filled_price = price
        return order

    def cancel_order(self, order_id: str) -> None:
        # Paper broker executes synchronously; nothing to cancel.
        return None

    # -- internals -------------------------------------------------------
    def _reference_price_for_symbol(self, symbol: str) -> float:
        if self._price_source is not None:
            p = self._price_source(symbol)
            if p is not None:
                return float(p)
        pos = self._positions.get(symbol)
        return pos.avg_price if pos else 0.0
