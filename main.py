from __future__ import annotations
import argparse
import signal
import sys
import threading
from pathlib import Path

LOGS_DIR = Path("logs")
CATEGORY_RULES = Path("config/category_rules.json")

def _start_logger_thread(poll_seconds: int) -> tuple[threading.Thread, threading.Event]:
    from logger import parquet_logger
    stop = threading.Event()

    def _target():
        try:
            parquet_logger.run_logger(LOGS_DIR, poll_seconds=poll_seconds, stop_event = stop)
        except TypeError:
            while not stop.is_set():
                parquet_logger.run_logger(LOGS_DIR, poll_seconds=poll_seconds)
                stop.wait(poll_seconds)
        
    th = threading.Thread(target=_target, name="ParquetLogger", daemon=True)
    th.start()
    return th, stop


