"""Lightweight stockbot dashboard server.

Standard-library only (``http.server``). Exposes a small JSON API and serves
a single-page front-end from ``static/``. Market data and broker state are
sourced from the real ``stockbot`` classes.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from ..broker import make_broker
from ..config import Config
from ..data import MultiMarketDataProvider, is_korean_symbol
from ..logger import get_logger
from ..models import Bar, Position

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_log = get_logger()


def compute_sma(closes: List[float], window: int) -> List[Optional[float]]:
    """Simple moving average aligned to ``closes``. None before ``window`` samples."""
    result: List[Optional[float]] = [None] * len(closes)
    if window <= 0 or len(closes) < window:
        return result
    running = sum(closes[:window])
    result[window - 1] = running / window
    for i in range(window, len(closes)):
        running += closes[i] - closes[i - window]
        result[i] = running / window
    return result


def _bar_to_dict(bar: Bar) -> Dict[str, object]:
    return {
        "timestamp": bar.timestamp.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def _position_to_dict(pos: Position) -> Dict[str, object]:
    return {
        "symbol": pos.symbol,
        "quantity": pos.quantity,
        "avg_price": pos.avg_price,
    }


def _int_param(params: Dict[str, List[str]], key: str, default: int,
               min_val: int = 1, max_val: int = 500) -> int:
    raw = params.get(key, [str(default)])[0]
    try:
        return max(min_val, min(max_val, int(raw)))
    except (TypeError, ValueError):
        return default


class _DashboardState:
    """Shared state handed to every request handler."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.data_provider = MultiMarketDataProvider()
        self.broker = make_broker(config, data_provider=self.data_provider)


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serves static files + ``/api/*`` JSON endpoints."""

    server_version = "StockbotDashboard/1.0"
    protocol_version = "HTTP/1.1"
    state: "_DashboardState"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, fmt: str, *args: object) -> None:  # pragma: no cover
        _log.debug("HTTP %s", fmt % args)

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int) -> None:
        self._send_json({"error": message}, status=status)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        params = parse_qs(parsed.query)
        try:
            if route == "/api/health":
                self._send_json({"status": "ok",
                                 "time": datetime.now(timezone.utc).isoformat()})
            elif route == "/api/config":
                self._send_json({
                    "broker": self.state.config.broker,
                    "interval": self.state.config.interval,
                    "timeframe": self.state.config.lookback,
                    "symbols": list(self.state.config.symbols),
                    "initial_cash": self.state.config.initial_cash,
                })
            elif route == "/api/bars":
                self._handle_bars(params)
            elif route == "/api/account":
                self._handle_account()
            else:
                if route == "/":
                    self.path = "/index.html"
                super().do_GET()
                return
        except Exception as exc:
            self._send_error_json(f"{type(exc).__name__}: {exc}", 500)

    def _handle_bars(self, params: Dict[str, List[str]]) -> None:
        symbol = (params.get("symbol", [None])[0] or "").strip()
        if not symbol:
            self._send_error_json("query parameter 'symbol' is required", 400)
            return
        interval = params.get("interval", [self.state.config.interval])[0]
        limit = _int_param(params, "limit", self.state.config.lookback, 10, 500)
        sma_short = _int_param(params, "sma_short", 20, 1, 200)
        sma_long = _int_param(params, "sma_long", 50, 1, 500)

        bars = self.state.data_provider.get_bars(symbol, interval, limit)
        closes = [b.close for b in bars]
        self._send_json({
            "symbol": symbol,
            "is_korean": is_korean_symbol(symbol),
            "bars": [_bar_to_dict(b) for b in bars],
            "sma_short": compute_sma(closes, sma_short),
            "sma_long": compute_sma(closes, sma_long),
            "sma_windows": {"short": sma_short, "long": sma_long},
        })

    def _handle_account(self) -> None:
        account = self.state.broker.get_account()
        positions = self.state.broker.get_positions()
        self._send_json({
            "cash": account.cash,
            "equity": account.equity,
            "positions": [_position_to_dict(p) for p in positions.values()],
        })


def build_server(host: str, port: int,
                 config: Optional[Config] = None) -> ThreadingHTTPServer:
    cfg = config or Config()
    state = _DashboardState(cfg)
    DashboardHandler.state = state  # type: ignore[attr-defined]
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer((host, port), DashboardHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description="stockbot dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--broker", default="paper",
                        choices=["paper", "ibkr", "kiwoom", "tossinvest"])
    parser.add_argument("--symbols", default="AAPL,MSFT,GOOGL,005930,000660")
    parser.add_argument("--cash", type=float, default=100_000.0)
    args = parser.parse_args()

    config = Config(
        interval="1d",
        lookback=90,
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        broker=args.broker,
        initial_cash=args.cash,
    )

    try:
        server = build_server(args.host, args.port, config)
    except OSError as exc:
        print(f"[error] cannot bind {args.host}:{args.port} - {exc}", flush=True)
        return 1

    url = f"http://{args.host}:{args.port}"
    print(f"[stockbot] dashboard listening on {url}", flush=True)
    print(f"[stockbot] broker={config.broker}  symbols={config.symbols}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[stockbot] shutting down", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())