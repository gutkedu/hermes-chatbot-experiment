"""Compatibility helpers for Bedrock model-specific request differences."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


def _is_nova_model(model: str) -> bool:
    return model.strip().lower().startswith("amazon.nova")


def _without_cache_points(value: Any) -> Any:
    if isinstance(value, list):
        return [item for item in (_without_cache_points(item) for item in value) if item != {}]
    if isinstance(value, dict):
        if set(value) == {"cachePoint"}:
            return {}
        return {
            key: _without_cache_points(child)
            for key, child in value.items()
            if key != "cachePoint"
        }
    return value


def strip_nova_tool_cache_points(request: dict[str, Any], model: str) -> dict[str, Any]:
    """Remove cache markers rejected by the deployed Nova model."""
    if not _is_nova_model(model):
        return request

    result = _without_cache_points(deepcopy(request))
    tool_config = result.get("toolConfig")
    if not isinstance(tool_config, dict):
        return result

    tools = tool_config.get("tools")
    if not isinstance(tools, list):
        return result

    tool_config["tools"] = [tool for tool in tools if "cachePoint" not in tool]
    if not tool_config["tools"]:
        result.pop("toolConfig", None)
    return result


def install_nova_bedrock_compat() -> None:
    """Patch Hermes' shared Converse builder for the Nova runtime only."""
    from agent import bedrock_adapter

    if getattr(bedrock_adapter, "_hermes_nova_tool_cache_compat", False):
        return

    original: Callable[..., dict[str, Any]] = bedrock_adapter.build_converse_kwargs

    def build_converse_kwargs(*args: Any, **kwargs: Any) -> dict[str, Any]:
        request = original(*args, **kwargs)
        model = kwargs.get("model")
        if model is None and args:
            model = args[0]
        return strip_nova_tool_cache_points(request, str(model or ""))

    bedrock_adapter.build_converse_kwargs = build_converse_kwargs
    bedrock_adapter._hermes_nova_tool_cache_compat = True
