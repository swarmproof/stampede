"""Target adapter interface + shared data types (ARCHITECTURE §2.1, FR-TA-03).

The adapter contract is given as an abstract base class rather than a bare
``Protocol`` so adapters inherit sensible defaults (``reset``/``health``/
``isolation``) and only override what differs.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IsolationMode(StrEnum):
    """How target state is isolated across agents (FR-TA-06)."""

    PER_AGENT = "per_agent"  # each agent gets a private state (no confounding)
    PER_WAVE = "per_wave"  # reset() between waves
    SHARED = "shared"  # one shared state; confounding documented


@dataclass
class ToolSpec:
    """One tool the agents may call. ``input_schema`` is JSON Schema."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    tool_type: str = "function"  # OTel gen_ai.tool.type: function | extension | datastore
    # Side-effect hints used by chaos/exactly-once and cost modelling.
    destructive: bool = False  # deleting/irreversible → recovery cares
    idempotency_arg: str | None = None  # arg name that keys exactly-once, if any


@dataclass
class ToolSet:
    tools: list[ToolSpec] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    def names(self) -> list[str]:
        return [t.name for t in self.tools]

    def get(self, name: str) -> ToolSpec | None:
        return next((t for t in self.tools if t.name == name), None)


@dataclass
class AgentContext:
    """The slice of agent state a target invocation needs."""

    agent_id: str
    persona: str = ""
    traceparent: str | None = None  # injected for target-side span nesting
    isolation_key: str = "shared"  # which state bucket this agent reads/writes


@dataclass
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    ok: bool
    content: str = ""
    structured: dict[str, Any] | None = None
    is_error: bool = False
    error: str = ""
    latency_ticks: int = 0
    # True the *second* time a keyed side-effect is requested (exactly-once proof).
    side_effect_deduped: bool = False


@dataclass
class HealthStatus:
    ok: bool
    detail: str = ""


@dataclass
class SafetyDescriptor:
    """What the Safety Gate inspects before allowing a run (FR-TA-05)."""

    kind: str  # "mock" | "http" | "mcp" | "evm"
    endpoint: str  # host:port or command or "mock:crm" — matched against allowlist
    is_probably_production: bool = False
    evm_is_fork: bool | None = None  # None for non-EVM targets


class TargetAdapter(abc.ABC):
    """Abstract base every adapter implements."""

    @abc.abstractmethod
    async def discover(self) -> ToolSet:
        """Tools/resources/prompts the agents can use."""

    @abc.abstractmethod
    async def invoke(self, call: ToolCall, ctx: AgentContext) -> ToolResult:
        """Execute one tool call on behalf of an agent."""

    async def reset(self, seed: int | None = None) -> None:
        """Deterministic reset between waves. Default: no-op (stateless target)."""
        return None

    async def health(self) -> HealthStatus:
        return HealthStatus(ok=True)

    def isolation(self) -> IsolationMode:
        return IsolationMode.SHARED

    @abc.abstractmethod
    def safety_descriptor(self) -> SafetyDescriptor:
        """Describe the target so the Safety Gate can allow/deny the run."""

    async def aclose(self) -> None:
        """Release any connections/subprocesses. Default: no-op."""
        return None
