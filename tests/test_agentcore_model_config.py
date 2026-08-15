from bridge.model_config import (
    DEFAULT_BEDROCK_MODEL,
    resolve_bedrock_model,
    resolve_bedrock_settings,
)


def test_agentcore_defaults_to_active_amazon_nova_model(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    assert DEFAULT_BEDROCK_MODEL == "amazon.nova-lite-v1:0"
    assert resolve_bedrock_model() == DEFAULT_BEDROCK_MODEL


def test_agentcore_allows_an_explicit_bedrock_model(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

    assert resolve_bedrock_model() == "amazon.nova-pro-v1:0"


def test_agentcore_uses_bedrock_converse_for_nova(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    assert resolve_bedrock_settings() == {
        "model": "amazon.nova-lite-v1:0",
        "provider": "bedrock",
        "base_url": "https://bedrock-runtime.us-east-1.amazonaws.com",
    }
