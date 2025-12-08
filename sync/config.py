import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
DEFAULT_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


@dataclass
class SyncConfig:
    credentials_path: Path
    token_path: Path
    folder_id: str
    scopes: list[str]

    @classmethod
    def from_mapping(cls, data: dict, base_dir: Path) -> "SyncConfig":
        creds = base_dir / data["credentials_path"]
        token = base_dir / data.get("token_path", "token.json")
        scopes = data.get("scopes") or DEFAULT_SCOPES
        return cls(
            credentials_path=creds.expanduser(),
            token_path=token.expanduser(),
            folder_id=data["folder_id"],
            scopes=list(scopes),
        )


def load_config(path: Path | None = None) -> SyncConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Drive sync config not found: {config_path}")

    base_dir = config_path.parent
    data = json.loads(config_path.read_text(encoding="utf-8"))
    required = {"credentials_path", "folder_id"}
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Drive sync config missing keys: {', '.join(missing)}")

    return SyncConfig.from_mapping(data, base_dir)
