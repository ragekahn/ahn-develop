"""Interactive Brokers (US) broker adapter.

Requires the ``ib_insync`` package and a running IB Gateway / TWS.

    pip install ib_insync

Port ``7497`` is the paper (simulated) gateway, ``7496`` is the live one.
Pick via ``IB_PORT`` in ``.env``.
"""
from __future__ import annotations

from typing import Dict

from ..logger import get_logger
from ..models import (
    AccountState,
    Order,
    OrderStatus,
    Position,
    Side,
)
from .base import Broker


class IBKRBroker(Broker):
    """Live/paper order execution through Interactive Brokers."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        try:
            from ib_insync import IB  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "IBKRBroker requires the 'ib_insync' package. "
                "Install it with: pip install ib_insync"
            ) from exc

        from ib_insync import IB

        self.log = get_logger()
        self._ib = IB()
        self._ib.connect(host, port, clientId=client_id)
        if not self._ib.isConnected:
            raise RuntimeError(
                f"Could not connect to IB at {host}:{port}. "
                "Is IB Gateway / TWS running and API enabled?"
            )
        self.log.info("Connected to IBKR (%s:%s, clientId=%s)", host, port, client_id)

    def _contract(self, symbol: str):
        from ib_insync import Stock

        return Stock(symbol, "SMART", "USD")

    def get_account(self) -> AccountState:
        net_liq = None
        cash = None
        for row in self._ib.accountValues():
            if row.tag == "NetLiquidation":
                net_liq = float(row.value)
            if row.tag == "CashBalance":
                cash = float(row.value)
        cash = cash if cash is not None else 0.0
        equity = net_liq if net_liq is not None else cash
        return AccountState(cash=cash, equity=equity, currency="USD")

    def get_positions(self) -> Dict[str, Position]:
        positions: Dict[str, Position] = {}
        for p in self._ib.positions():
            if p.position == 0:
                continue
            positions[p.contract.symbol] = Position(
                symbol=p.contract.symbol,
                quantity=int(p.position),
                avg_price=float(p.avgPrice),
            )
        return positions

    def place_order(self, order: Order) -> Order:
        from ib_insync import LimitOrder, MarketOrder, Order as IBOrder

        contract = self._contract(order.symbol)
        ib_order = IBOrder()
        ib_order.action = order.side.value  # "buy" / "sell"
        ib_order.totalQuantity = abs(int(order.quantity))

        if order.limit_price is not None:
            ib_order.orderType = "LMT"
            ib_order.lmtPrice = float(order.limit_price)
        else:
            ib_order.orderType = "MKT"

        try:
            trade = self._ib.placeOrder(contract, ib_order)
            order.order_id = str(trade.order.orderId)
            order.status = OrderStatus.PENDING
            return order
        except Exception as exc:  # pragma: no cover - depends on env
            order.status = OrderStatus.REJECTED
            order.error = str(exc)
            self.log.error("IBKR order rejected for %s: %s", order.symbol, exc)
            return order

    def cancel_order(self, order_id: str) -> None:
        for trade in self._ib.openTrades():
            if str(trade.order.orderId) == order_id:
                self._ib.cancelOrder(trade.order)
                return
        self.log.warning("No open IBKR order found with id %s", order_id)
