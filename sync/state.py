import json
from pathlib import Path
from typing import Any, Dict, Optional


class SyncState:
    """Records the Drive file ids we have already downloaded (with their md5)."""

    def __init__(self, path: Path | None = None):
        self.path = path or (Path(__file__).resolve().parent / ".state.json")
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, file_id: str) -> Optional[Dict[str, Any]]:
        return self._data.get(file_id)

    def update(self, file_id: str, info: Dict[str, Any]) -> None:
        self._data[file_id] = info
        self._save()
