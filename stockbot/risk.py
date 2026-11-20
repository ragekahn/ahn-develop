"""Risk management: validate and size orders before they reach a broker."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .config import Config
from .logger import get_logger
from .models import AccountState, Order, Side


@dataclass
class RiskDecision:
    """Outcome of a risk check.

    ``approved``  -> the (possibly resized) order may be sent.
    ``rejected``  -> do not send; ``reason`` explains why.
    """

    approved: bool
    order: Optional[Order] = None
    reason: str = ""


class RiskManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.log = get_logger()

    def evaluate(
        self,
        order: Order,
        account: AccountState,
        positions: Dict[str, object],
    ) -> RiskDecision:
        symbol = order.symbol
        position = positions.get(symbol)
        position_qty = int(getattr(position, "quantity", 0)) if position else 0

        # --- reject if no sensible price is available --------------------
        # (The broker fills at the latest close; we use it here for sizing.)
        price = self._last_close(account, order)
        if price is None or price <= 0:
            return RiskDecision(False, reason="no price available for sizing")

        notional = price * order.quantity

        # --- SELL guard: can't sell what we don't hold -------------------
        if order.side is Side.SELL and position_qty < order.quantity:
            if position_qty == 0:
                return RiskDecision(
                    False, reason=f"no position in {symbol} to sell"
                )
            order.quantity = position_qty  # sell all we do hold
            notional = price * order.quantity

        # --- BUY guard: max order notional -------------------------------
        max_notional = self.config.max_order_value
        if max_notional and notional > max_notional:
            scaled = int(max_notional // price)
            if scaled <= 0:
                return RiskDecision(
                    False,
                    reason=f"max_order_value={max_notional} too small for {symbol}",
                )
            self.log.info(
                "Capping %s BUY size %s -> %s (max_order_value)",
                symbol, order.quantity, scaled,
            )
            order.quantity = scaled
            notional = price * scaled

        # --- BUY guard: cash availability -------------------------------
        if order.side is Side.BUY and notional > account.cash:
            affordable = int(account.cash // price)
            if affordable <= 0:
                return RiskDecision(False, reason="insufficient cash")
            self.log.info(
                "Capping %s BUY size %s -> %s (cash)",
                symbol, order.quantity, affordable,
            )
            order.quantity = affordable

        return RiskDecision(True, order=order)

    @staticmethod
    def _last_close(account: AccountState, order: Order) -> Optional[float]:
        # Order doesn't carry a fill price yet; the engine supplies the
        # latest close via a temporary attribute when it knows one.
        return getattr(order, "_reference_price", None)
