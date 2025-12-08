import uuid
from pathlib import Path


DEFAULT_DEVICE_ID_PATH = (
    Path.home() / ".activity_logger" / "device_id"
)


def get_device_id(path: Path | None = None) -> str:
    """
    Retrieve (or lazily generate) the persistent identifier for this device.
    The ID is stored under ~/.activity_logger/device_id by default so every
    process on the same machine reuses the same value.
    """
    target = Path(path) if path else DEFAULT_DEVICE_ID_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        existing = target.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    device_id = uuid.uuid4().hex
    target.write_text(device_id, encoding="utf-8")
    return device_id
