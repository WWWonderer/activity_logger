# Firefox URL Bridge (mmap)

Firefox WebExtension + native messaging host that streams the active Firefox tab (URL/title) to the activity logger via a **memory-mapped shared state (mmap)**.

## Outline

Since Firefox does not provide native AppleScript support, reading the active tab URL on MacOS requires a different approach. This project uses a Firefox WebExtension (in `/extension`) to capture the current tab’s URL/title and send it to a native messaging host over `stdin` as JSON. The native Python host (in `/native_host`) then writes the latest tab snapshot into shared memory (mmap), where the activity logger can read it.

Because Firefox native messaging is strict about manifest format, extension IDs, and absolute paths, the setup steps must be followed carefully.


## Files

- `extension/background.js` — captures active tab changes and sends them to the native host.
- `extension/manifest.json` — permissions (`tabs`, `activeTab`, `nativeMessaging`), id `activity-logger-bridge@example.com`.
- `native_host/firefox_logger_bridge.py` — native host; receives tab snapshots and writes to mmap.
- `native_host/firefox_mmap.py` — mmap helpers (create/open mmap + write state).
- `native_host/activity_logger_bridge.json` — native messaging manifest; `path` must be an absolute path to the host script.

## Install / Update (macOS, user scope)

```bash
# 1) Install native host scripts
mkdir -p "$HOME/Library/Application Support/activity_logger/native_host"
cp firefox_bridge/native_host/firefox_logger_bridge.py \
   firefox_bridge/native_host/firefox_mmap.py \
   "$HOME/Library/Application Support/activity_logger/native_host/"
chmod +x "$HOME/Library/Application Support/activity_logger/native_host/firefox_logger_bridge.py"

# 2) Install native messaging manifest for Firefox
mkdir -p "$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
cp firefox_bridge/native_host/activity_logger_bridge.json \
   "$HOME/Library/Application Support/Mozilla/NativeMessagingHosts/"

# 3) Point the manifest "path" to the installed host script (absolute path required)
python - <<'PY'
import json, pathlib
manifest = pathlib.Path("~/Library/Application Support/Mozilla/NativeMessagingHosts/activity_logger_bridge.json").expanduser()
data = json.loads(manifest.read_text())
data["path"] = str(pathlib.Path.home() / "Library" / "Application Support" / "activity_logger" / "native_host" / "firefox_logger_bridge.py")
manifest.write_text(json.dumps(data, indent=2))
print("Updated manifest path ->", data["path"])
PY
```

## Load the extension

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on…**
3. Select `firefox_bridge/extension/manifest.json`

For a persistent install, run `web-ext build` inside `firefox_bridge/extension` and install the generated `.xpi`.  
Make sure the extension id matches the manifest `allowed_extensions`.

## Private (incognito) windows

Firefox blocks extensions from running in private windows unless explicitly enabled. After loading/installing the add-on:

**about:addons → Activity Logger Bridge → Run in Private Windows → Allow**

Without this toggle, the bridge will not see incognito tabs.

## Verify
Setup carefully. Then open a firefox tab and input any url. Run the `smoke_macos_app_overrides.py` script and it should print the current url and title.

If no messages arrive:

- Confirm you have installed the web extension correctly
- Confirm the native messaging manifest `path` exists and is executable
- Confirm the extension id matches `allowed_extensions`
- Check native host logs / stderr output (launching Firefox from Terminal can help)


