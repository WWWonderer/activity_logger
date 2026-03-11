from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Tuple, Dict
from urllib.parse import urlsplit
from AppKit import NSWorkspace, NSAppleScript

from new_core.models import Event
from new_core.ports import EventSource, AppOverride
from new_logger.macos.macos_idle import make_idle_monitor
from new_logger.macos.app_overrides import FirefoxOverride
from new_logger.sanitization.url_sanitizer import sanitize_url


class MacOSFrontAppSourceAdaptive(EventSource):
    # Polling intervals
    POLL_INTERVAL: float = 1.0
    IDLE_INTERVAL: float = 10.0
    IDLE_AFTER: int = 600

    def __init__(self):
        self.workspace = NSWorkspace.sharedWorkspace()
        self.stop_signal = threading.Event()
        self.overrides: Dict[str, AppOverride] = {
            "Firefox": FirefoxOverride()
        }
        
        # Internal State
        self._prev_key: Optional[Tuple[str, str, str]] = None
        self._open_start_ts: Optional[float] = None
        self.emit: Optional[Callable[[Event], None]] = None

        # AppleScript for Title and URL
        self.script_source = """
            try
                tell application "System Events"
                    set frontProcess to first process whose frontmost is true
                    set appName to name of frontProcess
                    set windowTitle to name of window 1 of frontProcess
                end tell
                set currentURL to ""
                if appName is "Google Chrome" then
                    tell application "Google Chrome" to set currentURL to URL of active tab of window 1
                else if appName is "Safari" then
                    tell application "Safari" to set currentURL to URL of document 1
                end if
                return windowTitle & "||" & currentURL
            on error
                return "frontProcess Error||"
            end try
        """
        self.apple_script = NSAppleScript.alloc().initWithSource_(self.script_source)

    def _apply_override(self, app_name: str, title: str, url: str) -> Tuple[str, str]:
        override = self.overrides.get(app_name)
        if not override:
            return title, url
        
        data = override.get() # return (title, url) or None, defined in app_overrides.py
        if not data:
            return title, url
        
        o_title, o_url = data
        return (o_title or title), (o_url or url)

    @staticmethod
    def _sanitize_http_url(url: str) -> str:
        value = (url or "").strip()
        if not value:
            return ""

        try:
            scheme = urlsplit(value).scheme.lower()
            if scheme not in {"http", "https"}:
                return value
            return sanitize_url(value).sanitized_url
        except Exception:
            return value

    def _key_changed(self, old_key: Tuple[str, str, str], new_key: Tuple[str, str, str]) -> bool:
        """Determines if the application state has shifted enough to trigger a new event."""
        old_app, _, old_url = old_key
        new_app, _, new_url = new_key

        # Logic: Ignore changes if it's a browser-like update where 
        # the App and URL remain identical (e.g., just a title flutter when hovering).
        if new_url and old_app == new_app and old_url == new_url:
            return False

        return old_key != new_key

    def _flush_open_segment(self):
        """Finalizes the current event and sends it to the emit callback."""
        if not self.emit or self._prev_key is None or self._open_start_ts is None:
            return

        app, title, url = self._prev_key
        end_ts = time.time()

        # Create the domain model event
        event = Event(
            start_ts=self._open_start_ts, 
            end_ts=end_ts, 
            app=app, 
            title=title, 
            url=url
        )
        # DEBUG
        # print(event)

        self.emit(event)
        
        # Reset state
        self._open_start_ts = None
        self._prev_key = None

    def start(self, emit_callback: Callable[[Event], None]):
        """Runs the monitoring loop. Designed to be called on the Main Thread."""
        self.emit = emit_callback
        self.stop_signal.clear()
        idle_monitor = make_idle_monitor(user_idle_seconds=int(self.IDLE_AFTER))
        
        print("MacOS Source Started. Monitoring frontmost app...")

        try:
            while not self.stop_signal.is_set():
                # if idle, poll slowly
                if idle_monitor.is_idle():
                    if self._prev_key:
                        self._flush_open_segment()
                    self.stop_signal.wait(self.IDLE_INTERVAL)
                    continue

                # 1. Capture Current State
                active_app = self.workspace.frontmostApplication()
                if not active_app:
                    self.stop_signal.wait(self.POLL_INTERVAL)
                    continue

                app_name = active_app.localizedName()
                
                # 2. Get Title and URL via AppleScript
                success, _ = self.apple_script.executeAndReturnError_(None)
                title, url = "", ""
                if success:
                    parts = success.stringValue().split("||")
                    title = parts[0] if len(parts) > 0 else ""
                    url = parts[1] if len(parts) > 1 else ""
                    # mostly triggered by closing one app without clicking or focusing on another
                    if title == "frontProcess Error":
                        self.stop_signal.wait(self.POLL_INTERVAL)
                        continue

                # 3. Apply Title and URL Override for specific apps
                title, url = self._apply_override(app_name, title, url)
                url = self._sanitize_http_url(url)

                current_key = (app_name, title, url)
                ## DEBUG ##
                # print(f'prev_key: {self._prev_key}')
                # print(f'current_key: {current_key}')

                now = time.time()

                # 3. State Change Detection
                if self._prev_key is None:
                    # Initializing first segment
                    self._prev_key = current_key
                    self._open_start_ts = now
                
                elif self._key_changed(self._prev_key, current_key):
                    # Key changed: Flush the old one, start a new one
                    self._flush_open_segment()
                    self._prev_key = current_key
                    self._open_start_ts = now

                # 4. Wait for next poll (interruptible by stop_signal.set())
                self.stop_signal.wait(self.POLL_INTERVAL)

        except KeyboardInterrupt:
            pass
        finally:
            self._flush_open_segment()

    def stop(self):
        """Triggers the stop signal to break the start loop."""
        self.stop_signal.set()
