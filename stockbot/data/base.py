"""Market data interface."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List

from ..models import Bar


class DataProvider(ABC):
    """Provides OHLCV bars for a symbol."""

    @abstractmethod
    def get_bars(
        self, symbol: str, interval: str = "1d", limit: int = 60
    ) -> List[Bar]:
        """Return up to ``limit`` most recent bars, oldest -> newest."""


_KR_CODE_RE = re.compile(r"^\d{6}$")


def is_korean_symbol(symbol: str) -> bool:
    """Heuristic: 6-digit codes are Korean (e.g. 005930), letters are US (AAPL)."""
    return bool(_KR_CODE_RE.match(symbol.strip()))
