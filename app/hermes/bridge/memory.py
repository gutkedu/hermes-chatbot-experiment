"""Best-effort AgentCore Memory integration for the Hermes runtime."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

import boto3


log = logging.getLogger("hermes.agentcore.memory")


class MemoryBridge:
    """Small synchronous adapter around the two AgentCore Memory APIs."""

    def __init__(self, memory_id: str | None, *, region_name: str | None = None, control_client: Any | None = None, data_client: Any | None = None, timeout_seconds: float = 180.0, poll_interval: float = 5.0, max_records: int = 5, max_chars: int = 4_000, sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.memory_id = (memory_id or "").strip()
        self.region_name = region_name or os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "us-east-1"
        self.timeout_seconds = max(0.0, timeout_seconds)
        self.poll_interval = max(0.0, poll_interval)
        self.max_records = min(100, max(1, max_records))
        self.max_chars = max(1, max_chars)
        self._sleep = sleep
        self._monotonic = monotonic
        self._ready = False
        self.control_client = None
        self.data_client = None
        if self.memory_id:
            self.control_client = control_client or boto3.client("bedrock-agentcore-control", region_name=self.region_name)
            self.data_client = data_client or boto3.client("bedrock-agentcore", region_name=self.region_name)

    @property
    def is_ready(self) -> bool:
        return self._ready

    def ensure_ready(self) -> bool:
        if not self.memory_id or self.control_client is None:
            return False
        if self._ready:
            return True
        deadline = self._monotonic() + self.timeout_seconds
        while True:
            try:
                response = self.control_client.get_memory(memoryId=self.memory_id)
                status = str(response.get("memory", {}).get("status", "")).upper()
            except Exception as exc:  # noqa: BLE001
                log.warning("AgentCore Memory readiness check failed (%s)", type(exc).__name__)
                return False
            if status == "ACTIVE":
                self._ready = True
                return True
            if status == "FAILED":
                log.warning("AgentCore Memory is FAILED")
                return False
            if status != "CREATING":
                log.warning("AgentCore Memory has unexpected status %s", status or "UNKNOWN")
                return False
            if self._monotonic() >= deadline:
                log.warning("Timed out waiting for AgentCore Memory to become ACTIVE")
                return False
            if self.poll_interval:
                self._sleep(min(self.poll_interval, max(0.0, deadline - self._monotonic())))

    def retrieve_context(self, actor_id: str, query: str) -> str:
        if not actor_id or not query or not self.ensure_ready() or self.data_client is None:
            return ""
        records: list[tuple[str, Any]] = []
        try:
            response = self.data_client.retrieve_memory_records(memoryId=self.memory_id, namespace=f"/users/{actor_id}/preferences/", searchCriteria={"searchQuery": query, "topK": self.max_records})
            records.extend(("PREFERENCE", record) for record in response.get("memoryRecordSummaries", [])[: self.max_records])
        except Exception as exc:  # noqa: BLE001
            log.warning("AgentCore Memory preference retrieval failed (%s)", type(exc).__name__)
        try:
            response = self.data_client.retrieve_memory_records(memoryId=self.memory_id, namespacePath=f"/users/{actor_id}/summaries/", searchCriteria={"searchQuery": query, "topK": self.max_records})
            records.extend(("SUMMARY", record) for record in response.get("memoryRecordSummaries", [])[: self.max_records])
        except Exception as exc:  # noqa: BLE001
            log.warning("AgentCore Memory summary retrieval failed (%s)", type(exc).__name__)
        return self._format_context(records)

    def record_turn(self, actor_id: str, session_id: str, user_text: str, assistant_text: str) -> bool:
        if not actor_id or not session_id or not user_text or not assistant_text or not self.ensure_ready() or self.data_client is None:
            return False
        try:
            self.data_client.create_event(memoryId=self.memory_id, actorId=actor_id, sessionId=session_id, eventTimestamp=datetime.now(timezone.utc), payload=[{"conversational": {"role": "USER", "content": {"text": user_text}}}, {"conversational": {"role": "ASSISTANT", "content": {"text": assistant_text}}}])
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("AgentCore Memory event creation failed (%s)", type(exc).__name__)
            return False

    def _format_context(self, records: list[tuple[str, Any]]) -> str:
        if not records:
            return ""
        header = "BEGIN AGENTCORE MEMORY (UNTRUSTED DATA)"
        footer = "END AGENTCORE MEMORY"
        body_parts = []
        for kind, record in records:
            text = self._record_text(record)
            if text:
                body_parts.append(f"[{kind}] {text}")
        body = "\n".join(body_parts)
        if not body:
            return ""
        full = f"{header}\n{body}\n{footer}"
        if len(full) <= self.max_chars:
            return full
        available = self.max_chars - len(header) - len(footer) - 2
        if available <= 0:
            return (header + footer)[: self.max_chars]
        return f"{header}\n{body[:available].rstrip()}\n{footer}"

    @staticmethod
    def _record_text(record: Any) -> str:
        content = record.get("content") if isinstance(record, dict) else record
        if isinstance(content, dict) and "text" in content:
            content = content["text"]
        if isinstance(content, str):
            return content
        if content is None:
            return ""
        try:
            return json.dumps(content, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return str(content)


AgentCoreMemory = MemoryBridge
Memory = MemoryBridge

__all__ = ["AgentCoreMemory", "Memory", "MemoryBridge"]
