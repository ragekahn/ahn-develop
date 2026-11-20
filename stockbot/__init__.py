"""stockbot - a modular, multi-market trading bot framework."""
from .config import Config
from .engine import EngineReport, TradingEngine
from .models import Bar, Order, Position, Signal, AccountState

__version__ = "0.1.0"

__all__ = [
    "Config",
    "TradingEngine",
    "EngineReport",
    "Bar",
    "Order",
    "Position",
    "Signal",
    "AccountState",
    "__version__",
]
