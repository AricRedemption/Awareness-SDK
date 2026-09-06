"""SDK-level structured trace for memory operations (F-069).

Produces the runtime evidence consumed by GOVERNANCE.md's direction
review (§5): recall routes/hits/latency, broker degradation frequency,
migration binding counts.

Design:
- Envelope borrowed from M1's ``JsonlMetricWriter`` —
  ``{ts, event, session_id, channel, ...fields}``, one JSON per line —
  so SDK and M1 events can be joined by ``session_id`` when the broker
  lands.  Extended field naming follows OpenTelemetry GenAI semantic
  conventions (``gen_ai.*``) where applicable; a documented mapping
  (below) keeps a future OTel bridge to ~20 lines.  No OTel dependency
  in the core package.
- Default OFF: ``trace_path=None`` (or unset ``AWARENESS_TRACE_PATH``)
  yields a singleton no-op writer with zero overhead.
- hash-only by default: content is recorded as ``content_bytes`` +
  ``content_hash`` (sha256, first 16 hex chars).  ``full_content=True``
  opts in to recording raw text.
- Never throws: any write failure silently disables the writer for the
  rest of its life (same philosophy as the daemon's log-writer).

OTel mapping (documented, not code)::

    event "recall"  -> span "memory recall"    gen_ai.operation.name="memory.recall"
    event "write"   -> span "memory write"     gen_ai.operation.name="memory.write"
    event "forget"  -> span "memory forget"    gen_ai.operation.name="memory.forget"
    session_id      -> gen_ai.session.id (custom, non-standard)
    route           -> memory.route (custom, non-standard)
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

CHANNEL = "memory_trace"

ENV_TRACE_PATH = "AWARENESS_TRACE_PATH"


def _hash16(text: str) -> str:
    """sha256 of text, first 16 hex chars — stable, non-reversible."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _content_fields(content: Any, full_content: bool) -> Dict[str, Any]:
    """Content summary fields: bytes + hash always; raw text only on opt-in."""
    text = content if isinstance(content, str) else str(content)
    fields: Dict[str, Any] = {
        "content_bytes": len(text.encode("utf-8", errors="replace")),
        "content_hash": _hash16(text),
    }
    if full_content:
        fields["content"] = text
    return fields


class NullTraceWriter:
    """No-op writer — the default when tracing is off. Zero overhead."""

    def write(self, event: str, fields: Optional[Dict[str, Any]] = None) -> None:
        pass

    def close(self) -> None:
        pass


class MemoryTraceWriter:
    """Append-only JSONL trace writer. Never raises.

    static fields (channel, session_id) are stamped into every event.
    On any I/O failure the writer disables itself permanently — a broken
    trace must never break memory operations.
    """

    def __init__(self, path: str, session_id: str = "default"):
        self.path = path
        self.session_id = session_id
        self._static = {"channel": CHANNEL, "session_id": session_id}
        self._lock = threading.Lock()
        self._disabled = False
        self._fh = None
        try:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._fh = open(path, "a", encoding="utf-8")
        except Exception:
            self._fh = None
            self._disabled = True

    def write(self, event: str, fields: Optional[Dict[str, Any]] = None) -> None:
        if self._disabled or self._fh is None:
            return
        row: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **self._static,
        }
        if fields:
            row.update(fields)
        try:
            with self._lock:
                self._fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                self._fh.flush()
        except Exception:
            self._disable()

    def _disable(self) -> None:
        self._disabled = True
        try:
            if self._fh is not None:
                self._fh.close()
        except Exception:
            pass
        self._fh = None

    @property
    def disabled(self) -> bool:
        return self._disabled

    def close(self) -> None:
        self._disable()

    def __enter__(self) -> "MemoryTraceWriter":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def resolve_trace_writer(
    trace_path: Optional[str] = None,
    session_id: str = "default",
) -> Any:
    """Return a MemoryTraceWriter when tracing is on, else the Null no-op.

    Precedence: explicit ``trace_path`` > ``AWARENESS_TRACE_PATH`` env > off.
    """
    path = trace_path or os.environ.get(ENV_TRACE_PATH) or ""
    if not path.strip():
        return NullTraceWriter()
    return MemoryTraceWriter(path.strip(), session_id=session_id)


# ---------------------------------------------------------------------------
# Semantic emit helpers — call sites use these instead of raw write() so the
# event vocabulary stays in one place (F-069: vocabulary changes need an ADR).
# ---------------------------------------------------------------------------


def log_recall(
    writer: Any,
    *,
    trace_id: Optional[str] = None,
    route: str = "cascade",
    hit: bool = False,
    n_results: int = 0,
    latency_ms: Optional[float] = None,
) -> None:
    """route: parametric | cascade | daemon | cloud."""
    fields: Dict[str, Any] = {
        "gen_ai.operation.name": "memory.recall",
        "route": route,
        "hit": 1 if hit else 0,
        "n_results": n_results,
    }
    if trace_id:
        fields["trace_id"] = trace_id
    if latency_ms is not None:
        fields["latency_ms"] = round(latency_ms, 3)
    writer.write("recall", fields)


def log_write(
    writer: Any,
    *,
    trace_id: Optional[str] = None,
    content: Any = "",
    full_content: bool = False,
) -> None:
    fields: Dict[str, Any] = {"gen_ai.operation.name": "memory.write"}
    fields.update(_content_fields(content, full_content))
    if trace_id:
        fields["trace_id"] = trace_id
    writer.write("write", fields)


def log_forget(writer: Any, *, key: Any = None) -> None:
    fields: Dict[str, Any] = {"gen_ai.operation.name": "memory.forget"}
    if key is not None:
        fields["key_hash"] = _hash16(str(key))
    writer.write("forget", fields)


def log_snapshot(
    writer: Any,
    *,
    binding_count: Optional[int] = None,
    state_bytes: Optional[int] = None,
) -> None:
    fields: Dict[str, Any] = {"gen_ai.operation.name": "memory.snapshot"}
    if binding_count is not None:
        fields["binding_count"] = binding_count
    if state_bytes is not None:
        fields["state_bytes"] = state_bytes
    writer.write("snapshot", fields)


def log_restore(
    writer: Any,
    *,
    binding_count: Optional[int] = None,
    state_bytes: Optional[int] = None,
) -> None:
    fields: Dict[str, Any] = {"gen_ai.operation.name": "memory.restore"}
    if binding_count is not None:
        fields["binding_count"] = binding_count
    if state_bytes is not None:
        fields["state_bytes"] = state_bytes
    writer.write("restore", fields)


def log_conflict_forget(
    writer: Any,
    *,
    old_key: Any = None,
    new_key: Any = None,
) -> None:
    """Emitted when a conflict decision (this repo's card-evolution, F-066)
    executes forget(old)+write(new) at the parametric layer.

    Note: the current emitter for this event is the future JS↔Python broker
    bridge (the conflict decision lives in the daemon, F-066); the Python
    vocabulary slot is reserved so the bridge can use it without an ADR.
    """
    fields: Dict[str, Any] = {"gen_ai.operation.name": "memory.conflict_forget"}
    if old_key is not None:
        fields["old_key_hash"] = _hash16(str(old_key))
    if new_key is not None:
        fields["new_key_hash"] = _hash16(str(new_key))
    writer.write("conflict_forget", fields)


def log_degrade(writer: Any, *, op: str, reason: str) -> None:
    """Any silent-degradation path emits this — degradation must be observable."""
    writer.write("broker_unavailable", {"op": op, "reason": reason})
