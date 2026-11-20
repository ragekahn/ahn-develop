"""Simple Moving Average crossover strategy (reference implementation).

* BUY  when the short SMA crosses above the long SMA (golden cross).
* SELL when the short SMA crosses below the long SMA (death cross).

Order size is fixed at ``order_size`` shares (the engine's risk layer will
cap it to available cash / position).
"""
from __future__ import annotations

from typing import List, Optional

from ..models import Bar, Order, Side
from .base import Strategy


def _sma(bars: List[Bar], window: int, index: int) -> Optional[float]:
    if index + 1 < window:
        return None
    window_bars = bars[index - window + 1 : index + 1]
    return sum(b.close for b in window_bars) / window


class SMACrossoverStrategy(Strategy):
    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        order_size: int = 1,
    ) -> None:
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast = fast_period
        self.slow = slow_period
        self.order_size = int(order_size)

    def generate_signal(
        self, symbol: str, bars: List[Bar]
    ) -> Optional[Order]:
        # We need the previous bar's SMAs too to detect a *cross*.
        min_bars = self.slow + 1
        if len(bars) < min_bars:
            return None

        i_now = len(bars) - 1
        i_prev = len(bars) - 2

        fast_now = _sma(bars, self.fast, i_now)
        slow_now = _sma(bars, self.slow, i_now)
        fast_prev = _sma(bars, self.fast, i_prev)
        slow_prev = _sma(bars, self.slow, i_prev)

        if None in (fast_now, slow_now, fast_prev, slow_prev):
            return None

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        side: Optional[Side] = None
        if crossed_up:
            side = Side.BUY
        elif crossed_down:
            side = Side.SELL

        if side is None:
            return None

        return Order(symbol=symbol, side=side, quantity=self.order_size)
