from __future__ import annotations

import argparse
import threading
from typing import Iterable


def _run_logger(interval: int, flush_interval: int, max_rows: int) -> None:
    # Import inside to avoid loading logging stack when only running the dashboard.
    from logger.run import run_logger

    run_logger(interval=interval, flush_interval=flush_interval, max_rows=max_rows)


def _run_dashboard(host: str, port: int, debug: bool, use_reloader: bool) -> None:
    # Import inside so Dash dependencies only load when needed.
    from dashboard.visualizer import app

    app.run(host=host, port=port, debug=debug, use_reloader=use_reloader)


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Activity Logger CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    logger_parser = subparsers.add_parser("logger", help="Run the activity logger only")
    logger_parser.add_argument("--interval", type=int, default=1, help="Polling interval (seconds)")
    logger_parser.add_argument(
        "--flush-interval", type=int, default=60, help="Flush interval to parquet (seconds)"
    )
    logger_parser.add_argument("--max-rows", type=int, default=60, help="Max buffered rows before flush")

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the dashboard only")
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="Dashboard host")
    dashboard_parser.add_argument("--port", type=int, default=8050, help="Dashboard port")
    dashboard_parser.add_argument("--debug", action="store_true", help="Enable Dash debug/reloader")

    both_parser = subparsers.add_parser("serve", help="Run logger in background and dashboard in foreground")
    both_parser.add_argument("--interval", type=int, default=1, help="Polling interval (seconds)")
    both_parser.add_argument(
        "--flush-interval", type=int, default=60, help="Flush interval to parquet (seconds)"
    )
    both_parser.add_argument("--max-rows", type=int, default=60, help="Max buffered rows before flush")
    both_parser.add_argument("--host", default="127.0.0.1", help="Dashboard host")
    both_parser.add_argument("--port", type=int, default=8050, help="Dashboard port")
    both_parser.add_argument("--debug", action="store_true", help="Enable Dash debug/reloader")

    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.command == "logger":
        _run_logger(args.interval, args.flush_interval, args.max_rows)
        return

    if args.command == "dashboard":
        _run_dashboard(args.host, args.port, args.debug, use_reloader=args.debug)
        return

    # serve: keep logger in the foreground (handles Ctrl+C/flush), dashboard in background
    dash_thread = threading.Thread(
        target=_run_dashboard,
        kwargs={
            "host": args.host,
            "port": args.port,
            "debug": args.debug,
            "use_reloader": False,  # avoid spawning extra processes alongside logger
        },
        daemon=True,
        name="activity-dashboard",
    )
    dash_thread.start()
    _run_logger(args.interval, args.flush_interval, args.max_rows)


if __name__ == "__main__":
    main()
