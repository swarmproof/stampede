"""In-process mock worlds — the safe demo + test surface (TEST-PLAN §5).

MockTarget needs no network and is fully deterministic, so it carries most of the
test pyramid and the flagship demo. Two worlds ship:

* ``crm`` — ``archive_record`` (reversible) vs ``delete_record`` (destructive) with
  intentionally ambiguous descriptions. Naive agents confuse them → the misuse map.
* ``payments`` — ``charge_customer`` keyed by an idempotency arg, so a kill +
  resume that re-charges the same key is *deduped*: the exactly-once proof.

State is bucketed by ``isolation_key`` (default PER_AGENT) so agents don't confound
each other's results (FR-TA-06).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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

# Handler: (tool, arguments, state_bucket) -> ToolResult. Mutates the bucket.
Handler = Callable[[str, dict[str, Any], dict[str, Any]], ToolResult]


@dataclass
class World:
    name: str
    toolset: ToolSet
    handler: Handler


# ---- crm world (the misuse-map fixture) -------------------------------------


def _crm_toolset() -> ToolSet:
    return ToolSet(
        tools=[
            ToolSpec(
                name="archive_record",
                # Ambiguous on purpose: "remove" reads like deletion to a skimmer.
                description="Remove a record from the active list. Archived records are hidden but retained and can be restored later.",
                input_schema={
                    "type": "object",
                    "properties": {"record_id": {"type": "string"}},
                    "required": ["record_id"],
                },
            ),
            ToolSpec(
                name="delete_record",
                description="Delete a record. This is permanent and cannot be undone.",
                input_schema={
                    "type": "object",
                    "properties": {"record_id": {"type": "string"}},
                    "required": ["record_id"],
                },
                destructive=True,
            ),
            ToolSpec(
                name="find_records",
                description="Search records by a query string.",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            ),
        ],
        resources=["crm://records"],
    )


def _crm_handler(tool: str, args: dict[str, Any], state: dict[str, Any]) -> ToolResult:
    records: dict[str, str] = state.setdefault(
        "records", {f"rec_{i}": "active" for i in range(1, 21)}
    )
    if tool == "find_records":
        hits = [rid for rid, st in records.items() if st == "active"][:5]
        return ToolResult(ok=True, content=f"found {len(hits)} records", structured={"ids": hits})
    rid = str(args.get("record_id", "rec_1"))
    if tool == "archive_record":
        records[rid] = "archived"
        return ToolResult(ok=True, content=f"archived {rid}", structured={"state": "archived"})
    if tool == "delete_record":
        records[rid] = "deleted"
        return ToolResult(ok=True, content=f"deleted {rid}", structured={"state": "deleted"})
    return ToolResult(ok=False, is_error=True, error=f"unknown tool {tool!r}")


# ---- payments world (the exactly-once fixture) ------------------------------


def _payments_toolset() -> ToolSet:
    return ToolSet(
        tools=[
            ToolSpec(
                name="charge_customer",
                description="Charge a customer a given amount. Pass an idempotency_key so retries do not double-charge.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "amount_cents": {"type": "integer"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["customer_id", "amount_cents"],
                },
                destructive=True,
                idempotency_arg="idempotency_key",
            ),
            ToolSpec(
                name="list_charges",
                description="List charges made for a customer.",
                input_schema={
                    "type": "object",
                    "properties": {"customer_id": {"type": "string"}},
                },
            ),
        ]
    )


def _payments_handler(tool: str, args: dict[str, Any], state: dict[str, Any]) -> ToolResult:
    charges: dict[str, dict[str, Any]] = state.setdefault("charges", {})
    if tool == "list_charges":
        return ToolResult(ok=True, content=f"{len(charges)} charges", structured={"count": len(charges)})
    if tool == "charge_customer":
        # Key on the idempotency arg if present, else the (customer, amount) tuple.
        key = str(
            args.get("idempotency_key")
            or f"{args.get('customer_id')}:{args.get('amount_cents')}"
        )
        # A broken target (exactly_once disabled) never dedupes → double-charges.
        dedupe = state.get("_dedupe", True)
        if dedupe and key in charges:
            # Second attempt with the same key → dedupe, do NOT charge again.
            return ToolResult(
                ok=True,
                content=f"charge {key} already applied (deduped)",
                structured=charges[key],
                side_effect_deduped=True,
            )
        charge = {"key": key, "customer_id": args.get("customer_id"), "amount_cents": args.get("amount_cents")}
        charges[key] = charge
        return ToolResult(ok=True, content=f"charged {key}", structured=charge)
    return ToolResult(ok=False, is_error=True, error=f"unknown tool {tool!r}")


_WORLDS: dict[str, Callable[[], World]] = {
    "crm": lambda: World("crm", _crm_toolset(), _crm_handler),
    "payments": lambda: World("payments", _payments_toolset(), _payments_handler),
}


def available_worlds() -> list[str]:
    return sorted(_WORLDS)


class MockTarget(TargetAdapter):
    def __init__(self, world: str = "crm", exactly_once: bool = True) -> None:
        if world not in _WORLDS:
            raise ValueError(f"unknown mock world {world!r}; have: {', '.join(available_worlds())}")
        self.world_name = world
        self.exactly_once = exactly_once  # False → a broken, double-firing target
        self._world = _WORLDS[world]()
        # isolation_key -> world state bucket
        self._state: dict[str, dict[str, Any]] = {}

    async def discover(self) -> ToolSet:
        return self._world.toolset

    async def invoke(self, call: ToolCall, ctx: AgentContext) -> ToolResult:
        bucket = self._state.setdefault(ctx.isolation_key, {"_dedupe": self.exactly_once})
        spec = self._world.toolset.get(call.tool)
        if spec is None:
            return ToolResult(
                ok=False, is_error=True, error=f"no such tool {call.tool!r} on world {self.world_name!r}"
            )
        return self._world.handler(call.tool, call.arguments, bucket)

    async def reset(self, seed: int | None = None) -> None:
        self._state.clear()

    async def health(self) -> HealthStatus:
        return HealthStatus(ok=True, detail=f"mock world {self.world_name!r}")

    def isolation(self) -> IsolationMode:
        return IsolationMode.PER_AGENT

    def safety_descriptor(self) -> SafetyDescriptor:
        # mock:* is allowlisted by default — nothing leaves the process.
        return SafetyDescriptor(kind="mock", endpoint=f"mock:{self.world_name}")
