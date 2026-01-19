# firefox_mmap.py
import json, os, struct, mmap
from pathlib import Path
from datetime import datetime

STATE_DIR = Path.home() / "Library" / "Application Support" / "activity_logger" / "bridge"
MMAP_FILE = STATE_DIR / "firefox_active_tab.mmap"
MMAP_SIZE = 64 * 1024

HEADER_FMT = "<II"  # length, seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
PAYLOAD_OFFSET = HEADER_SIZE
MAX_PAYLOAD = MMAP_SIZE - PAYLOAD_OFFSET

def ensure_mmap_write():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(MMAP_FILE), os.O_CREAT | os.O_RDWR, 0o600)
    st = os.fstat(fd)
    if st.st_size != MMAP_SIZE:
        os.ftruncate(fd, MMAP_SIZE)
    mm = mmap.mmap(fd, MMAP_SIZE, access=mmap.ACCESS_WRITE)
    return fd, mm

def write_state(mm, seq: int, payload: dict) -> int:
    payload = dict(payload)
    payload["received_at"] = datetime.utcnow().isoformat() + "Z"
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    if len(data) > MAX_PAYLOAD:
        payload["title"] = (payload.get("title") or "")[:500]
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(data) > MAX_PAYLOAD:
            data = b"{}"

    seq = (seq + 1) & 0xFFFFFFFF

    mm.seek(PAYLOAD_OFFSET)
    mm.write(data)
    remaining = MAX_PAYLOAD - len(data)
    if remaining > 0:
        mm.write(b"\x00" * remaining)

    # seq then length last (commit marker)
    mm.seek(4)
    mm.write(struct.pack("<I", seq))
    mm.seek(0)
    mm.write(struct.pack("<I", len(data)))

    return seq

def read_state():
    if not MMAP_FILE.exists():
        return None

    fd = os.open(str(MMAP_FILE), os.O_RDONLY)
    mm = None
    try:
        mm = mmap.mmap(fd, MMAP_SIZE, access=mmap.ACCESS_READ)

        # Snapshot attempt
        length1 = struct.unpack("<I", mm[0:4])[0]
        seq1 = struct.unpack("<I", mm[4:8])[0]
        if length1 == 0 or length1 > MAX_PAYLOAD:
            return None

        data = bytes(mm[PAYLOAD_OFFSET:PAYLOAD_OFFSET + length1])

        # Verify writer didn't update mid-read
        seq2 = struct.unpack("<I", mm[4:8])[0]
        if seq1 != seq2:
            return None

        return json.loads(data.decode("utf-8"))
    finally:
        if mm is not None:
            mm.close()
        os.close(fd)
