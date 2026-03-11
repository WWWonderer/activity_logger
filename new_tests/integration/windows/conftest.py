import sys, pytest

@pytest.fixture(autouse=True)
def require_windows():
    if sys.platform != "win32":
        pytest.skip("Windows only")
