from __future__ import annotations

import subprocess
from typing import Optional


def resolve_idle_threshold_seconds(user_idle_seconds: int = 300) -> int:
    """
    Pick the minimum of user threshold and macOS system idle-ish timeouts:
      - display sleep (pmset displaysleep) in minutes
      - system sleep (pmset sleep) in minutes
      - screensaver idleTime in seconds

    Returns seconds. Falls back to user_idle_seconds if values are unavailable.
    """
    candidates: list[int] = [user_idle_seconds]

    # pmset values are in minutes
    try:
        out = subprocess.check_output(["pmset", "-g", "custom"], text=True)
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            key = parts[0]
            try:
                minutes = int(parts[1])
            except ValueError:
                continue
            if minutes <= 0:
                continue
            if key in {"displaysleep", "sleep"}:
                candidates.append(max(1, minutes * 60 - 1))
    except Exception:
        pass

    # screensaver idleTime is in seconds
    try:
        out = subprocess.check_output(
            ["defaults", "-currentHost", "read", "com.apple.screensaver", "idleTime"],
            text=True,
        )
        secs = int(out.strip())
        if secs > 0:
            candidates.append(secs)
    except Exception:
        pass

    return min(candidates)


def mac_idle_seconds() -> Optional[float]:
    """
    Returns seconds since last user input (keyboard/mouse) on macOS.
    Requires PyObjC (Quartz): pip install pyobjc
    """
    try:
        import Quartz  # type: ignore
    except Exception:
        return None

    try:
        return float(
            Quartz.CGEventSourceSecondsSinceLastEventType(
                Quartz.kCGEventSourceStateCombinedSessionState,
                Quartz.kCGAnyInputEventType,
            )
        )
    except Exception:
        return None


class MacOSIdleMonitor:
    """
    Idle detector for macOS. If Quartz isn't available, behaves as "not idle".
    """
    def __init__(self, threshold_seconds: float = 300.0):
        self.threshold_seconds = threshold_seconds

    def idle_seconds(self) -> Optional[float]:
        return mac_idle_seconds()

    def is_idle(self) -> bool:
        secs = self.idle_seconds()
        return secs is not None and secs >= self.threshold_seconds


def make_idle_monitor(user_idle_seconds: int = 300) -> MacOSIdleMonitor:
    """
    Convenience: picks a good threshold based on user preference + macOS settings.
    """
    threshold = resolve_idle_threshold_seconds(user_idle_seconds=user_idle_seconds)
    return MacOSIdleMonitor(threshold_seconds=float(threshold))