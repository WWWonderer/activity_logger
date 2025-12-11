# Activity Logger
Ever wonder how much time you've spent working or wasting throughout a day on your computer? 

This software track active apps, window titles, and URLs, then roll them into sessionized parquet logs and a Dash dashboard. You can easily review what you have done on your computer at any time. Built for macOS (AppleScript + Quartz) with planned future extension for other operating systems. 

The software is designed to be:
- lightweight
- customization (where you can define your own categories for your activities)
- cross-platform and multi-device
- easy and private data storage (local and no db), with optional cloud-based backup via Google Drive
- modular and extensible

## Features
- CLI runner with three modes: `logger`, `dashboard`, or `serve` (logger + dashboard together).
- Rule-based categorization (`config/category_rules.json`) with optional OpenAI fallback that can append new rules on the fly.
- Sessionized parquet files under `logs/` (monthly, device-scoped) ready for analysis or the bundled Dash UI.
- Optional Google Drive sync for logs, and a Firefox bridge to capture accurate URLs/titles from Firefox.
- Idle detection that maps idle time into the `Idle` category so breaks are visible in the data.

## Quick Start
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt

# Run only the logger (default interval=1s, flush every 60s, 60 snapshots buffered)
python main.py logger --interval 1 --flush-interval 60 --max-rows 60

# Run only the dashboard (reads parquet files from logs/)
python main.py dashboard --port 8050 --debug

# Run both: logger in the foreground, dashboard in a background thread
python main.py serve --interval 1 --flush-interval 60 --max-rows 60 --port 8050
```

### CLI flags (from `main.py`)
- `logger`: `--interval` poll seconds, `--flush-interval` seconds between parquet writes, `--max-rows` buffer size before flush.
- `dashboard`: `--host`, `--port`, `--debug` (Dash reloader).
- `serve`: combines both sets; dashboard runs without the auto-reloader to keep the logger in-process.

## Data & Files
- Logs live in `logs/activity_YYYY_MM_<device_id>.parquet`. Columns: `start_time`, `end_time`, `duration_sec`, `app`, `title`, `url`, `category`, `is_productive`, `device_id`.
- A per-sample debug stream is also appended to `logs/debug_samples.txt` for quick inspection.
- Device identifier is persisted at `~/.activity_logger/device_id` so multiple runs on the same machine stitch together.
- Categories and productivity flags come from `config/category_rules.json`. Edit this to tune app/domain buckets; AI additions will also write here (except for ambiguous hosts like Google/Bing/ChatGPT).
- Keyword learning (for ambiguous domains) is stored in `config/keyword_index.json` and grows automatically up to 500 keywords per category.

## Optional Integrations
- **AI categorization**: copy `config/ai_config.example.json` to `config/ai_config.json` or set `OPENAI_API_KEY`. The logger will call `logger.ai_callback.openai_categorize` for ambiguous/unknown cases and can append rules when confident.
- **Google Drive sync**: copy `sync/config.example.json` to `sync/config.json`, fill in your `folder_id` and credential paths, and the logger will download/upload parquet files via `sync.DriveSyncClient`.
- **Firefox URL bridge (macOS/Linux)**: see `firefox_bridge/README.md` to install the native host + temporary extension so Firefox URLs/titles are captured (AppleScript alone cannot read them reliably).

## Dashboard
- The Dash app (`dashboard/visualizer.py`) reads all monthly parquet files that overlap the selected week. Charts cover per-day timelines plus weekly/monthly timelines and cumulative bars. Missing files are reported in the console.
- Change the color palette in `config/color_scheme.json` if desired.

## Testing
```bash
pip install -r requirements-dev.txt
pytest
```
Key coverage: window capture logic (`tests/test_core.py`), categorization and keyword index behavior (`tests/test_categorize.py`), and parquet buffering/session rollups (`tests/test_log_buffer.py`).

## TODO
Major
- [ ] Add more analysis to dashboard and improve UI
- [ ] Extend to Windows 
- [ ] device synching
- [ ] Train ML model(s) for automatic categorization, replacing OpenAI API. 

Minor
- [ ] Fix UI daily bar's hovering info and legend
- [ ] For weekly/monthly summary, change from 'stack' to a better visualization
- [ ] Fix repeated API calls to categorize "Unknown" 
