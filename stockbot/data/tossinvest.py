"""Toss Invest (tois) market-data provider.

Real-time spot prices and OHLCV bars from the Toss Invest REST API (v1).
Credentials come from :class:`..tossinvest_client.TossInvestClient` via
``.env`` (``TOSSEST_CLIENT_ID`` / ``TOSSEST_CLIENT_SECRET``).

Endpoint map (v1 market data):
  * GET /v1/prices/{symbol}/spot          -> current price
  * GET /v1/prices/{symbol}/chart/day     -> daily bars
  * GET /v1/prices/{symbol}/chart/week    -> weekly bars
  * GET /v1/prices/{symbol}/chart/month   -> monthly bars
  * GET /v1/prices/{symbol}/chart/hour    -> hourly bars
  * GET /v1/prices/{symbol}/chart?period= -> intraday (1/5/10/15/30 min)

Interval tokens (case-sensitive for month vs. minute):
  * ``1d``/``1D`` daily, ``1w``/``1W`` weekly, ``1M``/``1mo`` monthly,
    ``1h``/``1H`` hourly, ``1m``/``5m``/``10m``/``15m``/``30m`` intraday.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ..logger import get_logger
from ..models import Bar
from ..tossinvest_client import TossInvestClient
from .base import DataProvider

_MONTH_TOKENS = {"1M", "1mo", "mo", "month", "monthly"}
_MINUTE_TOKENS = {"1m", "5m", "10m", "15m", "30m"}


def _resolve_chart(interval: str) -> Tuple[str, Optional[int]]:
    """Map an interval token to ``(chart_path, minute_period)``.

    ``chart_path`` is ``"day"`` / ``"week"`` / ``"month"`` / ``"hour"`` for the
    dedicated endpoints, or ``"chart"`` with ``minute_period`` set for intraday.
    """
    token = (interval or "1d").strip()
    if token in ("1d", "1D", "d", "day", "daily"):
        return ("day", None)
    if token in ("1w", "1W", "w", "week", "weekly"):
        return ("week", None)
    if token in _MONTH_TOKENS:
        return ("month", None)
    if token in ("1h", "1H", "h", "hour", "hourly"):
        return ("hour", None)
    if token in _MINUTE_TOKENS:
        return ("chart", int(token[:-1]))
    raise ValueError(f"Unsupported Toss Invest interval: {interval!r}")


def _parse_ts(value) -> datetime:
    """Parse an epoch (seconds/ms) or ISO-8601 timestamp to a UTC datetime."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:  # milliseconds
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(value).strip()
    if text.isdigit() and len(text) >= 12:
        return datetime.fromtimestamp(int(text) / 1000.0, tz=timezone.utc)
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class TossInvestDataProvider(DataProvider):
    """Market data access through the Toss Invest API."""

    def __init__(self, client_id: str = "", client_secret: str = "") -> None:
        self.log = get_logger()
        # Empty creds -> TossInvestClient falls back to TOSSEST_* env vars.
        self._client = TossInvestClient(
            client_id=client_id, client_secret=client_secret
        )

    def get_price(self, symbol: str) -> Optional[float]:
        try:
            resp = self._client.get(f"/v1/prices/{symbol}/spot", account=False)
        except Exception as exc:  # pragma: no cover - network
            self.log.warning("Toss Invest price for %s failed: %s", symbol, exc)
            return None
        if isinstance(resp, dict):
            for key in ("current_price", "price", "latest_price"):
                if resp.get(key) is not None:
                    try:
                        return float(resp[key])
                    except (TypeError, ValueError):
                        continue
        if isinstance(resp, (int, float)):
            return float(resp)
        return None

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 100) -> List[Bar]:
        try:
            chart, minutes = _resolve_chart(interval)
        except ValueError:
            self.log.warning("Unsupported interval %r for %s", interval, symbol)
            return []

        query: List[str] = []
        if limit and limit > 0:
            query.append(f"limit={int(limit)}")
        if minutes is not None:
            path = f"/v1/prices/{symbol}/chart"
            query.append(f"period={minutes}")
        else:
            path = f"/v1/prices/{symbol}/chart/{chart}"
        if query:
            path = f"{path}?{'&'.join(query)}"

        try:
            rows = self._client.get(path, account=False)
        except Exception as exc:  # pragma: no cover - network
            self.log.warning("Toss Invest bars for %s failed: %s", symbol, exc)
            return []
        if not isinstance(rows, list):
            return []

        bars: List[Bar] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                o = float(row.get("open", 0))
                h = float(row.get("high", 0))
                lo = float(row.get("low", 0))
                c = float(row.get("close", 0))
                v = float(row.get("volume", 0) or 0)
            except (TypeError, ValueError):
                continue
            bars.append(Bar(_parse_ts(row.get("timestamp")), o, h, lo, c, v))

        bars.sort(key=lambda b: b.timestamp)  # chronological, so [-1] is latest
        if limit and limit > 0 and len(bars) > limit:
            bars = bars[-int(limit):]
        return bars