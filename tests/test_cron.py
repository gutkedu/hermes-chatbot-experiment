"""Cron adapter identity and workspace namespace tests."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock


def _module(monkeypatch):
    monkeypatch.setenv("AGENTCORE_RUNTIME_ARN", "arn:aws:bedrock-agentcore:region:1:runtime/x")
    source = Path(__file__).resolve().parents[1] / "lambda" / "cron" / "index.py"
    spec = importlib.util.spec_from_file_location("hermes_cron_under_test", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cron_derives_runtime_identity_and_workspace_namespace(monkeypatch):
    module = _module(monkeypatch)
    client = MagicMock()
    client.invoke_agent_runtime.return_value = {"payload": io.BytesIO(json.dumps({"response": "ok"}).encode())}
    module._agentcore_client = client
    module._deliver = lambda *args: None

    result = module.handler({
        "jobId": "daily",
        "userId": "user_abc123",
        "prompt": "summarize",
    }, None)

    call = client.invoke_agent_runtime.call_args.kwargs
    payload = json.loads(call["payload"])
    assert call["runtimeUserId"].startswith("cron-user-")
    assert not call["runtimeUserId"].startswith("cron:user")
    assert payload["workspaceNamespace"].startswith("ws-")
    assert len(payload["workspaceNamespace"]) == 67
    assert "actorId" not in payload
    assert result["status"] == "ok"
