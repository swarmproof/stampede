"""Target adapters — "what am I stress-testing?" (ARCHITECTURE §2.1).

One :class:`~stampede.targets.base.TargetAdapter` protocol abstracts the system
under test so the orchestrator is target-agnostic. v0.1 ships:

* :class:`~stampede.targets.mock.MockTarget` — in-process worlds (``crm``,
  ``payments``) for the dry-run pipeline, tests, and the misuse-map demo.
* :class:`~stampede.targets.http.HTTPTarget` — an OpenAPI/REST spec → ToolSet.
* :class:`~stampede.targets.mcp.MCPTarget` — a real MCP server over stdio or
  Streamable HTTP.

The :class:`~stampede.targets.safety.SafetyGate` runs *before* any of them connect.
"""

from __future__ import annotations

from stampede.targets.base import (
    AgentContext,
    HealthStatus,
    IsolationMode,
    SafetyDescriptor,
    TargetAdapter,
    ToolCall,
    ToolResult,
    ToolSet,
    ToolSpec,
)
from stampede.targets.safety import SafetyGate, SafetyViolation

__all__ = [
    "AgentContext",
    "HealthStatus",
    "IsolationMode",
    "SafetyDescriptor",
    "SafetyGate",
    "SafetyViolation",
    "TargetAdapter",
    "ToolCall",
    "ToolResult",
    "ToolSet",
    "ToolSpec",
    "build_target",
]


def build_target(config: "object") -> TargetAdapter:  # noqa: UP037
    """Construct the right adapter from a ``TargetConfig`` (lazy imports keep the
    optional ``mcp`` / ``httpx`` deps out of the core dry-run path)."""
    from stampede.config import TargetConfig

    assert isinstance(config, TargetConfig)
    if config.type == "mock":
        from stampede.targets.mock import MockTarget

        return MockTarget(world=config.world or "crm")
    if config.type == "http":
        from stampede.targets.http import HTTPTarget

        return HTTPTarget(url=config.url, spec=config.spec)
    if config.type == "mcp":
        from stampede.targets.mcp import MCPTarget

        return MCPTarget(
            transport=config.transport, command=config.command, url=config.url
        )
    if config.type == "evm":
        raise NotImplementedError("EVMTarget lands in v0.2 (FR-TA-04)")
    raise ValueError(f"unknown target type: {config.type!r}")
