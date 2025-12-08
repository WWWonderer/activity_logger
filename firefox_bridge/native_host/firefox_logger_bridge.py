#!/usr/bin/python3
"""
Native messaging host that receives active Firefox tab info and stores it for the
activity logger to read.
"""
import json
import os
import struct
import sys
import traceback
import tempfile
from pathlib import Path
from datetime import datetime


STATE_DIR = Path.home() / "Library" / "Application Support" / "activity_logger" / "bridge"
STATE_FILE = STATE_DIR / "firefox_active_tab.json"


def _read_message():
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        return None
    message_length = struct.unpack("<I", raw_length)[0]
    data = sys.stdin.buffer.read(message_length).decode("utf-8")
    return json.loads(data)


def _write_message(payload):
    encoded = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _persist_state(payload):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload["received_at"] = datetime.utcnow().isoformat() + "Z"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=STATE_DIR
    ) as tmp_file:
        json.dump(payload, tmp_file)
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        temp_path = Path(tmp_file.name)
    temp_path.replace(STATE_FILE)


def main():
    while True:
        message = _read_message()
        if message is None:
            break
        _persist_state(message)
        _write_message({"status": "ok"})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Native host error: {exc}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        try:
            _write_message({"status": "error", "details": str(exc)})
        except Exception:
            pass
