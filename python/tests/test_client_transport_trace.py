"""F-072: client transport failures emit transport_error trace events.

Covers the two choke points: cloud REST (`_request_response`) and the local
daemon RPC bridge (`call_local_daemon`).  Emits only on FINAL failure —
retryable intermediate attempts are not events.
"""

import json

import pytest
import requests

from memory_cloud.client import MemoryCloudClient
from memory_cloud.errors import MemoryCloudError


def _client(tmp_path, **kwargs):
    path = str(tmp_path / "trace.jsonl")
    client = MemoryCloudClient(
        api_key="k", trace_path=path, max_retries=1, backoff_seconds=0.0, **kwargs
    )
    return client, path


def _rows(path):
    with open(path, encoding="utf-8") as fp:
        return [json.loads(line) for line in fp if line.strip()]


def test_cloud_connect_error_emits_transport_error(tmp_path):
    client, path = _client(tmp_path)
    failing = requests.Session()

    def raise_connect(*a, **kw):
        raise requests.exceptions.ConnectionError("refused")

    failing.request = raise_connect
    client.session = failing
    with pytest.raises(MemoryCloudError):
        client.list_memories()
    rows = _rows(path)
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "transport_error"
    assert row["route"] == "cloud"
    assert row["error_class"] == "connect"
    assert row["op"] == "list_memories"
    assert "latency_ms" in row


def test_cloud_timeout_classified_as_timeout(tmp_path):
    client, path = _client(tmp_path)
    failing = requests.Session()

    def raise_timeout(*a, **kw):
        raise requests.exceptions.Timeout("too slow")

    failing.request = raise_timeout
    client.session = failing
    with pytest.raises(MemoryCloudError):
        client.get_memory("m1")
    assert _rows(path)[0]["error_class"] == "timeout"


def test_cloud_http_status_emits_once_not_per_retry(tmp_path):
    client, path = _client(tmp_path)
    failing = requests.Session()
    calls = {"n": 0}

    def fake_request(*a, **kw):
        calls["n"] += 1
        return _response(503)

    failing.request = fake_request
    client.session = failing
    with pytest.raises(MemoryCloudError):
        client.get_memory("m1")
    assert calls["n"] == 2  # max_retries=1 → two attempts
    rows = _rows(path)
    assert len(rows) == 1  # but only ONE event (final failure)
    assert rows[0]["error_class"] == "http_status"
    assert rows[0]["status"] == 503


def test_daemon_connect_error_emits_transport_error(tmp_path):
    client, path = _client(tmp_path, mode="local")
    failing = requests.Session()

    def raise_connect(*a, **kw):
        raise requests.exceptions.ConnectionError("daemon down")

    failing.post = raise_connect
    client.session = failing
    with pytest.raises(MemoryCloudError):
        client.call_local_daemon("awareness_recall", {"query": "q"})
    rows = _rows(path)
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "transport_error"
    assert row["route"] == "daemon"
    assert row["error_class"] == "connect"
    assert row["op"] == "recall"


def test_daemon_http_status_emits_transport_error(tmp_path):
    client, path = _client(tmp_path, mode="local")
    failing = requests.Session()
    failing.post = lambda *a, **kw: _response(500, text="boom")
    client.session = failing
    with pytest.raises(MemoryCloudError):
        client.call_local_daemon("awareness_record", {"content": "c"})
    row = _rows(path)[0]
    assert row["op"] == "record"
    assert row["error_class"] == "http_status"
    assert row["status"] == 500


def test_success_path_emits_no_transport_error(tmp_path):
    client, path = _client(tmp_path)
    ok = requests.Session()
    ok.request = lambda *a, **kw: _response(200, body=[])
    client.session = ok
    client.list_memories()
    rows = _rows(path)
    assert not [r for r in rows if r["event"] == "transport_error"]


def _response(status, body=None, text=""):
    resp = requests.Response()
    resp.status_code = status
    resp._content = (text or json.dumps(body if body is not None else {})).encode()
    resp.headers["Content-Type"] = "application/json"
    return resp
