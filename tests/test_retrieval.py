from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "hermes"))
from retrieval import retrieve_context


def _collect(client, query: str = "Qual é o prazo?"):
    return asyncio.run(retrieve_context(client, "kb-123", query))


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None

    def retrieve(self, **kwargs):
        self.request = kwargs
        if self.error:
            raise self.error
        return self.response


def test_retrieval_builds_delimited_context_and_sources_from_semantic_results():
    client = _Client({
        "retrievalResults": [{
            "content": {"text": "A devolução pode ser solicitada em até 30 dias corridos após a entrega."},
            "location": {"s3Location": {"uri": "s3://private-documents/knowledge-base/lumen-desk-lamp.md"}},
            "metadata": {"x-amz-bedrock-kb-source-uri": "s3://private-documents/knowledge-base/lumen-desk-lamp.md"},
        }],
    })

    result = _collect(client)

    assert client.request == {
        "knowledgeBaseId": "kb-123",
        "retrievalQuery": {"text": "Qual é o prazo?"},
        "retrievalConfiguration": {
            "vectorSearchConfiguration": {"numberOfResults": 3, "overrideSearchType": "SEMANTIC"},
        },
    }
    assert "<retrieved_evidence>" in result.context
    assert "30 dias corridos" in result.context
    assert result.sources == [{
        "title": "lumen-desk-lamp.md",
        "identifier": "knowledge-base/lumen-desk-lamp.md",
        "excerpt": "A devolução pode ser solicitada em até 30 dias corridos após a entrega.",
    }]


def test_retrieval_returns_no_evidence_when_bedrock_finds_no_results():
    result = _collect(_Client({"retrievalResults": []}))

    assert result.context is None
    assert result.sources == []


def test_retrieval_returns_no_evidence_when_bedrock_fails():
    result = _collect(_Client(error=RuntimeError("unavailable")))

    assert result.context is None
    assert result.sources == []
