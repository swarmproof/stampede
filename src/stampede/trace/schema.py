"""The trace-format attribute registry + span model (ARCHITECTURE.md §4.1).

trace-format is **a profile of the OpenTelemetry GenAI semantic conventions**, not
a bespoke schema (ADR-1). We keep the standard ``gen_ai.*`` attribute names exactly
as OTel defines them and layer a ``swarmproof.*`` extension namespace for the things
OTel has no concept of: personas, chaos actions, per-span USD cost, the misuse
oracle, recovery verdicts. The constants below are the single authoritative source
of those names — mcp-probe, costbomb and mockworld are bound to them.

IDs are generated **deterministically** from ``(seed, counter)`` (blake2b), never
from wall-clock or ``random`` — that is what makes seeded ``--dry-run`` reports
bit-identical (NFR-REPRO-01).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GenAI:
    """Standard OTel GenAI semantic-convention attribute keys (unchanged names)."""

    OPERATION_NAME = "gen_ai.operation.name"  # "chat" | "execute_tool" | "invoke_agent"
    PROVIDER_NAME = "gen_ai.provider.name"  # "anthropic" | "openai" | "ollama"
    REQUEST_MODEL = "gen_ai.request.model"
    REQUEST_TEMPERATURE = "gen_ai.request.temperature"
    USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
    USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    AGENT_ID = "gen_ai.agent.id"
    AGENT_NAME = "gen_ai.agent.name"
    AGENT_DESCRIPTION = "gen_ai.agent.description"
    TOOL_NAME = "gen_ai.tool.name"
    TOOL_CALL_ID = "gen_ai.tool.call.id"
    TOOL_TYPE = "gen_ai.tool.type"


class Swarmproof:
    """The ``swarmproof.*`` extension namespace — our additions over OTel GenAI."""

    SPAN_SIDE = "swarmproof.span.side"  # "agent" | "target"
    RUN_ID = "swarmproof.run.id"
    RUN_SEED = "swarmproof.run.seed"
    PERSONA_NAME = "swarmproof.persona.name"
    PERSONA_PACK = "swarmproof.persona.pack"
    AGENT_TEMPERAMENT = "swarmproof.agent.temperament"
    GOAL_ID = "swarmproof.goal.id"
    GOAL_INTENT_EXPECTED_TOOL = "swarmproof.goal.intent.expected_tool"  # the misuse oracle
    GOAL_INTENT_LABELED = "swarmproof.goal.intent.labeled"
    DECISION_REASONING = "swarmproof.decision.reasoning"  # powers "why did you call X?"
    MISUSE_DETECTED = "swarmproof.misuse.detected"  # realized tool != expected intent
    CHAOS_ACTION = "swarmproof.chaos.action"  # what chaos did to this span, if anything
    FAULT_KIND = "swarmproof.fault.kind"  # target-side: the semantic fault applied
    COST_USD = "swarmproof.cost.usd"
    RECOVERY_EXACTLY_ONCE = "swarmproof.recovery.exactly_once"
    AGENT_STATE = "swarmproof.agent.state"  # six-state machine label at emit time


class SpanKind(StrEnum):
    """OTel span kinds we use. CLIENT = agent-side call, SERVER = target handler."""

    INTERNAL = "INTERNAL"
    CLIENT = "CLIENT"
    SERVER = "SERVER"


class SpanSide(StrEnum):
    """Which side of the wire emitted the span (``swarmproof.span.side``)."""

    AGENT = "agent"
    TARGET = "target"


# Secret-bearing attribute keys are redacted before store/export (NFR-SEC-02).
# Precise markers only: bare "token" would wrongly redact `gen_ai.usage.*_tokens`
# (which are counts, not secrets), so we match auth-token forms explicitly.
REDACT_KEYS = (
    "api_key",
    "apikey",
    "authorization",
    "secret",
    "password",
    "rpc_url",
    "access_token",
    "refresh_token",
    "bearer",
    "private_key",
)
REDACT_PLACEHOLDER = "«redacted»"


def _hex(seed: int, counter: int, nbytes: int) -> str:
    """Deterministic id: blake2b over ``seed:counter`` → ``nbytes`` of hex."""
    h = hashlib.blake2b(f"{seed}:{counter}".encode(), digest_size=nbytes)
    return h.hexdigest()


def new_trace_id(seed: int, counter: int) -> str:
    """A 16-byte (32 hex char) W3C trace-id, deterministic in (seed, counter)."""
    return _hex(seed, counter, 16)


def new_span_id(seed: int, counter: int) -> str:
    """An 8-byte (16 hex char) W3C span-id, deterministic in (seed, counter)."""
    return _hex(seed ^ 0x5A5A5A5A, counter, 8)


def traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    """Build a W3C ``traceparent`` header value for context propagation.

    Format: ``version-traceid-parentid-flags`` (RFC / W3C Trace Context).
    """
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


@dataclass
class Span:
    """One trace-format span. Maps 1:1 onto an OTel span at export time.

    ``attributes`` uses the exact ``gen_ai.*`` / ``swarmproof.*`` keys from the
    registry above. ``service_name`` is an OTel *resource* attribute (``stampede``
    for agent-side spans, ``mockworld.<mock>`` for target-side); ``run_id`` is a
    *span* attribute, never a resource one (one collector may observe many runs).
    """

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    kind: SpanKind = SpanKind.INTERNAL
    service_name: str = "stampede"
    # Virtual (simulated) start/end ticks — not wall clock. Keeps reports
    # deterministic and lets the SimClock compress hours into minutes.
    start_tick: int = 0
    end_tick: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"  # "OK" | "ERROR"
    status_message: str = ""

    def set(self, key: str, value: Any) -> Span:
        """Set an attribute, redacting anything that looks secret (NFR-SEC-02)."""
        self.attributes[key] = _redact(key, value)
        return self

    @property
    def duration_ticks(self) -> int:
        return max(0, self.end_tick - self.start_tick)


def _redact(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(bad in lowered for bad in REDACT_KEYS):
        return REDACT_PLACEHOLDER
    return value
