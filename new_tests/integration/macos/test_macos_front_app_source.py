# to run: RUN_MACOS_UI_INTEGRATION=1 PYTHONPATH=. venv/bin/pytest -c new_tests/pytest.ini new_tests/integration/macos/test_macos_front_app_source.py -m macos -s
from __future__ import annotations

import subprocess
import threading
import time

import pytest

from new_logger.macos.macos_front_app_source import MacOSFrontAppSourceAdaptive

pytest.importorskip("AppKit")


class _SkipScenario(Exception):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def _osascript(lines: list[str]) -> str:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    return _run(cmd).stdout.strip()


def _frontmost_app_name() -> str:
    return _osascript(
        [
            'tell application "System Events"',
            'set frontProcess to first process whose frontmost is true',
            'return name of frontProcess',
            "end tell",
        ]
    )


def _is_frontmost_app(app_name: str) -> bool:
    return _frontmost_app_name().casefold() == app_name.casefold()


def _wait_until(predicate, timeout: float, label: str, poll_interval: float = 0.1) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(poll_interval)
    pytest.fail(f"Timed out waiting for {label}")


def _activate_app(app_name: str) -> None:
    _osascript([f'tell application "{app_name}" to activate'])


@pytest.mark.macos
def test_launch_and_switch_apps_emits_expected_app_title_and_url(tmp_path):
    source = MacOSFrontAppSourceAdaptive()
    source.POLL_INTERVAL = 0.1
    source.IDLE_AFTER = 3600

    safari_url = (
        "https://example.com/integration?"
        "token=macosIntegrationSecretValue123&lang=en"
    )
    expected_safari_url = "https://example.com/integration?lang=en&token=_REDACTED_"

    events = []
    events_lock = threading.Lock()
    scenario_errors: list[BaseException] = []
    scenario_skip_reason: list[str] = []
    finder_dir = tmp_path

    def on_event(event):
        with events_lock:
            events.append(event)

    def has_finder_event() -> bool:
        with events_lock:
            return any(e.app == "Finder" for e in events)

    # open finder and then safari
    def run_scenario() -> None:
        try:
            _wait_until(
                lambda: source.emit is not None,
                timeout=10,
                label="source loop initialization",
            )

            try:
                _run(["open", "-a", "Finder", str(finder_dir)])
            except subprocess.CalledProcessError as exc:
                raise _SkipScenario(
                    f"Cannot launch Finder for macOS E2E test: {exc.stderr.strip() or exc}"
                ) from exc

            _activate_app("Finder")
            _wait_until(
                lambda: _is_frontmost_app("Finder"),
                timeout=20,
                label="Finder to become frontmost",
            )

            # Let the source poll at least once while Finder is frontmost.
            time.sleep(1.0)

            browser_app = None
            browser_errors = []
            for candidate in ("Safari", "Google Chrome"):
                try:
                    _run(["open", "-a", candidate, safari_url])
                    _activate_app(candidate)
                    browser_app = candidate
                    break
                except subprocess.CalledProcessError as exc:
                    browser_errors.append(
                        f"{candidate}: {exc.stderr.strip() or exc}"
                    )

            if browser_app is None:
                raise _SkipScenario(
                    "Cannot launch Safari or Google Chrome for macOS E2E test: "
                    + " | ".join(browser_errors)
                )

            _wait_until(
                lambda: _is_frontmost_app(browser_app),
                timeout=20,
                label=f"{browser_app} to become frontmost",
            )

            _wait_until(
                has_finder_event,
                timeout=30,
                label="Finder segment emission after app switch",
            )

            # Give browser a moment to become the active open segment before stopping.
            time.sleep(1.0)

        except _SkipScenario as exc:
            scenario_skip_reason.append(str(exc))
        except BaseException as exc:
            scenario_errors.append(exc)
        finally:
            source.stop()

    thread = threading.Thread(target=run_scenario, daemon=True)
    thread.start()

    source.start(on_event)

    thread.join(timeout=10)
    if thread.is_alive():
        pytest.fail("Scenario thread did not finish after source stopped")

    if scenario_skip_reason:
        pytest.skip(scenario_skip_reason[0])

    if scenario_errors:
        raise scenario_errors[0]

    with events_lock:
        captured_events = list(events)

    finder_event = next(
        (e for e in captured_events if e.app == "Finder"),
        None,
    )
    assert finder_event is not None
    assert finder_event.url == ""

    browser_event = next(
        (
            e
            for e in reversed(captured_events)
            if e.app in {"Safari", "Google Chrome"} and e.url == expected_safari_url
        ),
        None,
    )
    assert browser_event is not None
    assert browser_event.title != ""


