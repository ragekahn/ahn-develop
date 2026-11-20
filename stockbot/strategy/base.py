"""Strategy interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Bar, Order, Side


class Strategy(ABC):
    """Turns a series of bars into an intended action.

    Implementations stay pure: they return an ``Order`` with a side and
    quantity, and let the engine/risk layer validate and execute it.
    """

    @abstractmethod
    def generate_signal(
        self, symbol: str, bars: List[Bar]
    ) -> Optional[Order]:
        """Return a desired Order, or ``None`` if no action is warranted."""
