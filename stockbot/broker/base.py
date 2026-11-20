"""Broker interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from ..models import AccountState, Order, Position


class Broker(ABC):
    """Abstract broker: account info + order execution.

    Market data is handled separately by ``DataProvider`` so that data
    source and order execution can be mixed independently (e.g. Korean
    quotes from Naver but orders through Kiwoom).
    """

    @abstractmethod
    def get_account(self) -> AccountState:
        """Return current account cash/equity."""

    @abstractmethod
    def get_positions(self) -> Dict[str, Position]:
        """Return currently held positions keyed by symbol."""

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """Submit an order. Returns the order with an updated status.

        Implementations should mutate and return the passed order so the
        caller can inspect ``status`` / ``filled_price`` / ``error``.
        """

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        """Cancel a pending order by id."""
