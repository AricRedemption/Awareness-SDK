"""Quickstart for the Parametric memory adapter.

Demonstrates:
1. Constructing ``MemoryCloudParametric`` with and without a broker.
2. Direct parametric write / recall / forget.
3. Bit-exact snapshot → restore round-trip.
4. Graceful degradation when ``mt_lnn.memory_broker`` is not installed.

Run::

    python -m examples.parametric_quickstart
"""

from unittest.mock import MagicMock

from memory_cloud import MemoryCloudClient
from memory_cloud.integrations.parametric import MemoryCloudParametric


def _mock_cloud_client() -> MemoryCloudClient:
    """A mock client so the example runs without a live daemon or cloud."""
    client = MagicMock(spec=MemoryCloudClient)
    client._begin_memory_session = MagicMock(return_value={"session_id": "sess-demo"})
    client.retrieve = MagicMock(return_value={"results": []})
    client.record = MagicMock(return_value={"status": "ok", "events_sent": 1})
    client.insights = MagicMock(return_value={"knowledge_cards": [], "risks": [], "action_items": []})
    return client


def main() -> None:
    client = _mock_cloud_client()

    # --- Without a broker: graceful degradation ----------------------------
    mc = MemoryCloudParametric(client=client, memory_id="mem-demo")
    print(f"broker_available: {mc.broker_available}")
    print(f"source: {mc.source}")
    print(f"session_id: {mc.session_id}")

    # These are no-ops when the broker is absent — no exceptions.
    result = mc.parametric_write("s1", key="color", value="blue")
    print(f"write (no broker): {result}")

    hits = mc.parametric_recall("s1", query="color")
    print(f"recall (no broker): {hits}")

    snap = mc.parametric_snapshot("s1")
    print(f"snapshot (no broker): {snap}")

    # --- With a broker (if mt_lnn.memory_broker is installed) --------------
    if mc.broker_available:
        print("\n--- Broker available: live parametric operations ---")
        mc.parametric_write("s1", key="favorite color", value="blue")
        mc.parametric_write("s1", key="favorite food", value="sushi")

        hits = mc.parametric_recall("s1", query="favorite color", top_k=3)
        print(f"recall 'favorite color': {hits}")

        # Snapshot → restore round-trip (bit-exact)
        snap = mc.parametric_snapshot("s1")
        mc.parametric_forget("s1")  # wipe session
        assert mc.parametric_recall("s1", query="favorite color") == []
        mc.parametric_restore("s1", snap)
        hits_after = mc.parametric_recall("s1", query="favorite color", top_k=3)
        print(f"recall after restore: {hits_after}")

        # Surgical forget of one binding
        mc.parametric_forget("s1", key="favorite color")
        hits_after_forget = mc.parametric_recall("s1", query="favorite color", top_k=3)
        print(f"recall after forget 'favorite color': {hits_after_forget}")
    else:
        print("\nmt_lnn.memory_broker not installed — skipping live operations.")
        print("Install with: pip install 'awareness-memory-cloud[parametric]'")

    # --- Shared surface (works with or without broker) ---------------------
    tools = mc.get_tool_functions()
    print(f"\ntool functions: {[t['name'] for t in tools]}")
    print(f"memory_search: {mc.memory_search('test query')}")


if __name__ == "__main__":
    main()
