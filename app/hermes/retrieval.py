"""Evidence-only retrieval for Hermes product-support responses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse


@dataclass(frozen=True)
class RetrievalResult:
    context: str | None
    sources: list[dict[str, str]]


def _source(result: dict) -> dict[str, str] | None:
    text = (result.get("content") or {}).get("text", "").strip()
    uri = ((result.get("location") or {}).get("s3Location") or {}).get("uri") or (result.get("metadata") or {}).get("x-amz-bedrock-kb-source-uri", "")
    key = urlparse(uri).path.lstrip("/")
    if not text or not key:
        return None
    return {"title": PurePosixPath(key).name, "identifier": key, "excerpt": text[:500]}


async def retrieve_context(client, knowledge_base_id: str, query: str) -> RetrievalResult:
    """Retrieve only grounded evidence; failures deliberately reveal no context."""
    try:
        response = client.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 3, "overrideSearchType": "SEMANTIC"}},
        )
    except Exception:
        return RetrievalResult(context=None, sources=[])
    sources = [source for item in response.get("retrievalResults", [])[:3] if (source := _source(item))]
    if not sources:
        return RetrievalResult(context=None, sources=[])
    evidence = "\n\n".join(f"[{item['identifier']}]\n{item['excerpt']}" for item in sources)
    return RetrievalResult(context=f"<retrieved_evidence>\n{evidence}\n</retrieved_evidence>", sources=sources)
