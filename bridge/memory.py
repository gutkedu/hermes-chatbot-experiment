"""Compatibility exports for tests and local imports.

The deployable implementation lives beside the AgentCore entrypoint. The
phase-2 sync preserves that implementation in the Docker build context.
"""

import importlib.util
import sys
from pathlib import Path


_implementation_path = (
    Path(__file__).resolve().parents[1] / "app" / "hermes" / "bridge" / "memory.py"
)
_spec = importlib.util.spec_from_file_location(
    "_hermes_agentcore_memory_implementation", _implementation_path
)
if _spec is None or _spec.loader is None:  # pragma: no cover - repository invariant
    raise ImportError(f"Unable to load {_implementation_path}")
_memory = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _memory
_spec.loader.exec_module(_memory)

boto3 = _memory.boto3
MemoryBridge = _memory.MemoryBridge
AgentCoreMemory = _memory.AgentCoreMemory
Memory = _memory.Memory

__all__ = ["AgentCoreMemory", "Memory", "MemoryBridge"]
