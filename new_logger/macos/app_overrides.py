from new_core.ports import AppOverride
from new_logger.macos.firefox_bridge.native_host.firefox_mmap import read_state

class FirefoxOverride(AppOverride):
    def get(self) -> tuple[str, str] | None:
        state = read_state()
        if not state:
            return None

        url = state.get("url") or ""
        title = state.get("title") or ""

        # If there's no useful metadata, bail
        if not url and not title:
            return None

        return (title, url)


