"""Command-line entry point for stockbot.

Examples
--------
# Paper-trade a US symbol, dry run (no order actually placed):
python main_trading.py --symbols AAPL --broker paper --dry-run

# Real paper broker (simulated fills) on a Korean + US mix:
python main_trading.py --symbols AAPL 005930 --broker paper

# Live trading via Interactive Brokers:
python main_trading.py --symbols AAPL --broker ibkr

# Live trading via Kiwoom (Windows):
python main_trading.py --symbols 005930 --broker kiwoom

# Run several cycles:
python main_trading.py --symbols AAPL --broker paper --cycles 3 --interval 5
"""
from __future__ import annotations

import argparse
import sys

from stockbot.broker import make_broker
from stockbot.config import Config
from stockbot.data import MultiMarketDataProvider
from stockbot.engine import TradingEngine
from stockbot.strategy import SMACrossoverStrategy


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Modular multi-market trading bot")
    p.add_argument(
        "--symbols", required=True,
        help="Comma-separated watchlist, e.g. 'AAPL,MSFT,005930'",
    )
    p.add_argument(
        "--broker", default="paper",
        choices=["paper", "ibkr", "kiwoom"],
        help="Broker backend (default: paper)",
    )
    p.add_argument(
        "--strategy", default="sma",
        choices=["sma"],
        help="Strategy to run (default: sma crossover)",
    )
    p.add_argument("--fast", type=int, default=10, help="Fast SMA period")
    p.add_argument("--slow", type=int, default=30, help="Slow SMA period")
    p.add_argument("--size", type=int, default=1, help="Shares per order")
    p.add_argument("--interval", default="1d", help="Bar interval (default 1d)")
    p.add_argument("--bars", type=int, default=60, help="Number of bars to fetch")
    p.add_argument(
        "--max-order-value", type=float, default=None,
        help="Max notional per order (USD for US, KRW for KR)",
    )
    p.add_argument(
        "--cash", type=float, default=None,
        help="Override initial cash for the paper broker",
    )
    p.add_argument("--cycles", type=int, default=1, help="Number of cycles to run")
    p.add_argument("--cycle-interval", type=int, default=30,
                   help="Seconds to wait between cycles")
    p.add_argument("--verbose", action="store_true", help="Debug logging")
    p.add_argument(
        "--dry-run", action="store_true",
        help="Evaluate signals but do NOT send orders",
    )
    return p.parse_args(argv)


def build_engine(args: argparse.Namespace):
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if args.cash is not None:
        initial_cash = args.cash
    else:
        initial_cash = 100_000.0

    config = Config(
        broker=args.broker,
        symbols=symbols,
        interval=args.interval,
        bars_limit=args.bars,
        max_order_value=args.max_order_value,
        initial_cash=initial_cash,
        dry_run=args.dry_run,
    )

    data = MultiMarketDataProvider()
    broker = make_broker(config, data)
    strategy = SMACrossoverStrategy(
        fast_period=args.fast,
        slow_period=args.slow,
        order_size=args.size,
    )
    return TradingEngine(config=config, data=data, strategy=strategy, broker=broker)


def main(argv=None) -> int:
    args = parse_args(argv)

    # Configure the stockbot logger (it owns its own handler; root logging
    # won't reach it because propagate=False).
    import logging

    from stockbot.logger import get_logger

    get_logger().setLevel(logging.DEBUG if args.verbose else logging.INFO)
    try:
        engine = build_engine(args)
    except Exception as exc:
        print(f"Failed to initialise: {exc}", file=sys.stderr)
        return 2

    try:
        reports = engine.run(cycles=args.cycles, interval_seconds=args.cycle_interval)
    except Exception as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1
    finally:
        # close() is optional on the Broker interface; only call if present.
        close = getattr(engine.broker, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    print("\n" + "=" * 60)
    for i, report in enumerate(reports, start=1):
        print(f"--- Cycle {i} ---")
        print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