@pytest.mark.macos
def test_firefox_event_uses_bridge_title_and_url(tmp_path):
    source = MacOSFrontAppSourceAdaptive()
    source.POLL_INTERVAL = 0.1
    source.IDLE_AFTER = 3600

    token_value = f"firefoxBridgeE2E{int(time.time() * 1000)}"
    probe_value = f"run{int(time.time() * 1000)}"
    firefox_url = f"https://example.com/?token={token_value}&lang=en&probe={probe_value}"
    expected_firefox_url = (
        f"https://example.com/?lang=en&probe={probe_value}&token=_REDACTED_"
    )

    events = []
    events_lock = threading.Lock()
    scenario_errors: list[BaseException] = []
    scenario_skip_reason: list[str] = []
    finder_dir = tmp_path

    def on_event(event):
        with events_lock:
            events.append(event)

    def has_finder_event() -> bool:
        with events_lock:
            return any(e.app == "Finder" for e in events)

    def run_scenario() -> None:
        try:
            _wait_until(
                lambda: source.emit is not None,
                timeout=10,
                label="source loop initialization",
            )

            try:
                _run(["open", "-a", "Finder", str(finder_dir)])
            except subprocess.CalledProcessError as exc:
                raise _SkipScenario(
                    f"Cannot launch Finder for macOS E2E test: {exc.stderr.strip() or exc}"
                ) from exc

            _activate_app("Finder")
            _wait_until(
                lambda: _is_frontmost_app("Finder"),
                timeout=20,
                label="Finder to become frontmost",
            )
            time.sleep(1.0)

            try:
                _run(["open", "-a", "Firefox", firefox_url])
            except subprocess.CalledProcessError as exc:
                raise _SkipScenario(
                    f"Cannot launch Firefox for macOS E2E test: {exc.stderr.strip() or exc}"
                ) from exc

            _activate_app("Firefox")
            _wait_until(
                lambda: _is_frontmost_app("Firefox"),
                timeout=20,
                label="Firefox to become frontmost",
            )

            _wait_until(
                has_finder_event,
                timeout=30,
                label="Finder segment emission after app switch",
            )
            time.sleep(1.0)

        except _SkipScenario as exc:
            scenario_skip_reason.append(str(exc))
        except BaseException as exc:
            scenario_errors.append(exc)
        finally:
            source.stop()

    thread = threading.Thread(target=run_scenario, daemon=True)
    thread.start()

    source.start(on_event)

    thread.join(timeout=10)
    if thread.is_alive():
        pytest.fail("Scenario thread did not finish after source stopped")

    if scenario_skip_reason:
        pytest.skip(scenario_skip_reason[0])

    if scenario_errors:
        raise scenario_errors[0]

    with events_lock:
        captured_events = list(events)

    finder_event = next((e for e in captured_events if e.app == "Finder"), None)
    assert finder_event is not None
    assert finder_event.url == ""
    firefox_event = next(
        (
            e
            for e in reversed(captured_events)
            if e.app.casefold() == "firefox" and e.url == expected_firefox_url
        ),
        None,
    )
    assert firefox_event is not None
    assert firefox_event.title != ""
