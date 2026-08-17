"""Safe, credential-free seams around the Amazon Bedrock Guardrails API."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import boto3


class GuardrailServiceError(RuntimeError):
    """Raised when the Guardrails service cannot evaluate content."""

    def __init__(self) -> None:
        super().__init__("Guardrail evaluation failed")


@dataclass(frozen=True)
class GuardrailDecision:
    """The safe result of evaluating one content block."""

    text: str
    intervened: bool
    blocked: bool


def _contains_block_action(value: Any) -> bool:
    """Return whether an assessment contains a blocking action.

    Assessment details are deliberately inspected only for their action names;
    matched values are never copied into logs or exceptions.
    """

    if isinstance(value, dict):
        if value.get("action") == "BLOCK":
            return True
        return any(_contains_block_action(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_block_action(child) for child in value)
    return False


def _contains_anonymize_action(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("action") in {"ANONYMIZED", "ANONYMIZE"}:
            return True
        return any(_contains_anonymize_action(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_anonymize_action(child) for child in value)
    return False


def _first_output_text(response: dict[str, Any]) -> str | None:
    outputs = response.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if isinstance(output, dict) and isinstance(output.get("text"), str):
                return output["text"]
    return None


class GuardrailEvaluator:
    """Apply one immutable Guardrail version to input or output text."""

    def __init__(self, client: Any, guardrail_id: str, guardrail_version: str) -> None:
        self.client = client
        self.guardrail_id = guardrail_id
        self.guardrail_version = guardrail_version

    @classmethod
    def from_environment(cls, env: dict[str, str] | None = None) -> "GuardrailEvaluator | None":
        values = env if env is not None else os.environ
        guardrail_id = values.get("AGENTCORE_GUARDRAIL_ID", "").strip()
        guardrail_version = values.get("AGENTCORE_GUARDRAIL_VERSION", "").strip()
        if not guardrail_id and not guardrail_version:
            return None
        if not guardrail_id or not guardrail_version:
            raise ValueError("Guardrail ID and version must be configured together")
        if not guardrail_version.isdigit() or guardrail_version == "0":
            raise ValueError("Guardrail version must be numbered and immutable")
        region = (
            values.get("AWS_DEFAULT_REGION", "").strip()
            or values.get("AWS_REGION", "").strip()
            or "us-east-1"
        )
        return cls(
            boto3.client("bedrock-runtime", region_name=region),
            guardrail_id,
            guardrail_version,
        )

    def evaluate(self, text: str, *, source: str) -> GuardrailDecision:
        if source not in {"INPUT", "OUTPUT"}:
            raise ValueError("Guardrail source must be INPUT or OUTPUT")
        if not text:
            return GuardrailDecision(text="", intervened=False, blocked=False)
        try:
            response = self.client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source=source,
                content=[{"text": {"text": text}}],
            )
        except Exception:  # noqa: BLE001 - provider details stay private
            raise GuardrailServiceError() from None

        if response.get("action") != "GUARDRAIL_INTERVENED":
            return GuardrailDecision(text=text, intervened=False, blocked=False)

        assessments = response.get("assessments", [])
        output_text = _first_output_text(response)
        blocked = (
            output_text is None
            or not _contains_anonymize_action(assessments)
            or _contains_block_action(assessments)
        )
        safe_message = (
            "I can't help with that request."
            if source == "INPUT"
            else "I can't provide that response."
        )
        return GuardrailDecision(
            text=output_text or safe_message,
            intervened=True,
            blocked=blocked,
        )
