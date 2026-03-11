import os
import shutil
import sys

import pytest


@pytest.fixture(autouse=True)
def require_macos():
    if sys.platform != "darwin":
        pytest.skip("macOS only")


@pytest.fixture(autouse=True)
def require_ui_integration_opt_in():
    if os.getenv("RUN_MACOS_UI_INTEGRATION") != "1":
        pytest.skip("Set RUN_MACOS_UI_INTEGRATION=1 to run macOS UI integration tests")


@pytest.fixture(autouse=True)
def require_macos_tools():
    missing = [tool for tool in ("open", "osascript") if not shutil.which(tool)]
    if missing:
        pytest.skip(f"Missing required macOS CLI tools: {', '.join(missing)}")
