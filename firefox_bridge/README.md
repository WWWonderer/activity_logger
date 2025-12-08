# Firefox URL Bridge

WebExtension + native host that streams the active Firefox tab (URL/title) to the activity logger at `~/Library/Application Support/activity_logger/bridge/firefox_active_tab.json`.

## Files

- `extension/background.js` — captures active tab changes and sends them to the native host.
- `extension/manifest.json` — permissions (`tabs`, `activeTab`, `nativeMessaging`), id `activity-logger-bridge@example.com`.
- `native_host/firefox_logger_bridge.py` — native host that writes the tab snapshot to disk.
- `native_host/activity_logger_bridge.json` — native messaging manifest; must contain an absolute `path` to the host script.

## Install / Update (macOS, user scope)

```bash
# 1) Place host script outside quarantined locations
mkdir -p "$HOME/Library/Application Support/activity_logger/native_host"
cp firefox_bridge/native_host/firefox_logger_bridge.py \
   "$HOME/Library/Application Support/activity_logger/native_host/"
chmod +x "$HOME/Library/Application Support/activity_logger/native_host/firefox_logger_bridge.py"

# 2) Copy manifest to Firefox's native host directory
mkdir -p "$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
cp firefox_bridge/native_host/activity_logger_bridge.json \
   "$HOME/Library/Application Support/Mozilla/NativeMessagingHosts/"

# 3) Point the manifest to the installed host (Firefox requires an absolute path)
python - <<'PY'
import json, pathlib
manifest = pathlib.Path("~/Library/Application Support/Mozilla/NativeMessagingHosts/activity_logger_bridge.json").expanduser()
data = json.loads(manifest.read_text())
data["path"] = str(pathlib.Path.home() / "Library" / "Application Support" / "activity_logger" / "native_host" / "firefox_logger_bridge.py")
manifest.write_text(json.dumps(data, indent=2))
print("Updated manifest path ->", data["path"])
PY
```

Linux is the same flow but with the manifest under `~/.mozilla/native-messaging-hosts/`.

## Load the extension

1) In Firefox, open `about:debugging#/runtime/this-firefox`.  
2) Click **Load Temporary Add-on…** and choose `firefox_bridge/extension/manifest.json`.  
3) For a persistent install, run `web-ext build` inside `firefox_bridge/extension` and install the generated XPI. Ensure the extension id matches the manifest `allowed_extensions`.

## Verify

- After focusing a tab, `~/Library/Application Support/activity_logger/bridge/firefox_active_tab.json` should update with `url`, `title`, and `received_at`.
- If no messages arrive, confirm the manifest `path` exists and the extension id matches `allowed_extensions`. Launching Firefox from a terminal helps surface host stderr/stdout.

 
