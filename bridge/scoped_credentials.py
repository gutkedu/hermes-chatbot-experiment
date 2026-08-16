"""Compatibility import for the runtime-packaged scoped credential manager."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_implementation = Path(__file__).resolve().parents[1] / "app" / "hermes" / "bridge" / "scoped_credentials.py"
_spec = importlib.util.spec_from_file_location("_hermes_scoped_credentials", _implementation)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError("runtime scoped credential implementation is unavailable")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
ScopedCredentials = _module.ScopedCredentials

__all__ = ["ScopedCredentials"]
