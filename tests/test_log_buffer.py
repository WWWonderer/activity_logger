from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from logger.parquet_writer import LogBuffer

TEST_DEVICE_ID = "test-device"


def _sample_entry(ts, app, title, url=None):
    return {
        "timestamp": ts,
        "app": app,
        "title": title,
        "url": url,
    }


def test_buffer_to_sessions_rolls_over(monkeypatch, tmp_path):
    base_ts = datetime(2024, 1, 1, 12, 0, 0)
    entries = [
        _sample_entry(base_ts, "App1", "Title1"),
        _sample_entry(base_ts + timedelta(seconds=30), "App1", "Title1"),
        _sample_entry(base_ts + timedelta(minutes=1), "App2", "Title2", url="https://example.com"),
    ]

    buffer = LogBuffer(flush_interval=999, max_rows=10, log_dir=tmp_path, device_id=TEST_DEVICE_ID)
    buffer.buffer = entries.copy()

    monkeypatch.setattr(
        "logger.parquet_writer.classify", lambda *args, **kwargs: ("General", True)
    )

    sessions = buffer._buffer_to_sessions()

    assert len(sessions) == 1
    session = sessions[0]
    assert session["start_time"] == entries[0]["timestamp"]
    assert session["end_time"] == entries[2]["timestamp"]
    assert session["duration_sec"] == pytest.approx(60.0)
    assert session["app"] == "App1"
    assert session["title"] == "Title1"
    assert session["url"] is None
    assert session["category"] == "General"
    assert session["is_productive"] is True

    assert buffer.active_app == "App2"
    assert buffer.active_title == "Title2"
    assert buffer.active_start == entries[2]["timestamp"]
    assert buffer.active_url == "https://example.com"


def test_flush_writes_expected_sessions(monkeypatch, tmp_path):
    base_ts = datetime(2024, 1, 1, 9, 0, 0)
    entries = [
        _sample_entry(base_ts, "App1", "Title1"),
        _sample_entry(base_ts + timedelta(minutes=5), "App2", "Title2"),
    ]

    buffer = LogBuffer(flush_interval=999, max_rows=10, log_dir=tmp_path, device_id=TEST_DEVICE_ID)
    buffer.buffer = entries.copy()

    monkeypatch.setattr(
        "logger.parquet_writer.classify", lambda *args, **kwargs: ("General", True)
    )

    recorded = {}

    def fake_to_parquet(self, file_path, *args, **kwargs):
        recorded["path"] = Path(file_path)
        recorded["df"] = self.copy()
        recorded["kwargs"] = kwargs

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet, raising=False)

    buffer.flush()

    assert recorded
    output_df = recorded["df"]
    assert list(output_df.columns) == [
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
    assert len(output_df) == 1
    row = output_df.iloc[0]
    assert row["start_time"] == entries[0]["timestamp"]
    assert row["end_time"] == entries[1]["timestamp"]
    assert row["duration_sec"] == pytest.approx(300.0)
    assert row["app"] == "App1"
    assert buffer.buffer == []
    assert recorded["path"].name == f"activity_2024_01_{TEST_DEVICE_ID}.parquet"
    assert recorded["kwargs"]["index"] is False
    assert row["device_id"] == TEST_DEVICE_ID


def test_flush_no_session_when_same_app(monkeypatch, tmp_path):
    base_ts = datetime(2024, 1, 1, 10, 0, 0)
    entries = [
        _sample_entry(base_ts, "App1", "Title1"),
        _sample_entry(base_ts + timedelta(minutes=5), "App1", "Title1"),
    ]

    buffer = LogBuffer(flush_interval=999, max_rows=10, log_dir=tmp_path, device_id=TEST_DEVICE_ID)
    buffer.buffer = entries.copy()

    monkeypatch.setattr(
        "logger.parquet_writer.classify", lambda *args, **kwargs: ("General", True)
    )

    buffer.flush()

    assert buffer.buffer == []
    assert buffer.active_app == "App1"
    assert buffer.active_start == entries[0]["timestamp"]


def test_force_flush_closes_active_session(monkeypatch, tmp_path):
    base_ts = datetime(2024, 1, 1, 11, 0, 0)
    flush_time = base_ts + timedelta(minutes=10)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return flush_time if tz is None else super().now(tz)

    monkeypatch.setattr("logger.parquet_writer.datetime", FixedDateTime)

    entries = [
        _sample_entry(base_ts, "App1", "Title1", url="https://example.com"),
        _sample_entry(base_ts + timedelta(minutes=5), "App1", "Title1", url="https://example.com"),
    ]

    buffer = LogBuffer(flush_interval=999, max_rows=10, log_dir=tmp_path, device_id=TEST_DEVICE_ID)
    buffer.buffer = entries.copy()

    monkeypatch.setattr(
        "logger.parquet_writer.classify", lambda *args, **kwargs: ("General", True)
    )

    recorded = {}

    def fake_to_parquet(self, file_path, *args, **kwargs):
        recorded["path"] = Path(file_path)
        recorded["df"] = self.copy()
        recorded["kwargs"] = kwargs

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet, raising=False)

    buffer.flush(force=True)

    assert recorded
    output_df = recorded["df"]
    assert len(output_df) == 1
    row = output_df.iloc[0]
    assert row["start_time"] == entries[0]["timestamp"]
    assert row["end_time"] == flush_time
    assert row["duration_sec"] == pytest.approx((flush_time - entries[0]["timestamp"]).total_seconds())
    assert row["url"] == "https://example.com"
    assert row["device_id"] == TEST_DEVICE_ID
    assert buffer.active_app is None
    assert buffer.active_start is None


def test_add_triggers_flush_on_max_rows(monkeypatch, tmp_path):
    buffer = LogBuffer(flush_interval=999, max_rows=2, log_dir=tmp_path, device_id=TEST_DEVICE_ID)

    flush_calls = []

    def fake_flush(force=False):
        flush_calls.append(buffer.buffer.copy())
        buffer.buffer.clear()

    monkeypatch.setattr(buffer, "flush", fake_flush)

    ts = datetime(2024, 1, 1, 12, 0, 0)
    buffer.add(_sample_entry(ts, "App1", "Title1"))
    assert not flush_calls

    buffer.add(_sample_entry(ts + timedelta(seconds=10), "App2", "Title2"))
    assert flush_calls  # flush called
    assert flush_calls[0][0]["app"] == "App1"
