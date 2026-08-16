from __future__ import annotations

from datetime import timezone

from bridge.memory import MemoryBridge


class FakeControlClient:
    def __init__(self, statuses: list[str]):
        self.statuses = iter(statuses)
        self.calls: list[dict] = []

    def get_memory(self, **kwargs):
        self.calls.append(kwargs)
        return {"memory": {"status": next(self.statuses)}}


class FakeDataClient:
    def __init__(self):
        self.retrieve_calls: list[dict] = []
        self.events: list[dict] = []
        self.retrieve_error: Exception | None = None
        self.create_error: Exception | None = None

    def retrieve_memory_records(self, **kwargs):
        self.retrieve_calls.append(kwargs)
        if self.retrieve_error:
            raise self.retrieve_error
        return {
            "memoryRecordSummaries": [
                {"content": "The user prefers concise answers."},
            ]
        }

    def create_event(self, **kwargs):
        if self.create_error:
            raise self.create_error
        self.events.append(kwargs)
        return {"event": {"eventId": "event-1"}}


def ready_bridge(data: FakeDataClient) -> MemoryBridge:
    return MemoryBridge(
        "memory-1234567890",
        region_name="us-east-1",
        control_client=FakeControlClient(["ACTIVE"]),
        data_client=data,
        poll_interval=0,
    )


def test_record_turn_maps_one_user_and_assistant_turn_to_conversational_event():
    data = FakeDataClient()
    bridge = ready_bridge(data)

    assert bridge.record_turn("actor-a", "session-a", "I like blue", "I will remember that.") is True

    assert len(data.events) == 1
    event = data.events[0]
    assert event["memoryId"] == "memory-1234567890"
    assert event["actorId"] == "actor-a"
    assert event["sessionId"] == "session-a"
    assert event["payload"] == [
        {"conversational": {"role": "USER", "content": {"text": "I like blue"}}},
        {"conversational": {"role": "ASSISTANT", "content": {"text": "I will remember that."}}},
    ]
    assert event["eventTimestamp"].tzinfo == timezone.utc
    assert "metadata" not in event


def test_retrieve_context_uses_actor_scoped_preference_and_summary_namespaces():
    data = FakeDataClient()
    bridge = ready_bridge(data)

    bridge.retrieve_context("actor-a", "What should I remember?")
    first_calls = list(data.retrieve_calls)
    data.retrieve_calls.clear()
    bridge.retrieve_context("actor-b", "What should I remember?")

    assert first_calls[0]["namespace"] == "/users/actor-a/preferences/"
    assert first_calls[1]["namespacePath"] == "/users/actor-a/summaries/"
    assert data.retrieve_calls[0]["namespace"] == "/users/actor-b/preferences/"
    assert data.retrieve_calls[1]["namespacePath"] == "/users/actor-b/summaries/"
    assert all(call["memoryId"] == "memory-1234567890" for call in first_calls + data.retrieve_calls)


def test_retrieved_context_is_bounded_and_marked_as_untrusted_data():
    data = FakeDataClient()
    data.retrieve_memory_records = lambda **kwargs: {
        "memoryRecordSummaries": [
            {"content": "A" * 100},
            {"content": "B" * 100},
            {"content": "C" * 100},
        ]
    }
    bridge = MemoryBridge(
        "memory-1234567890",
        region_name="us-east-1",
        control_client=FakeControlClient(["ACTIVE"]),
        data_client=data,
        max_records=2,
        max_chars=80,
        poll_interval=0,
    )

    context = bridge.retrieve_context("actor-a", "preferences")

    assert context.startswith("BEGIN AGENTCORE MEMORY (UNTRUSTED DATA)")
    assert context.endswith("END AGENTCORE MEMORY")
    assert len(context) <= 80


def test_ensure_ready_waits_from_creating_until_active():
    control = FakeControlClient(["CREATING", "CREATING", "ACTIVE"])
    bridge = MemoryBridge(
        "memory-1234567890",
        region_name="us-east-1",
        control_client=control,
        data_client=FakeDataClient(),
        timeout_seconds=10,
        poll_interval=0,
    )

    assert bridge.ensure_ready() is True
    assert len(control.calls) == 3


def test_failed_memory_and_timeout_are_safe_for_chat():
    failed = MemoryBridge(
        "memory-1234567890",
        region_name="us-east-1",
        control_client=FakeControlClient(["FAILED"]),
        data_client=FakeDataClient(),
        poll_interval=0,
    )
    timeout = MemoryBridge(
        "memory-1234567890",
        region_name="us-east-1",
        control_client=FakeControlClient(["CREATING"]),
        data_client=FakeDataClient(),
        timeout_seconds=0,
        poll_interval=0,
    )

    assert failed.retrieve_context("actor-a", "query") == ""
    assert failed.record_turn("actor-a", "session-a", "hello", "hi") is False
    assert timeout.retrieve_context("actor-a", "query") == ""


def test_memory_data_plane_errors_are_absorbed():
    data = FakeDataClient()
    data.retrieve_error = RuntimeError("retrieve unavailable")
    data.create_error = RuntimeError("create unavailable")
    bridge = ready_bridge(data)

    assert bridge.retrieve_context("actor-a", "query") == ""
    assert bridge.record_turn("actor-a", "session-a", "hello", "hi") is False


def test_missing_memory_id_disables_memory_without_creating_clients(monkeypatch):
    calls: list[tuple[str, str]] = []

    def client(service_name, *, region_name):
        calls.append((service_name, region_name))
        raise AssertionError("client should not be created without a memory id")

    monkeypatch.setattr("bridge.memory.boto3.client", client)
    bridge = MemoryBridge(None, region_name="us-east-1")

    assert bridge.ensure_ready() is False
    assert bridge.retrieve_context("actor-a", "query") == ""
    assert bridge.record_turn("actor-a", "session-a", "hello", "hi") is False
    assert calls == []


def test_memory_uses_separate_boto_clients_with_explicit_region(monkeypatch):
    clients: list[tuple[str, str]] = []

    class Client:
        def get_memory(self, **_kwargs):
            return {"memory": {"status": "ACTIVE"}}

    def client(service_name, *, region_name):
        clients.append((service_name, region_name))
        return Client()

    monkeypatch.setattr("bridge.memory.boto3.client", client)
    MemoryBridge("memory-1234567890", region_name="sa-east-1")

    assert clients == [
        ("bedrock-agentcore-control", "sa-east-1"),
        ("bedrock-agentcore", "sa-east-1"),
    ]
