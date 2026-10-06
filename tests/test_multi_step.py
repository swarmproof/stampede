"""Multi-step agents (max_steps > 1): an agent sequences tool calls against a target."""

from __future__ import annotations

from stampede.config import StampedeConfig
from stampede.population.brain import Decision, Observation
from stampede.run import run_simulation
from stampede.targets.base import (
    AgentContext,
    SafetyDescriptor,
    TargetAdapter,
    ToolCall,
    ToolResult,
    ToolSet,
    ToolSpec,
)


class FakeStatefulTarget(TargetAdapter):
    """`use_item` only works after `create_item` — a minimal stateful world so a
    multi-step agent must do create → use. Logs every call for assertions."""

    def __init__(self) -> None:
        self.items: set[str] = set()
        self.log: list[tuple[str, bool]] = []

    async def discover(self) -> ToolSet:
        schema = {"type": "object", "properties": {"item_id": {"type": "string"}}, "required": ["item_id"]}
        return ToolSet(tools=[
            ToolSpec(name="use_item", description="Use an existing item.", input_schema=schema),
            ToolSpec(name="create_item", description="Create an item.", input_schema=schema),
        ])

    async def invoke(self, call: ToolCall, ctx: AgentContext) -> ToolResult:
        iid = str(call.arguments.get("item_id"))
        if call.tool == "create_item":
            self.items.add(iid)
            self.log.append(("create_item", True))
            return ToolResult(ok=True, content=f"created {iid}")
        if call.tool == "use_item":
            ok = iid in self.items
            self.log.append(("use_item", ok))
            return ToolResult(ok=ok, is_error=not ok, content="used" if ok else "", error="" if ok else "no such item")
        return ToolResult(ok=False, is_error=True, error="unknown tool")

    def safety_descriptor(self) -> SafetyDescriptor:
        return SafetyDescriptor(kind="mock", endpoint="mock:fake")


class _ScriptedCreateThenUse:
    """A tiny multi-step brain: try use (fails), create, use again (ok), then done."""

    async def decide(self, agent, toolset, obs: Observation) -> Decision:
        if obs.turn == 0:
            return Decision(tool="use_item", arguments={"item_id": "it_1"}, reasoning="try use first")
        if obs.history and not obs.history[-1].ok and obs.history[-1].tool == "use_item":
            return Decision(tool="create_item", arguments={"item_id": "it_1"}, reasoning="create the missing item")
        if obs.history and obs.history[-1].tool == "create_item":
            return Decision(tool="use_item", arguments={"item_id": "it_1"}, reasoning="now use it")
        return Decision(tool=None, done=True, reasoning="goal achieved")


class _Pool:
    def __init__(self, brain) -> None:
        self.brain = brain

    def for_agent(self, agent):
        return self.brain


def _cfg(max_steps: int) -> StampedeConfig:
    return StampedeConfig.from_dict({
        "target": {"type": "mock", "world": "crm"},  # overridden by the passed target
        "population": {"size": 1, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"], "max_steps": max_steps},
        "concurrency": {"curve": "steady", "peak": 1, "hold": 0},
        "report": {"trace_db": ":memory:", "out": "x.html"},
        "seed": 42,
    })


async def test_agent_sequences_create_then_use():
    target = FakeStatefulTarget()
    result = await run_simulation(
        _cfg(max_steps=4), dry_run=False, target=target, brains=_Pool(_ScriptedCreateThenUse())
    )
    # The engine drove the full sequence against the real target:
    assert target.log == [("use_item", False), ("create_item", True), ("use_item", True)]
    # The item exists and the agent finished successfully.
    assert "it_1" in target.items
    assert result.outcome.agents[0].sm.state.value == "DONE"


async def test_single_step_cannot_recover():
    # With max_steps=1 the same brain gets one decision — use fails and is retried
    # (same tool, per patience); it never gets to create_item, so it can't recover.
    target = FakeStatefulTarget()
    result = await run_simulation(
        _cfg(max_steps=1), dry_run=False, target=target, brains=_Pool(_ScriptedCreateThenUse())
    )
    assert {t[0] for t in target.log} == {"use_item"}  # only ever the one tool
    assert "create_item" not in {t[0] for t in target.log}
    assert "it_1" not in target.items
    assert result.outcome.agents[0].sm.state.value == "FAILED"


async def test_multi_step_dry_run_is_deterministic():
    a = (await run_simulation(_cfg(max_steps=3).model_copy(update={}), dry_run=True)).report.to_dict()
    b = (await run_simulation(_cfg(max_steps=3), dry_run=True)).report.to_dict()
    import json
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
