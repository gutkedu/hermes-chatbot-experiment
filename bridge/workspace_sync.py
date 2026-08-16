"""Compatibility import for the implementation packaged with the runtime."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_implementation = Path(__file__).resolve().parents[1] / "app" / "hermes" / "bridge" / "workspace_sync.py"
_spec = importlib.util.spec_from_file_location("_hermes_workspace_sync", _implementation)
if _spec is None or _spec.loader is None:  # pragma: no cover - repository packaging error
    raise ImportError("runtime workspace sync implementation is unavailable")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

for _name in (
    "MAX_SKILL_BYTES",
    "NAMESPACE_RE",
    "RUNTIME_SESSION_RE",
    "SKILL_NAME_RE",
    "SKIP_PATTERNS",
    "NamespaceBindingError",
    "WorkspaceFilesystemError",
    "WorkspaceSync",
    "load_skill_instructions",
    "validate_workspace_namespace",
):
    globals()[_name] = getattr(_module, _name)

__all__ = [
    "MAX_SKILL_BYTES", "NAMESPACE_RE", "RUNTIME_SESSION_RE", "SKILL_NAME_RE", "SKIP_PATTERNS",
    "NamespaceBindingError", "WorkspaceFilesystemError", "WorkspaceSync",
    "load_skill_instructions", "validate_workspace_namespace",
]
