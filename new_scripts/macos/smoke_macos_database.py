from __future__ import annotations

import argparse
import sqlite3
import threading
from pathlib import Path

from new_core.appservice import AppService
from new_logger.macos.macos_front_app_source import MacOSFrontAppSourceAdaptive
from new_storage.sqlite import SQLiteStorage


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke test macOS capture -> AppService -> SQLiteStorage."
    )
    parser.add_argument(
        "--db",
        default="logs/activity.sqlite3",
        help="SQLite database path to create/update.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=15.0,
        help="How long to record before stopping.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    source = MacOSFrontAppSourceAdaptive()
    storage = SQLiteStorage(db_path)
    app = AppService(source=source, storage=storage)

    print(f"Recording for {args.seconds:g}s into {db_path}")
    print("Switch apps/windows once, then wait for the script to stop.")

    timer = threading.Timer(args.seconds, app.stop)
    timer.start()

    try:
        app.start()
    finally:
        timer.cancel()
        storage.close()

    _print_summary(db_path)


def _print_summary(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        label_count = conn.execute(
            "SELECT COUNT(*) FROM engine_classifications"
        ).fetchone()[0]
        override_count = conn.execute("SELECT COUNT(*) FROM user_overrides").fetchone()[0]
        rows = conn.execute(
            """
            SELECT id, start_ts, end_ts, app, title, url
            FROM events
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()

    print("")
    print(f"DB: {db_path}")
    print(f"events={event_count} engine_classifications={label_count} overrides={override_count}")
    print("latest events:")
    for event_id, start_ts, end_ts, app, title, url in rows:
        duration = end_ts - start_ts
        print(f"- #{event_id} {duration:.2f}s app={app!r} title={title!r} url={url!r}")


if __name__ == "__main__":
    main()
