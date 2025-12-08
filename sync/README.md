## Google Drive Synchronisation

1. Create a folder on Google Drive that will hold the log files (e.g. `Activity Logger`), copy its folder id.
2. In `sync/credentials/` place your OAuth client secret JSON (downloaded from Google Cloud Console). The repo ignores this path so it remains local.
3. Copy `sync/config.example.json` to `sync/config.json` and fill in:
   - `credentials_path`: relative path to the client secret JSON (e.g. `"credentials/client_secret.json"`).
   - `token_path`: where the OAuth refresh token should be stored (defaults to `credentials/token.json`).
   - `folder_id`: the Drive folder id from step 1.
4. The first time the logger runs it will prompt for OAuth consent in a browser window. Afterwards `token_path` is reused.
5. Every flush uploads the per-device parquet file. At start-up the logger also downloads any new/updated files so the dashboard can see other devices' data.

> Tip: commit only `config.example.json`; keep `config.json`, tokens, and credentials out of git.
