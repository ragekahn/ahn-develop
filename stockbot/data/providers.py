"""Market data providers.

* Korean (KOSPI/KOSDAQ) - Naver Finance public API (no key required).
* US                    - ``yfinance`` (optional dependency).
* ``MultiMarketDataProvider`` routes each symbol to the right source.

All providers degrade gracefully: if a network call fails they raise a
clear error, and the engine logs & skips that symbol.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import List, Optional

from ..logger import get_logger
from ..models import Bar
from .base import DataProvider, is_korean_symbol

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _http_get_json(url: str, timeout: float = 15.0) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body.decode("utf-8"))


class NaverDataProvider(DataProvider):
    """Korean market data via Naver Finance (``api.finance.naver.com``)."""

    BASE_URL = "https://api.finance.naver.com/siseJson.naver"

    def __init__(self) -> None:
        self.log = get_logger()

    def get_bars(
        self, symbol: str, interval: str = "1d", limit: int = 60
    ) -> List[Bar]:
        if interval not in {"1d", "day"}:
            # Naver intraday endpoint differs; fall back to daily for MVP.
            self.log.warning(
                "NaverDataProvider only supports daily bars for MVP, "
                "ignoring interval=%s", interval
            )
        params = {
            "symbol": symbol,
            "requestType": "1",
            "timeframe": "day",
            "isFirst": "y",
        }
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        data = _http_get_json(url)
        rows = data if isinstance(data, list) else data.get("result", [])
        rows = rows[-limit:]
        bars: List[Bar] = []
        for row in rows:
            ts = datetime.strptime(
                str(row["time"]), "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return bars


class YFinanceDataProvider(DataProvider):
    """US market data via ``yfinance`` (optional dependency)."""

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "YFinanceDataProvider requires the 'yfinance' package. "
                "Install it with: pip install yfinance"
            ) from exc
        self.log = get_logger()

    def get_bars(
        self, symbol: str, interval: str = "1d", limit: int = 60
    ) -> List[Bar]:
        import yfinance as yf

        period_map = {"1d": f"{limit + 5}d", "60m": f"{limit}d"}
        interval_map = {"1d": "1d", "60m": "60m"}
        period = period_map.get(interval, "60d")
        bar_interval = interval_map.get(interval, "1d")

        df = yf.Ticker(symbol).history(period=period, interval=bar_interval)
        if df is None or df.empty:
            return []
        bars: List[Bar] = []
        for ts, row in df.tail(limit).iterrows():
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=ts.to_pydatetime().replace(tzinfo=timezone.utc),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        return bars


class MultiMarketDataProvider(DataProvider):
    """Routes each symbol to Naver (Korean) or yfinance (US)."""

    def __init__(self) -> None:
        self.log = get_logger()
        self._kr: Optional[NaverDataProvider] = None
        self._us: Optional[YFinanceDataProvider] = None

    def _kr_provider(self) -> NaverDataProvider:
        if self._kr is None:
            self._kr = NaverDataProvider()
        return self._kr

    def _us_provider(self) -> YFinanceDataProvider:
        if self._us is None:
            self._us = YFinanceDataProvider()
        return self._us

    def get_bars(
        self, symbol: str, interval: str = "1d", limit: int = 60
    ) -> List[Bar]:
        provider = self._kr_provider() if is_korean_symbol(symbol) else self._us_provider()
        return provider.get_bars(symbol, interval, limit)
