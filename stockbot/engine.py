"""Trading engine: data -> strategy -> risk -> broker."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .broker.base import Broker
from .config import Config
from .data.base import DataProvider
from .logger import get_logger
from .models import AccountState, Order, OrderStatus, Position, Side
from .risk import RiskManager
from .strategy.base import Strategy


@dataclass
class TradeResult:
    symbol: str
    side: Side
    quantity: int
    order_id: Optional[str] = None
    status: Optional[OrderStatus] = None
    price: Optional[float] = None
    reason: str = ""


@dataclass
class EngineReport:
    account_before: Optional[AccountState] = None
    account_after: Optional[AccountState] = None
    trades: List[TradeResult] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            (
                f"Account before: cash={self.account_before.cash:,.0f} "
                f"equity={self.account_before.equity:,.0f}"
                if self.account_before
                else "Account before: n/a"
            ),
            (
                f"Account after : cash={self.account_after.cash:,.0f} "
                f"equity={self.account_after.equity:,.0f}"
                if self.account_after
                else "Account after : n/a"
            ),
            f"Trades        : {len(self.trades)}  |  Skipped: {len(self.skipped)}",
        ]
        for t in self.trades:
            price = f"@ {t.price:,.2f}" if t.price else ""
            lines.append(
                f"  - {t.side.value.upper():>4} {t.quantity:>5} {t.symbol:<10} "
                f"{price}  [{t.status.value if t.status else 'n/a'}] {t.reason}"
            )
        for s in self.skipped:
            lines.append(f"  ! skipped: {s}")
        return "\n".join(lines)


class TradingEngine:
    """Orchestrates evaluation cycles over the watchlist."""

    def __init__(
        self,
        config: Config,
        data: DataProvider,
        strategy: Strategy,
        broker: Broker,
        risk: Optional[RiskManager] = None,
    ) -> None:
        self.config = config
        self.data = data
        self.strategy = strategy
        self.broker = broker
        self.risk = risk or RiskManager(config)
        self.log = get_logger()

    def run_cycle(self) -> EngineReport:
        report = EngineReport(account_before=self._safe_account())
        positions = self._safe_positions()

        for symbol in self.config.symbols:
            self.log.info("Evaluating %s", symbol)
            try:
                bars = self.data.get_bars(
                    symbol, self.config.interval, self.config.bars_limit
                )
            except Exception as exc:
                self.log.error("Data fetch failed for %s: %s", symbol, exc)
                report.skipped.append(f"{symbol}: data error ({exc})")
                continue

            if not bars:
                self.log.warning("No bars returned for %s", symbol)
                report.skipped.append(f"{symbol}: no data")
                continue

            latest_close = bars[-1].close

            try:
                order = self.strategy.generate_signal(symbol, bars)
            except Exception as exc:
                self.log.error("Strategy error for %s: %s", symbol, exc)
                report.skipped.append(f"{symbol}: strategy error ({exc})")
                continue

            if order is None:
                self.log.info("No signal for %s", symbol)
                continue

            order._reference_price = latest_close  # type: ignore[attr-defined]

            decision = self.risk.evaluate(
                order,
                report.account_before or AccountState(cash=0.0, equity=0.0),
                positions,
            )
            if not decision.approved:
                self.log.info(
                    "Rejected %s %s: %s", order.side.value, symbol, decision.reason
                )
                report.skipped.append(f"{symbol}: {decision.reason}")
                continue

            if self.config.dry_run:
                self.log.info(
                    "[DRY_RUN] Would %s %sx %s",
                    order.side.value, order.quantity, symbol,
                )
                report.trades.append(
                    TradeResult(
                        symbol=symbol,
                        side=order.side,
                        quantity=order.quantity,
                        status=OrderStatus.REJECTED,
                        price=latest_close,
                        reason="DRY_RUN (not sent)",
                    )
                )
                continue

            try:
                filled = self.broker.place_order(order)
            except Exception as exc:
                self.log.error("Order execution error for %s: %s", symbol, exc)
                report.skipped.append(f"{symbol}: execution error ({exc})")
                continue

            report.trades.append(
                TradeResult(
                    symbol=symbol,
                    side=order.side,
                    quantity=order.quantity,
                    order_id=filled.order_id,
                    status=filled.status,
                    price=filled.filled_price,
                    reason=filled.error or "",
                )
            )

        report.account_after = self._safe_account()
        return report

    def run(
        self, cycles: int = 1, interval_seconds: int = 30
    ) -> List[EngineReport]:
        reports: List[EngineReport] = []
        for i in range(cycles):
            self.log.info("=== Cycle %s/%s ===", i + 1, cycles)
            reports.append(self.run_cycle())
            if i < cycles - 1 and interval_seconds > 0:
                time.sleep(interval_seconds)
        return reports

    def _safe_account(self) -> Optional[AccountState]:
        try:
            return self.broker.get_account()
        except Exception as exc:
            self.log.warning("Could not fetch account: %s", exc)
            return None

    def _safe_positions(self) -> Dict[str, Position]:
        try:
            return self.broker.get_positions()
        except Exception as exc:
            self.log.warning("Could not fetch positions: %s", exc)
            return {}

