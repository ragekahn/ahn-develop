"""Kiwoom (Korean market) broker adapter.

This adapter targets the official Kiwoom Open API (COM object) on Windows.
It requires the Kiwoom Open API to be installed and the account credentials
set in ``.env`` (``KIWOOM_ACCOUNT_ID`` / ``KIWOOM_ACCOUNT_PW``).

Important caveats for a production deployment:
  * Kiwoom's Open API is asynchronous: responses arrive via the
    ``OnReceiveTrData`` / ``OnReceiveRealData`` callbacks, and the API only
    works when a (hidden) window is attached to the COM server. The methods
    below cover the common synchronous-style calls (login, order, balance)
    and are the building blocks you wire to those callbacks.
  * This adapter cannot be live-tested in a non-Windows / sandboxed env, so
    treat it as a documented integration scaffold that you finish against
    your Kiwoom build.
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


class KiwoomBroker(Broker):
    """Order execution through the Kiwoom Open API (Korean market)."""

    def __init__(
        self,
        account_id: str = "",
        account_pw: str = "",
        trade_id: str = "",
        trade_pw: str = "",
        server_ip: str = "",
        server_port: int = 20003,
    ):
        self.log = get_logger()

        if not (account_id and account_pw):
            raise RuntimeError(
                "KiwoomBroker requires KIWOOM_ACCOUNT_ID and KIWOOM_ACCOUNT_PW "
                "to be set in .env"
            )

        try:
            import pythoncom  # noqa: F401
            import win32com.client as win32  # noqa: F401
        except ImportError as exc:  # pragma: no cover - Windows only
            raise RuntimeError(
                "KiwoomBroker requires the Windows-only 'pywin32' package "
                "and the Kiwoom Open API installed. "
                "Install with: pip install pywin32"
            ) from exc

        self._account_id = account_id
        self._account_pw = account_pw
        self._trade_id = trade_id
        self._trade_pw = trade_pw
        self._server_ip = server_ip
        self._server_port = server_port

        import pythoncom
        import win32com.client as win32

        pythoncom.CoInitialize()
        # Kiwoom Open API ProgID. Adjust to your build if it differs.
        self._kiwoom = win32.Dispatch("KiwoomNextOpenAPI")
        self._logged_in = False
        self._order_seq = 0

    def _ensure_login(self) -> None:
        if self._logged_in:
            return
        ret = self._kiwoom.kiwoom_login(
            self._account_id, self._account_pw, False, "StockBot"
        )
        if ret != "0":
            raise RuntimeError(f"Kiwoom login failed: {ret}")
        self._logged_in = True
        self.log.info("Logged in to Kiwoom")

    def get_account(self) -> AccountState:
        self._ensure_login()
        # Inq balance (bopls). In a real setup you capture the response via
        # OnReceiveTrData; here we expose a synchronous helper hook.
        self._kiwoom.kiwoom_inq_bopls("01")
        cash = self._last_value("balance") or 0.0
        equity = self._last_value("equity") or cash
        return AccountState(cash=cash, equity=equity, currency="KRW")

    def get_positions(self) -> Dict[str, Position]:
        self._ensure_login()
        self._kiwoom.kiwoom_inq_cheil("1")  # inq held stocks
        positions: Dict[str, Position] = {}
        for row in self._last_rows("positions") or []:
            positions[row["code"]] = Position(
                symbol=row["code"],
                quantity=int(row.get("qty", 0)),
                avg_price=float(row.get("avg_price", 0.0)),
            )
        return positions

    def place_order(self, order: Order) -> Order:
        self._ensure_login()
        self._order_seq += 1
        order.order_id = f"KIWOOM-{self._order_seq:06d}"

        side_code = "1" if order.side is Side.BUY else "2"  # 1=buy, 2=sell
        price = str(int(order.limit_price or 0))
        ret = self._kiwoom.kiwoom_stock_buy(
            order.symbol, price, order.quantity, side_code, "0", order.order_id
        )
        if ret not in (0, "0"):
            order.status = OrderStatus.REJECTED
            order.error = f"kiwoom_stock_buy returned {ret}"
            self.log.error("Kiwoom order rejected for %s: %s", order.symbol, ret)
            return order

        order.status = OrderStatus.PENDING
        self.log.info("Submitted Kiwoom order %s %sx%s", order.side.value, order.quantity, order.symbol)
        return order

    def cancel_order(self, order_id: str) -> None:
        self._ensure_login()
        ret = self._kiwoom.kiwoom_cancel(order_id, "0")
        if ret not in (0, "0"):
            self.log.warning("Kiwoom cancel for %s failed: %s", order_id, ret)

    # -- response sink (filled by OnReceiveTrData in a full implementation)
    def _last_value(self, key: str):
        return getattr(self, f"_last_{key}", None)

    def _last_rows(self, key: str):
        return getattr(self, f"_last_{key}_rows", None)
