from __future__ import annotations

import argparse
from pathlib import Path

from new_classifiers.rules import RulesClassifier
from new_core.appservice import AppService
from new_logger.macos.macos_front_app_source import MacOSFrontAppSourceAdaptive
from new_storage.sqlite import SQLiteStorage


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "activity.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the refactored activity logger backend.")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path. Defaults to {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--no-classify",
        action="store_true",
        help="Record events without writing engine classifications.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    source = MacOSFrontAppSourceAdaptive()
    storage = SQLiteStorage(args.db)
    classifier = None if args.no_classify else RulesClassifier()
    service = AppService(source=source, storage=storage, classifier=classifier)

    print(f"New backend writing to {storage.db_path}")
    print("Press Ctrl+C to stop.")

    try:
        service.start()
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        storage.close()


if __name__ == "__main__":
    main()

