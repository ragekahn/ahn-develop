"""TossInvestBroker -- Toss Securities (토스증권) implementation of :class:`Broker`.

Orders are submitted, and account/holdings read, through the low-level
:class:`TossInvestClient` (which carries the OAuth token and account header).
The raw JSON payloads are mapped onto the stockbot model objects
(``AccountState`` / ``Position`` / ``Order``).

The client is configured from the environment so this broker can be
constructed with no arguments, as required by the ``Broker`` contract and
``broker_factory``.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..models import (
    AccountState,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Side,
)
from ..data.tossinvest import TossInvestClient
from .base import Broker

# Toss ``orderType`` codes for the KIND (장내/국내) market.
_TOSS_ORDER_TYPE = {
    OrderType.MARKET: 1,  # 시장가 (market)
    OrderType.LIMIT: 2,   # 지정가 (limit)
}

# Toss ``orderStatusCd`` values -> stockbot ``OrderStatus``.
_TOSS_STATUS = {
    "0": OrderStatus.PENDING,   # 접수 (accepted)
    "1": OrderStatus.PENDING,   # 처리중 (processing)
    "2": OrderStatus.FILLED,    # 완료 (filled)
    "3": OrderStatus.CANCELLED, # 취소 (cancelled)
    "4": OrderStatus.REJECTED,  # 거절 (rejected)
    "5": OrderStatus.REJECTED,  # 실패 (failed)
}


def _first_mapping(data: Any) -> Dict[str, Any]:
    """Return the first dict found in *data* (handles list/row payloads)."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
    return {}


def _as_rows(data: Any) -> List[Dict[str, Any]]:
    """Normalise a list/dict payload into a flat list of row mappings."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("holdings", "list", "rows", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [data]
    return []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


class TossInvestBroker(Broker):
    """Toss Securities broker backed by the low-level ``TossInvestClient``.

    Satisfies the :class:`Broker` abstract interface:
    ``get_account``, ``get_positions``, ``place_order`` and ``cancel_order``.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        api_key: Optional[str] = None,
        account_no: Optional[str] = None,
    ) -> None:
        # ``TossInvestClient`` authenticates with OAuth client credentials and
        # resolves the account itself, so it only accepts ``client_id`` /
        # ``client_secret`` (no ``api_key`` / ``account_no``). It does not read
        # the environment on its own, so fall back to the TOSSEST_* variables
        # (explicit arguments take precedence).
        client_id = client_id or os.environ.get("TOSSEST_CLIENT_ID", "")
        client_secret = client_secret or os.environ.get("TOSSEST_CLIENT_SECRET", "")
        self._client = TossInvestClient(client_id=client_id, client_secret=client_secret)

    # -- Broker API ------------------------------------------------------
    def get_account(self) -> AccountState:
        """Return the account's cash and equity as an :class:`AccountState`."""
        seq = self._account_seq()
        data = self._client.get(f"/v1/accounts/{seq}", account=True)
        account = _first_mapping(data)
        cash = _to_float(account.get("availableAmount"))
        hold_value = _to_float(account.get("holdValue"))
        return AccountState(cash=cash, equity=cash + hold_value, currency="KRW")

    def get_positions(self) -> Dict[str, Position]:
        """Return currently held positions keyed by symbol."""
        seq = self._account_seq()
        data = self._client.get(f"/v1/accounts/{seq}/holdings", account=True)
        positions: Dict[str, Position] = {}
        for row in _as_rows(data):
            symbol = str(row.get("ticker") or row.get("tickerNm") or "").strip()
            if not symbol:
                continue
            quantity = _to_int(row.get("qty"))
            avg_price = _to_float(row.get("avgAcqPrc"), _to_float(row.get("prc")))
            positions[symbol] = Position(
                symbol=symbol, quantity=quantity, avg_price=avg_price
            )
        return positions

    def place_order(self, order: Order) -> Order:
        """Submit *order* to Toss and return it with updated status/price/id.

        The passed :class:`Order` is mutated in place (``order_id``, ``status``,
        ``filled_price`` and ``error``) and returned, per the ``Broker``
        contract.
        """
        seq = self._account_seq()
        payload: Dict[str, Any] = {
            "marketType": "KIND",
            "orderType": _TOSS_ORDER_TYPE.get(order.order_type, 1),
            "orderCnclType": 1,  # 1 = 신규 (new) order
            "ticker": order.symbol,
            "orderCnclQty": int(order.quantity),
            "accountSeq": int(seq),
            "side": "1" if order.side is Side.BUY else "2",  # 1=매수, 2=매도
        }
        if order.limit_price is not None:
            payload["orderPrc"] = int(round(float(order.limit_price)))

        result = self._client.post("/v1/orders", body=payload, account=True)
        result = result if isinstance(result, dict) else {}

        order.order_id = str(
            result.get("orderSeq")
            or result.get("orderUid")
            or order.order_id
            or ""
        )
        status_code = str(
            result.get("orderStatusCd") or result.get("orderStatus") or "0"
        )
        order.status = _TOSS_STATUS.get(status_code, OrderStatus.PENDING)
        if result.get("orderPrc") is not None:
            order.filled_price = _to_float(result.get("orderPrc"))
        if order.status in (OrderStatus.REJECTED, OrderStatus.CANCELLED):
            order.error = str(
                result.get("msg") or result.get("error") or "order not accepted"
            )
        return order

    def cancel_order(self, order_id: str) -> None:
        """Cancel a pending order by its Toss ``orderSeq``."""
        seq = (order_id or "").strip()
        if not seq:
            raise ValueError("order_id is required to cancel an order")
        self._client.post(
            f"/v1/orders/{seq}/cancel",
            body={"orderCnclType": 2},  # 2 = 취소 (cancel)
            account=True,
        )
        return None

    # -- helpers ---------------------------------------------------------
    def _account_seq(self) -> int:
        """Ensure the Toss account is resolved and return its sequence number.

        ``ensure_account`` is idempotent: it returns immediately when the
        sequence is already known and otherwise performs the account lookup,
        so it is safe to call before every order.
        """
        self._client.ensure_account()
        return self._client.account_seq
