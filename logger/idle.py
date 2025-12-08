import platform
from typing import Callable, Optional


def _mac_idle_seconds() -> Optional[float]:
    try:
        import Quartz

        return Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState,
            Quartz.kCGAnyInputEventType,
        )
    except Exception:
        return None


def _windows_idle_seconds() -> Optional[float]:
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        GetLastInputInfo = ctypes.windll.user32.GetLastInputInfo
        GetTickCount = ctypes.windll.kernel32.GetTickCount

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not GetLastInputInfo(ctypes.byref(info)):
            return None
        millis = GetTickCount() - info.dwTime
        return millis / 1000.0
    except Exception:
        return None


def _dummy_idle_seconds() -> Optional[float]:
    return None


class IdleMonitor:
    def __init__(self, threshold_seconds: int = 300):
        self.threshold_seconds = threshold_seconds
        self._idle_seconds_fn: Callable[[], Optional[float]] = _dummy_idle_seconds

        system = platform.system()
        if system == "Darwin":
            self._idle_seconds_fn = _mac_idle_seconds
        elif system == "Windows":
            self._idle_seconds_fn = _windows_idle_seconds

    def is_idle(self) -> bool:
        seconds = self._idle_seconds_fn()
        if seconds is None:
            return False
        return seconds >= self.threshold_seconds
