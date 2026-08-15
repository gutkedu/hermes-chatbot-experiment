from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bridge.streaming import stream_conversation


def collect(generator):
    async def _collect():
        return [item async for item in generator]

    return asyncio.run(_collect())


class _StreamingAgent:
    def run_conversation(self, *, stream_callback, **_kwargs):
        stream_callback("Hel")
        stream_callback("lo")
        return {"final_response": "Hello"}


class _FallbackAgent:
    def run_conversation(self, *, stream_callback, **_kwargs):
        assert callable(stream_callback)
        return {"final_response": "fallback"}


class _FailingAgent:
    def run_conversation(self, *, stream_callback, **_kwargs):
        stream_callback("partial")
        raise RuntimeError("agent failed")


def test_streaming_agent_does_not_duplicate_final_response():
    assert collect(stream_conversation(_StreamingAgent(), user_message="hello")) == ["Hel", "lo"]


def test_non_streaming_agent_uses_final_response_fallback():
    assert collect(stream_conversation(_FallbackAgent(), user_message="hello")) == ["fallback"]


def test_agent_exception_is_propagated():
    with pytest.raises(RuntimeError, match="agent failed"):
        collect(stream_conversation(_FailingAgent(), user_message="hello"))


def test_agentcore_copy_matches_source():
    root = Path(__file__).resolve().parents[1]
    assert (root / "bridge" / "streaming.py").read_text() == (
        root / "app" / "hermes" / "bridge" / "streaming.py"
    ).read_text()
