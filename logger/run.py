import time
import datetime
import subprocess
from pathlib import Path

from logger.core import get_active_window_info
from logger.categorize import categorize, categorize_with_ai
from logger.device import get_device_id
from logger.idle import IdleMonitor
from logger.parquet_writer import LogBuffer
from sync import get_drive_sync_client

try:
    from logger.ai_callback import openai_categorize
except Exception:
    openai_categorize = None


def classify(app, title, url):
    """
    Categorize using AI callback if available; otherwise fall back to rules.
    """
    url = url or ""
    if openai_categorize:
        try:
            return categorize_with_ai(app, title, url, ai_callback=openai_categorize)
        except Exception as exc:
            print(f"[AI categorize fallback] {exc}")
    return categorize(app, title, url)


def _resolve_idle_threshold(user_idle_seconds: int = 300) -> int:
    """
    Pick the minimum of user-provided idle threshold and system timeouts (macOS):
    - display sleep
    - system sleep
    - screensaver
    Falls back to user value if system values are unavailable.
    """
    candidates = [user_idle_seconds]

    try:
        out = subprocess.check_output(["pmset", "-g", "custom"], text=True)
        for line in out.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split()
            if len(parts) < 2:
                continue
            key = parts[0]
            try:
                val = int(parts[1])
            except ValueError:
                continue
            if key == "displaysleep" and val > 0:
                candidates.append(max(1, val * 60 - 1))
            elif key == "sleep" and val > 0:
                candidates.append(max(1, val * 60 - 1))
    except Exception:
        pass

    # macOS screen saver idle time (seconds)
    try:
        out = subprocess.check_output(
            ["defaults", "-currentHost", "read", "com.apple.screensaver", "idleTime"],
            text=True,
        )
        val = int(out.strip())
        if val > 0:
            candidates.append(val)
    except Exception:
        pass

    return min(candidates)

def run_logger(interval=10, flush_interval=60, max_rows=50):
    print("Activity logger started...")

    log_dir = Path(__file__).resolve().parent.parent / "logs"
    device_id = get_device_id()
    drive_sync = get_drive_sync_client(log_dir)
    if drive_sync:
        drive_sync.pull_remote_logs()

    buffer = LogBuffer(
        flush_interval=flush_interval,
        max_rows=max_rows,
        log_dir=log_dir,
        device_id=device_id,
        sync_client=drive_sync,
    )
    idle_threshold = _resolve_idle_threshold(user_idle_seconds=600)  # TODO: make configurable
    idle_monitor = IdleMonitor(threshold_seconds=idle_threshold)
    idle_active = False

    try:
        while True:
            now = datetime.datetime.now()

            is_idle = idle_monitor.is_idle()
            info = None

            if is_idle:
                if not idle_active:
                    idle_active = True
                    cat, prod = classify("Idle", "Idle", "")
                    info = {
                        "timestamp": now,
                        "app": "Idle",
                        "title": "Idle",
                        "url": None,
                        "category": cat,
                        "is_productive": prod,
                    }
            else:
                if idle_active:
                    idle_active = False
                info = get_active_window_info()
                if info:
                    cat, prod = classify(
                        info["app"],
                        info["title"],
                        info.get("url") or "",
                    )
                    info["category"] = cat
                    info["is_productive"] = prod

            DEBUG_LOG = Path(__file__).resolve().parent.parent / "logs" / "debug_samples.txt"
            ts_str = now.isoformat()
            with DEBUG_LOG.open("a", encoding="utf-8") as fh:
                fh.write(f"{ts_str} | {info}\n")

            if info:
                buffer.add(info)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Activity logger stopping...")
    finally:
        buffer.flush(force=True)

if __name__ == "__main__":
    run_logger(1)
