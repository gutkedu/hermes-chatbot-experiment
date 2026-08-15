"""Model configuration shared by the AgentCore runtime entrypoints."""

from __future__ import annotations

import os
from collections.abc import Mapping


DEFAULT_BEDROCK_MODEL = "amazon.nova-lite-v1:0"


def _environment(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return os.environ if env is None else env


def resolve_bedrock_model(env: Mapping[str, str] | None = None) -> str:
    """Return the configured Bedrock model, defaulting to Amazon Nova Lite."""
    return _environment(env).get("BEDROCK_MODEL_ID", "").strip() or DEFAULT_BEDROCK_MODEL


def resolve_bedrock_settings(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the provider settings required by Hermes' Bedrock Converse path."""
    values = _environment(env)
    region = (
        values.get("AWS_REGION", "").strip()
        or values.get("AWS_DEFAULT_REGION", "").strip()
        or "us-east-1"
    )
    return {
        "model": resolve_bedrock_model(values),
        "provider": "bedrock",
        "base_url": f"https://bedrock-runtime.{region}.amazonaws.com",
    }
