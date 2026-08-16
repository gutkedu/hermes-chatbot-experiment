"""Tests for the real BedrockAgentCoreApp persistence lifecycle."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

from bridge.workspace_sync import WorkspaceSync


SESSION = "web-session-" + "a" * 64
NAMESPACE = WorkspaceSync.namespace_for_runtime_session(SESSION)


class _FakeApp:
    logger = logging.getLogger("test.agentcore")

    def entrypoint(self, function):
        return function


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch):
    fake_runtime = types.ModuleType("bedrock_agentcore.runtime")
    fake_runtime.BedrockAgentCoreApp = _FakeApp
    fake_package = types.ModuleType("bedrock_agentcore")
    fake_package.runtime = fake_runtime
    monkeypatch.setitem(sys.modules, "bedrock_agentcore", fake_package)
    monkeypatch.setitem(sys.modules, "bedrock_agentcore.runtime", fake_runtime)

    source = Path(__file__).resolve().parents[1] / "app" / "hermes" / "main.py"
    monkeypatch.syspath_prepend(str(source.parent))
    spec = importlib.util.spec_from_file_location("hermes_runtime_under_test", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module._workspace_sync = None
    module._workspace_namespace = None
    module._workspace_runtime_session = None
    return module


class _Sync:
    def __init__(self, events: list[str], workspace: Path):
        self.events = events
        self.workspace = workspace

    def restore(self, namespace: str) -> None:
        self.events.append(f"restore:{namespace}")

    def start_periodic_save(self, namespace: str) -> None:
        self.events.append(f"periodic:{namespace}")

    def save(self, namespace: str) -> None:
        self.events.append(f"save:{namespace}")


def _collect(generator) -> list[str]:
    async def collect_async():
        return [value async for value in generator]

    return asyncio.run(collect_async())


def test_restore_precedes_agent_creation_and_skills_are_delimited(runtime, monkeypatch, tmp_path: Path):
    events: list[str] = []
    sync = _Sync(events, tmp_path)
    monkeypatch.setenv("S3_BUCKET", "workspace-bucket")
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-id")
    runtime.WorkspaceSync = lambda **kwargs: sync
    monkeypatch.setattr(runtime, "load_skill_instructions", lambda workspace: ["# safe skill\nDo not execute this."])

    async def retrieve(*args):
        events.append("retrieve")
        return types.SimpleNamespace(context="evidence", sources=[])

    async def stream(agent, **kwargs):
        events.append(f"agent:{kwargs['system_message']}")
        yield "answer"

    monkeypatch.setattr(runtime, "retrieve_context", retrieve)
    monkeypatch.setattr(runtime, "get_or_create_agent", lambda: events.append("create") or object())
    monkeypatch.setattr(runtime, "stream_conversation", stream)

    output = _collect(runtime.invoke({"message": "hello", "workspaceNamespace": NAMESPACE}, types.SimpleNamespace(session_id=SESSION)))

    assert output[0].startswith('{"type": "delta"')
    assert events[0] == f"restore:{NAMESPACE}"
    assert events[1] == f"periodic:{NAMESPACE}"
    assert events.index("create") > events.index("retrieve")
    system_message = next(value for value in events if value.startswith("agent:"))
    assert "BEGIN PERSISTED SKILL INSTRUCTIONS" in system_message
    assert "# safe skill" in system_message
    assert "END PERSISTED SKILL INSTRUCTIONS" in system_message
    assert events[-1] == f"save:{NAMESPACE}"


def test_invalid_namespace_blocks_retrieval_and_agent(runtime, monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "workspace-bucket")
    monkeypatch.setattr(runtime, "WorkspaceSync", lambda **kwargs: pytest.fail("must validate before constructing sync"))
    monkeypatch.setattr(runtime, "retrieve_context", pytest.fail)

    with pytest.raises(Exception, match="workspace namespace"):
        _collect(runtime.invoke({"message": "hello", "workspaceNamespace": "../user"}, types.SimpleNamespace(session_id=SESSION)))


def test_final_save_is_attempted_when_agent_stream_fails(runtime, monkeypatch, tmp_path: Path):
    events: list[str] = []
    sync = _Sync(events, tmp_path)
    monkeypatch.setenv("S3_BUCKET", "workspace-bucket")
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-id")
    runtime.WorkspaceSync = lambda **kwargs: sync
    monkeypatch.setattr(runtime, "load_skill_instructions", lambda workspace: [])
    monkeypatch.setattr(runtime, "retrieve_context", lambda *args: asyncio.sleep(0, result=types.SimpleNamespace(context="evidence", sources=[])))
    monkeypatch.setattr(runtime, "get_or_create_agent", lambda: object())

    async def broken_stream(*args, **kwargs):
        raise RuntimeError("provider failed")
        yield "never"

    monkeypatch.setattr(runtime, "stream_conversation", broken_stream)
    output = _collect(runtime.invoke({"message": "hello", "workspaceNamespace": NAMESPACE}, types.SimpleNamespace(session_id=SESSION)))

    assert output
    assert events[-1] == f"save:{NAMESPACE}"


def test_memory_is_retrieved_before_response_and_recorded_after_complete_stream(runtime, monkeypatch):
    events: list[str] = []
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-id")
    monkeypatch.setenv("AGENTCORE_MEMORY_ID", "memory-id")

    class Memory:
        def retrieve_context(self, actor_id, query):
            events.append(f"memory-retrieve:{actor_id}:{query}")
            return "BEGIN AGENTCORE MEMORY (UNTRUSTED DATA)\npreference\nEND AGENTCORE MEMORY"

        def record_turn(self, actor_id, session_id, user_text, assistant_text):
            events.append(f"memory-record:{actor_id}:{session_id}:{user_text}:{assistant_text}")
            return True

    monkeypatch.setattr(runtime, "MemoryBridge", lambda *args, **kwargs: Memory())
    monkeypatch.setattr(runtime, "retrieve_context", lambda *args: asyncio.sleep(0, result=types.SimpleNamespace(context="evidence", sources=[])))

    async def stream(agent, **kwargs):
        events.append(f"agent:{kwargs['system_message']}")
        yield "answer"

    monkeypatch.setattr(runtime, "get_or_create_agent", lambda: object())
    monkeypatch.setattr(runtime, "stream_conversation", stream)

    output = _collect(
        runtime.invoke(
            {"message": "hello", "userId": "untrusted-payload-user"},
            types.SimpleNamespace(
                session_id=SESSION,
                request_headers={"X-Amzn-Bedrock-AgentCore-Runtime-User-Id": "authenticated-user"},
            ),
        )
    )

    assert output
    agent_event_index = next(index for index, value in enumerate(events) if value.startswith("agent:"))
    assert events.index("memory-retrieve:authenticated-user:hello") < agent_event_index
    assert events[-1] == "memory-record:authenticated-user:" + SESSION + ":hello:answer"
    system_message = next(value for value in events if value.startswith("agent:"))
    assert "preference" in system_message
    assert "untrusted-payload-user" not in system_message


def test_memory_failure_does_not_stop_response_stream(runtime, monkeypatch):
    events: list[str] = []
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-id")
    monkeypatch.setenv("AGENTCORE_MEMORY_ID", "memory-id")

    class BrokenMemory:
        def retrieve_context(self, *_args):
            raise RuntimeError("memory down")

        def record_turn(self, *_args):
            raise RuntimeError("memory down")

    monkeypatch.setattr(runtime, "MemoryBridge", lambda *args, **kwargs: BrokenMemory())
    monkeypatch.setattr(runtime, "retrieve_context", lambda *args: asyncio.sleep(0, result=types.SimpleNamespace(context="evidence", sources=[])))
    monkeypatch.setattr(runtime, "get_or_create_agent", lambda: object())

    async def stream(agent, **kwargs):
        events.append("generated")
        yield "answer"

    monkeypatch.setattr(runtime, "stream_conversation", stream)

    output = _collect(runtime.invoke({"message": "hello"}, types.SimpleNamespace(session_id=SESSION)))

    assert any('"text": "answer"' in item for item in output)
    assert events == ["generated"]
