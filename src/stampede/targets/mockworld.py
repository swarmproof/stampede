"""MockworldTarget — drive a mockworld mock as a stampede target (FR-TA-03).

`stampede.targets.mock.MockTarget` ships two hand-coded worlds for the dry-run
pipeline. mockworld is the productized version of that idea: a deterministic,
LLM-free library of stateful fake services (payments, crm, exchange, email,
files, + a public registry) exposed as MCP servers, with real business-logic
faults, per-session isolation, and a sandbox for untrusted community mocks.

This adapter runs one mockworld Engine in-process, so
``target: {type: mockworld, world: payments}`` gets the whole library instead of
a bespoke world. Determinism is driven the standard way — the orchestrator calls
``reset(seed)`` and mockworld's state is a pure function of the seed.

Requires ``pip install "stampede[mockworld]"``.
"""

from __future__ import annotations

from typing import Any

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

_JSON_TYPES = {
    "str": "string", "int": "integer", "float": "number",
    "bool": "boolean", "list": "array", "dict": "object",
}
_IDEMPOTENCY_ARG = "idempotency_key"  # mockworld's convention (payments)


class MockworldTarget(TargetAdapter):
    def __init__(self, world: str = "payments", faults: str = "realistic", seed: int = 0) -> None:
        from mockworld import Engine

        # A bare name → a built-in/registry mock; a path or mock:/world: passes through.
        source = world if world.startswith(("mock:", "world:", "/", ".", "~")) else f"mock:{world}"
        self._world = world
        self._faults = faults
        self._engine = Engine.from_source(source, seed=seed, faults=faults)
        # (isolation_key, tool, idempotency_key) already applied → report dedupe.
        self._seen: set[tuple[str, str, str]] = set()

    async def discover(self) -> ToolSet:
        specs: list[ToolSpec] = []
        for tool in self._engine.definition.tools:
            specs.append(
                ToolSpec(
                    name=tool.name,
                    description=self._engine.effective_description(tool).strip(),
                    input_schema=self._input_schema(tool),
                    destructive="delete" in tool.name,
                    idempotency_arg=(_IDEMPOTENCY_ARG if _IDEMPOTENCY_ARG in tool.params else None),
                )
            )
        return ToolSet(tools=specs, resources=[f"mockworld://{self._world}"])

    async def invoke(self, call: ToolCall, ctx: AgentContext) -> ToolResult:
        deduped = False
        key = call.arguments.get(_IDEMPOTENCY_ARG)
        if key is not None:
            sig = (ctx.isolation_key, call.tool, str(key))
            deduped = sig in self._seen  # the second keyed call → side-effect deduped
            self._seen.add(sig)

        result = self._engine.call(
            call.tool, call.arguments,
            session_id=ctx.isolation_key, traceparent=ctx.traceparent,
        )
        latency = int(result.meta.get("latency_ms", 0))
        if result.success:
            data = result.data if isinstance(result.data, dict) else {"result": result.data}
            return ToolResult(
                ok=True, structured=data, content="",
                side_effect_deduped=deduped, latency_ticks=latency,
            )
        return ToolResult(
            ok=False, is_error=True, error=result.err.code,
            content=result.err.message, latency_ticks=latency,
        )

    async def reset(self, seed: int | None = None) -> None:
        self._engine.reset(seed)  # state is a pure function of the seed
        self._seen.clear()

    async def health(self) -> HealthStatus:
        return HealthStatus(ok=True, detail=f"mockworld:{self._world}")

    def isolation(self) -> IsolationMode:
        # mockworld's per-session copy-on-write overlays → each agent gets its own tenant.
        return IsolationMode.PER_AGENT

    def safety_descriptor(self) -> SafetyDescriptor:
        # In-process, sandboxed, nothing leaves the machine → matches the mock:* allowlist.
        return SafetyDescriptor(kind="mock", endpoint=f"mock:{self._world}")

    async def aclose(self) -> None:
        self._engine.close()

    def _input_schema(self, tool: Any) -> dict[str, Any]:
        props: dict[str, Any] = {}
        required: list[str] = []
        for name, spec in tool.params.items():
            prop: dict[str, Any] = {"type": _JSON_TYPES.get(spec.type, "string")}
            if spec.enum:
                prop["enum"] = spec.enum
            props[name] = prop
            if spec.required and spec.default is None:
                required.append(name)
        return {"type": "object", "properties": props, "required": required}
