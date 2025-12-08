import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from datetime import datetime
from logger.categorize import categorize
from logger.device import get_device_id

class LogBuffer:
    def __init__(
        self,
        flush_interval=60,
        max_rows=100,
        log_dir=None,
        device_id=None,
        sync_client=None,
        resume_gap_seconds=60,
    ):
        self.buffer = []
        self.flush_interval = flush_interval
        self.max_rows = max_rows
        self.last_flush = datetime.now()
        self.log_dir = Path(log_dir or Path(__file__).resolve().parent.parent / "logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.device_id = device_id or get_device_id()
        self.sync_client = sync_client
        self.active_app = None
        self.active_title = None
        self.active_start = None
        self.active_url = None
        self.resume_gap_seconds = resume_gap_seconds

        self._resume_from_last_row()

    def _resume_from_last_row(self):
        """Resume the active session if the last logged app was recent."""
        now = datetime.now()
        file_path = self.log_dir / f"activity_{now.year}_{now.month:02d}_{self.device_id}.parquet"
        if not file_path.exists():
            legacy_path = self.log_dir / f"activity_{now.year}_{now.month:02d}.parquet"
            if not legacy_path.exists():
                return
            file_path = legacy_path

        try:
            pf = pq.ParquetFile(file_path)
            last_rg = pf.num_row_groups - 1
            table = pf.read_row_group(last_rg)
            last_row = table.slice(table.num_rows - 1, 1).to_pandas().iloc[0]
        except Exception as e:
            print(f"Warning: failed to read last row for resume: {e}")
            return

        # Extract end_time and check how long ago it was
        end_time = pd.to_datetime(last_row["end_time"])
        if (datetime.now() - end_time).total_seconds() <= self.resume_gap_seconds:
            # Resume from that session
            self.active_app = last_row["app"]
            self.active_title = last_row["title"]
            self.active_start = end_time
            self.active_url = last_row.get("url") if "url" in last_row else None
            print(f"Resumed active session: {self.active_app} ({self.active_title}) at {self.active_start}")

    def add(self, row: dict):
        self.buffer.append(row)
        now = datetime.now()

        if len(self.buffer) >= self.max_rows or (now - self.last_flush).total_seconds() >= self.flush_interval:
            self.flush()

    def _buffer_to_sessions(self, close_active=False):
        """
        Convert self.buffer (point samples) into session-style rows:
        start_time, end_time, duration_sec, app, title, category, is_productive
        using categorize(app, title).
        """
        sessions = []

        # bring in ongoing session info across flushes
        current_app = self.active_app
        current_title = self.active_title
        current_start = self.active_start
        current_url = self.active_url

        for entry in self.buffer:
            ts = entry["timestamp"]
            app = entry["app"]
            title = entry["title"]
            url = entry.get("url")

            if (app, title, url) != (current_app, current_title, current_url):
                # close previous session if it existed
                if current_app is not None:
                    category, is_productive = categorize(current_app, current_title, current_url or "")
                    sessions.append({
                        "start_time": current_start,
                        "end_time": ts,
                        "duration_sec": (ts - current_start).total_seconds(),
                        "app": current_app,
                        "title": current_title,
                        "url": current_url,
                        "category": category,
                        "is_productive": is_productive,
                        "device_id": self.device_id,
                    })

                # start new session
                current_app = app
                current_title = title
                current_start = ts
                current_url = url

            # else: same app/title as before, so just keep going

        if close_active and current_app is not None:
            final_end = datetime.now()
            category, is_productive = categorize(current_app, current_title, current_url or "")
            sessions.append({
                "start_time": current_start,
                "end_time": final_end,
                "duration_sec": (final_end - current_start).total_seconds(),
                "app": current_app,
                "title": current_title,
                "url": current_url,
                "category": category,
                "is_productive": is_productive,
                "device_id": self.device_id,
            })
            current_app = None
            current_title = None
            current_start = None
            current_url = None

        # after iterating through buffer, DO NOT close the last session yet.
        # we keep it "open" because user might still be in that app.
        # we save it back to self.active_* so next flush can continue it.
        self.active_app = current_app
        self.active_title = current_title
        self.active_start = current_start
        self.active_url = current_url

        return sessions
    
    def flush(self, force=False):
        if not self.buffer and not (force and self.active_app):
            return

        # 1. convert snapshots -> finished sessions (except the still-active last one)
        session_rows = self._buffer_to_sessions(close_active=force)

        if not session_rows:
            # Nothing closed yet (e.g. user never switched apps in this buffer),
            # so just update timestamps and bail.
            self.last_flush = datetime.now()
            self.buffer.clear()
            return

        # 2. create DataFrame of finalized sessions
        df = pd.DataFrame(session_rows).reindex(
            columns=[
                "start_time",
                "end_time",
                "duration_sec",
                "app",
                "title",
                "url",
                "category",
                "is_productive",
                "device_id",
            ]
        )

        # Use the timestamp of the FIRST row we are about to write
        first_ts = df["start_time"].iloc[0]
        filename = f"activity_{first_ts.year}_{first_ts.month:02d}_{self.device_id}.parquet"
        file_path = self.log_dir / filename

        merge_gap_seconds = self.resume_gap_seconds

        # 3. Append to parquet (with optional merge to stitch quick restarts)
        if file_path.exists():
            try:
                existing_df = pd.read_parquet(file_path)
                target_cols = list(existing_df.columns) + [c for c in df.columns if c not in existing_df.columns]

                for col in target_cols:
                    if col not in df.columns:
                        df[col] = None
                    if col not in existing_df.columns:
                        existing_df[col] = None

                should_merge = False
                try:
                    last_existing = existing_df.iloc[-1]
                    first_new = df.iloc[0]
                    gap = (pd.to_datetime(first_new["start_time"]) - pd.to_datetime(last_existing["end_time"])).total_seconds()
                    same_identity = (
                        last_existing.get("app") == first_new.get("app")
                        and last_existing.get("title") == first_new.get("title")
                        and (last_existing.get("url") or None) == (first_new.get("url") or None)
                    )
                    should_merge = gap >= 0 and gap <= merge_gap_seconds and same_identity
                except Exception:
                    should_merge = False

                # Rewrite the file when schema changed or we need to merge adjacent sessions.
                if set(target_cols) != set(existing_df.columns) or should_merge:
                    if should_merge:
                        existing_df.at[existing_df.index[-1], "end_time"] = df.iloc[0]["end_time"]
                        existing_df.at[existing_df.index[-1], "duration_sec"] = (
                            pd.to_datetime(existing_df.iloc[-1]["end_time"]) - pd.to_datetime(existing_df.iloc[-1]["start_time"])
                        ).total_seconds()
                        df = df.iloc[1:]

                    combined_df = pd.concat(
                        [existing_df[target_cols], df[target_cols]],
                        ignore_index=True,
                    )
                    combined_df.to_parquet(
                        file_path,
                        engine="fastparquet",
                        compression="snappy",
                        index=False,
                    )
                    self.buffer.clear()
                    self.last_flush = datetime.now()
                    if self.sync_client:
                        try:
                            self.sync_client.upload_file(file_path)
                        except Exception as exc:
                            print(f"[Drive Sync] Upload failed for {file_path.name}: {exc}")
                    return

                df = df[[c for c in target_cols if c in df.columns]]
            except Exception as e:
                print(f"Warning: failed to align schema with existing parquet: {e}")

            # append to existing parquet
            df.to_parquet(
                file_path,
                engine="fastparquet",
                compression="snappy",
                append=True,
                index=False,
            )
        else:
            # create new parquet
            df.to_parquet(
                file_path,
                engine="fastparquet",
                compression="snappy",
                index=False,        # optional: don't store pandas index
            )

        # 4. clear only the consumed buffer, but we actually consumed all timestamps
        # because we rolled them into sessions or into the still-open active_*.
        self.buffer.clear()
        self.last_flush = datetime.now()
        if self.sync_client:
            try:
                self.sync_client.upload_file(file_path)
            except Exception as exc:
                print(f"[Drive Sync] Upload failed for {file_path.name}: {exc}")
