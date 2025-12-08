import json
import sys
import types
from datetime import datetime

import pytest

from logger import core


def test_get_active_window_info_macos(monkeypatch):
    monkeypatch.setattr("logger.core.platform.system", lambda: "Darwin")
    monkeypatch.setattr("logger.core.subprocess.check_output", lambda cmd: b"Safari||Home - example.com||https://example.com")

    info = core.get_active_window_info()

    assert info is not None
    assert info["app"] == "Safari"
    assert info["title"] == "Home - example.com"
    assert info["url"] == "https://example.com"
    assert isinstance(info["timestamp"], datetime)


def test_get_active_window_info_windows(monkeypatch):
    monkeypatch.setattr("logger.core.platform.system", lambda: "Windows")

    fake_win32 = types.ModuleType("win32gui")
    fake_win32.GetForegroundWindow = lambda: 100
    fake_win32.GetWindowText = lambda window: "Visual Studio Code"
    monkeypatch.setitem(sys.modules, "win32gui", fake_win32)

    info = core.get_active_window_info()

    assert info is not None
    assert info["title"] == "Visual Studio Code"
    assert info["app"] == "Unknown App"
    assert isinstance(info["timestamp"], datetime)


def test_get_active_window_info_unknown_os(monkeypatch):
    monkeypatch.setattr("logger.core.platform.system", lambda: "Linux")
    assert core.get_active_window_info() is None


def test_get_active_window_handles_applescript_error(monkeypatch):
    monkeypatch.setattr("logger.core.platform.system", lambda: "Darwin")

    def _raise_called_process_error(cmd):
        raise core.subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr("logger.core.subprocess.check_output", _raise_called_process_error)

    assert core.get_active_window_info() is None


def test_get_active_window_info_uses_firefox_bridge(monkeypatch, tmp_path):
    monkeypatch.setattr("logger.core.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "logger.core.subprocess.check_output",
        lambda cmd: b"Firefox||Some Window||",
    )

    snapshot_path = tmp_path / "firefox_active_tab.json"
    snapshot = {
        "url": "https://developer.mozilla.org",
        "title": "MDN Web Docs",
        "tabId": 7,
        "windowId": 3,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "received_at": datetime.utcnow().isoformat() + "Z",
    }
    snapshot_path.write_text(json.dumps(snapshot))
    monkeypatch.setattr("logger.core.FIREFOX_STATE_FILE", snapshot_path)

    info = core.get_active_window_info()

    assert info is not None
    assert info["app"] == "Firefox"
    assert info["url"] == snapshot["url"]
    assert info["title"] == snapshot["title"]
    assert "metadata" not in info
