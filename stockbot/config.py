"""Configuration loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass
class Config:
    """Runtime configuration for the trading engine."""

    broker: str = "paper"  # paper | kiwoom | ibkr
    symbols: List[str] = field(default_factory=list)
    interval: str = "1d"
    lookback: int = 60
    bars_limit: int = 60
    max_order_value: Optional[float] = None  # optional notional cap per order

    initial_cash: float = 100_000.0
    max_position_pct: float = 0.20  # per-symbol exposure as % of equity
    max_positions: int = 5
    stop_loss_pct: float = 0.05  # 5% below avg cost triggers a full sell

    dry_run: bool = True  # when True, signals are logged but no orders placed

    # --- Kiwoom (Korean market) ---
    kiwoom_account_id: str = ""
    kiwoom_account_pw: str = ""
    kiwoom_trade_id: str = ""
    kiwoom_trade_pw: str = ""
    kiwoom_server_ip: str = ""
    kiwoom_server_port: int = 20003

    # --- IBKR (US market) ---
    ib_host: str = "127.0.0.1"
    ib_port: int = 7497  # 7497 = paper, 7496 = live
    ib_client_id: int = 1

    @classmethod
    def from_env(cls, dotenv_path: str | None = None) -> "Config":
        load_dotenv(dotenv_path)
        symbols_raw = os.getenv("SYMBOLS", "")
        symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]

        interval = os.getenv("INTERVAL", "1d")
        if interval in {"intraday", "minute", "60m", "60", "1h"}:
            interval = "60m"

        return cls(
            broker=os.getenv("BROKER", "paper").strip().lower(),
            symbols=symbols,
            interval=interval,
            lookback=_env_int("LOOKBACK", 60),
            bars_limit=_env_int("BARS_LIMIT", 60),
            max_order_value=(
                float(v)
                if (v := os.getenv("MAX_ORDER_VALUE", "").strip())
                else None
            ),
            initial_cash=_env_float("INITIAL_CASH", 100_000.0),
            max_position_pct=_env_float("MAX_POSITION_PCT", 0.20),
            max_positions=_env_int("MAX_POSITIONS", 5),
            stop_loss_pct=_env_float("STOP_LOSS_PCT", 0.05),
            dry_run=_env_bool("DRY_RUN", True),
            kiwoom_account_id=os.getenv("KIWOOM_ACCOUNT_ID", ""),
            kiwoom_account_pw=os.getenv("KIWOOM_ACCOUNT_PW", ""),
            kiwoom_trade_id=os.getenv("KIWOOM_TRADE_ID", ""),
            kiwoom_trade_pw=os.getenv("KIWOOM_TRADE_PW", ""),
            kiwoom_server_ip=os.getenv("KIWOOM_SERVER_IP", ""),
            kiwoom_server_port=_env_int("KIWOOM_SERVER_PORT", 20003),
            ib_host=os.getenv("IB_HOST", "127.0.0.1"),
            ib_port=_env_int("IB_PORT", 7497),
            ib_client_id=_env_int("IB_CLIENT_ID", 1),
        )
