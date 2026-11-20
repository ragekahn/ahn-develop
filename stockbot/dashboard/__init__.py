"""stockbot web dashboard.

A zero-dependency HTTP server (stdlib ``http.server`` only) plus a single-page
front-end that visualises market data (bars + SMA) and broker account /
positions using the exact same classes the trading engine uses.

Run:
    python -m stockbot.dashboard --port 8501
"""
from .server import build_server, main

__all__ = ["build_server", "main"]