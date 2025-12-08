import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path

FIREFOX_STATE_FILE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "activity_logger"
    / "bridge"
    / "firefox_active_tab.json"
)


def get_active_window_info():
    system = platform.system()
    if system == "Darwin":
        return _get_macos_active_window()
    if system == "Windows":
        return _get_windows_active_window()
    return None  # or raise NotImplementedError


def _get_macos_active_window():
    script_path = Path(__file__).resolve().parent / "macos_active_window.applescript"
    try:
        raw_result = subprocess.check_output(["osascript", str(script_path)])
    except subprocess.CalledProcessError as exc:
        print(f"[AppleScript Error] {exc}")
        return None
    except Exception as exc:
        print(f"[Unexpected Error] {exc}")
        return None

    result = raw_result.decode().strip()
    parts = result.split("||")
    app = parts[0].strip() if len(parts) > 0 else ""
    title = parts[1].strip() if len(parts) > 1 else ""
    url = parts[2].strip() if len(parts) > 2 else ""

    info = {
        "timestamp": datetime.now(),
        "app": app,
        "title": title,
        "url": url or None,
    }

    if _looks_like_firefox(app):
        snapshot = _load_firefox_bridge_snapshot()
        if snapshot:
            bridge_url = snapshot.get("url")
            bridge_title = snapshot.get("title")
            if bridge_url:
                info["url"] = bridge_url
            if bridge_title:
                info["title"] = bridge_title

    return info


def _load_firefox_bridge_snapshot():
    try:
        raw = FIREFOX_STATE_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    return data


def _looks_like_firefox(app_name):
    normalized = app_name.strip().lower().replace(" ", "")
    return normalized.startswith("firefox")


def _get_windows_active_window():
    try:
        import win32gui

        window = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(window)
        return {
            "timestamp": datetime.now(),
            "app": "Unknown App",
            "title": title.strip(),
        }
    except Exception:
        return None
