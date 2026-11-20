"""Broker implementations & factory."""
from .base import Broker
from .paper import PaperBroker
from .tossinvest import TossInvestBroker

__all__ = ["Broker", "PaperBroker", "TossInvestBroker"]


def make_broker(config, data_provider=None):
    """Build the configured broker.

    ``data_provider`` is only needed for ``paper`` (to source reference
    prices). Real brokers get prices from the exchange.
    """
    name = (config.broker or "paper").strip().lower()

    if name == "paper":
        def _price(symbol: str):
            if data_provider is None:
                return None
            bars = data_provider.get_bars(symbol, config.interval, 1)
            return bars[-1].close if bars else None

        return PaperBroker(config.initial_cash, price_source=_price)

    if name == "ibkr":
        from .ibkr import IBKRBroker

        return IBKRBroker(
            host=config.ib_host,
            port=config.ib_port,
            client_id=config.ib_client_id,
        )

    if name == "kiwoom":
        from .kiwoom import KiwoomBroker

        return KiwoomBroker(
            account_id=config.kiwoom_account_id,
            account_pw=config.kiwoom_account_pw,
            trade_id=config.kiwoom_trade_id,
            trade_pw=config.kiwoom_trade_pw,
            server_ip=config.kiwoom_server_ip,
            server_port=config.kiwoom_server_port,
        )

    if name in ("tossinvest", "toss", "tois"):
        # Credentials are read from the TOSSEST_* environment variables.
        return TossInvestBroker()

    raise ValueError(f"Unknown broker: {config.broker!r}")
