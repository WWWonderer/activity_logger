#!/usr/bin/python3
"""
Native messaging host that receives active Firefox tab info and stores it for the
activity logger to read (via mmap shared-state).
"""
import json, struct, sys, traceback
from firefox_mmap import ensure_mmap_write, write_state

_seq = 0
_fd, _mm = ensure_mmap_write()

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

def main():
    global _seq
    while True:
        message = _read_message()
        if message is None:
            break
        _seq = write_state(_mm, _seq, message)
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
