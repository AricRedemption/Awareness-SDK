"""Tests for memory_cloud.tracing (F-069).

Covers:
- Default off (no env, no path) → NullTraceWriter, zero overhead.
- Env var / explicit path activation.
- Envelope integrity: ts / event / channel / session_id in every event.
- Parent dir auto-creation; self-disabling on write failure (never raises).
- hash-only default; full_content opt-in.
- All seven vocabulary events emit their expected fields.
"""

import json
import os
import stat
from unittest.mock import MagicMock

import pytest

from memory_cloud import tracing
from memory_cloud.tracing import (
    NullTraceWriter,
    MemoryTraceWriter,
    resolve_trace_writer,
    log_recall,
    log_write,
    log_forget,
    log_snapshot,
    log_restore,
    log_conflict_forget,
    log_degrade,
    CHANNEL,
)


def _read_lines(path):
    with open(path, encoding="utf-8") as fp:
        return [json.loads(line) for line in fp if line.strip()]


# ------------------------------------------------------------------
# Default off / activation
# ------------------------------------------------------------------


def test_default_off_returns_null_writer(monkeypatch):
    monkeypatch.delenv(tracing.ENV_TRACE_PATH, raising=False)
    w = resolve_trace_writer()
    assert isinstance(w, NullTraceWriter)


def test_env_var_activates_writer(monkeypatch, tmp_path):
    path = str(tmp_path / "trace.jsonl")
    monkeypatch.setenv(tracing.ENV_TRACE_PATH, path)
    w = resolve_trace_writer(session_id="s1")
    assert isinstance(w, MemoryTraceWriter)
    assert w.path == path


def test_explicit_path_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv(tracing.ENV_TRACE_PATH, str(tmp_path / "env.jsonl"))
    w = resolve_trace_writer(trace_path=str(tmp_path / "explicit.jsonl"))
    assert w.path == str(tmp_path / "explicit.jsonl")


def test_null_writer_is_true_noop():
    w = NullTraceWriter()
    w.write("recall", {"anything": 1})  # must not raise
    w.close()


# ------------------------------------------------------------------
# Envelope integrity
# ------------------------------------------------------------------


def test_envelope_fields_present(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path, session_id="sess-9")
    w.write("write", {"content_hash": "abc"})
    row = _read_lines(path)[0]
    assert row["channel"] == CHANNEL
    assert row["session_id"] == "sess-9"
    assert row["event"] == "write"
    assert "ts" in row
    assert row["content_hash"] == "abc"


def test_writer_creates_parent_dirs(tmp_path):
    path = str(tmp_path / "deep" / "nested" / "trace.jsonl")
    w = MemoryTraceWriter(path)
    w.write("write", {})
    assert os.path.exists(path)


def test_multiple_events_append_in_order(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    with MemoryTraceWriter(path) as w:
        w.write("write", {"n": 1})
        w.write("recall", {"n": 2})
    rows = _read_lines(path)
    assert [r["event"] for r in rows] == ["write", "recall"]


# ------------------------------------------------------------------
# Never-throw / self-disabling
# ------------------------------------------------------------------


def test_unwritable_location_disables_writer_silently(tmp_path):
    # Directory exists but is read-only → open() fails at construction.
    ro_dir = tmp_path / "ro"
    ro_dir.mkdir()
    os.chmod(ro_dir, stat.S_IRUSR | stat.S_IXUSR)
    try:
        w = MemoryTraceWriter(str(ro_dir / "trace.jsonl"))
        assert w.disabled
        w.write("recall", {"x": 1})  # must not raise
    finally:
        os.chmod(ro_dir, stat.S_IRWXU)


def test_io_failure_midlife_disables_writer(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path)
    w.write("write", {"n": 1})
    w._fh.close()  # simulate mid-life I/O breakage
    w.write("write", {"n": 2})  # must not raise
    assert w.disabled
    assert len(_read_lines(path)) == 1  # first event persisted, second dropped


# ------------------------------------------------------------------
# hash-only / full_content
# ------------------------------------------------------------------


def test_log_write_hash_only_by_default(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path)
    log_write(w, content="my secret memory content")
    row = _read_lines(path)[0]
    assert "content" not in row
    assert row["content_bytes"] == len("my secret memory content".encode())
    assert row["content_hash"] == tracing._hash16("my secret memory content")


def test_log_write_full_content_optin(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path)
    log_write(w, content="raw text here", full_content=True)
    row = _read_lines(path)[0]
    assert row["content"] == "raw text here"


def test_hash16_is_stable_and_short():
    h1 = tracing._hash16("stable input")
    h2 = tracing._hash16("stable input")
    assert h1 == h2
    assert len(h1) == 16


# ------------------------------------------------------------------
# Vocabulary events
# ------------------------------------------------------------------


def test_log_recall_fields(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path)
    log_recall(w, trace_id="t1", route="parametric", hit=True,
               n_results=2, latency_ms=0.8123)
    row = _read_lines(path)[0]
    assert row["event"] == "recall"
    assert row["route"] == "parametric"
    assert row["hit"] == 1
    assert row["n_results"] == 2
    assert row["latency_ms"] == 0.812
    assert row["trace_id"] == "t1"
    assert row["gen_ai.operation.name"] == "memory.recall"


def test_log_forget_hashes_key(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path)
    log_forget(w, key="favorite color")
    row = _read_lines(path)[0]
    assert row["event"] == "forget"
    assert row["key_hash"] == tracing._hash16("favorite color")
    assert "key" not in row  # raw key must not leak


def test_log_snapshot_restore(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path)
    log_snapshot(w, binding_count=4, state_bytes=66048)
    log_restore(w, binding_count=4, state_bytes=66048)
    snap, restore = _read_lines(path)
    assert snap["event"] == "snapshot" and snap["binding_count"] == 4
    assert restore["event"] == "restore" and restore["state_bytes"] == 66048


def test_log_conflict_forget_hashes_both_keys(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path)
    log_conflict_forget(w, old_key="old decision", new_key="new decision")
    row = _read_lines(path)[0]
    assert row["event"] == "conflict_forget"
    assert row["old_key_hash"] == tracing._hash16("old decision")
    assert row["new_key_hash"] == tracing._hash16("new decision")
    assert "old_key" not in row and "new_key" not in row


def test_log_degrade(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    w = MemoryTraceWriter(path)
    log_degrade(w, op="parametric_write", reason="mt_lnn.memory_broker not installed")
    row = _read_lines(path)[0]
    assert row["event"] == "broker_unavailable"
    assert row["op"] == "parametric_write"


def test_helpers_never_raise_on_null_writer():
    w = NullTraceWriter()
    log_recall(w, route="parametric", hit=True)
    log_write(w, content="x")
    log_forget(w, key="k")
    log_snapshot(w)
    log_restore(w)
    log_conflict_forget(w, old_key="o", new_key="n")
    log_degrade(w, op="op", reason="r")  # all no-ops, none raise


def test_helpers_never_raise_on_disabled_writer(tmp_path):
    w = MemoryTraceWriter(str(tmp_path / "trace.jsonl"))
    w._disable()
    log_recall(w, route="cascade")
    log_write(w, content="x")  # all silently dropped, none raise
