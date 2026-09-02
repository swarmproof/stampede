"""Framework adapters (v0.3) — drive the swarm with the user's own agent."""

from __future__ import annotations

import pytest

from stampede.config import StampedeConfig
from stampede.goals.schema import Goal, Intent
from stampede.population.agent import Agent, ModelBinding
from stampede.population.brain import BrainPool, HeuristicBrain, Observation
from stampede.population.frameworks import (
    FrameworkBrain,
    FrameworkDecision,
    ToolInfo,
    build_framework_brain,
    langgraph_agent_fn,
)
from stampede.run import run_simulation
from stampede.targets.mock import MockTarget


def _agent() -> Agent:
    goal = Goal(id="g", text="archive rec_1", intent=Intent(expected_tool="archive_record"), labeled=True)
    p = __import__("stampede.personas", fromlist=["load_pack"]).load_pack("core").get("naive")
    return Agent(id="a1", index=1, persona=p, binding=ModelBinding.parse("dry-run:h"), goal=goal, seed=42)


async def _crm():
    return await MockTarget("crm").discover()


# ---- FrameworkBrain over an AgentFn ----


async def test_sync_and_async_agent_fns():
    def sync_fn(goal: str, tools: list[ToolInfo]) -> FrameworkDecision:
        return FrameworkDecision(tool="archive_record", arguments={"record_id": "rec_1"}, reasoning="chose archive")

    async def async_fn(goal, tools):
        return FrameworkDecision(tool="delete_record")

    ts = await _crm()
    d1 = await FrameworkBrain(sync_fn).decide(_agent(), ts, Observation(0))
    assert d1.tool == "archive_record" and d1.arguments == {"record_id": "rec_1"}
    d2 = await FrameworkBrain(async_fn).decide(_agent(), ts, Observation(0))
    assert d2.tool == "delete_record"


async def test_no_tool_call_is_give_up():
    brain = FrameworkBrain(lambda g, t: FrameworkDecision(tool=None))
    d = await brain.decide(_agent(), await _crm(), Observation(0))
    assert d.tool is None and d.give_up


async def test_framework_error_fails_the_agent_not_the_run():
    def boom(goal, tools):
        raise RuntimeError("graph exploded")

    d = await FrameworkBrain(boom).decide(_agent(), await _crm(), Observation(0))
    assert d.give_up and "framework error" in d.reasoning


# ---- loading + routing ----


def test_import_ref_and_build_callable(tmp_path, monkeypatch):
    mod = tmp_path / "myagent.py"
    mod.write_text(
        "from stampede.population.frameworks import FrameworkDecision\n"
        "def agent(goal, tools):\n    return FrameworkDecision(tool=tools[0].name)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    brain = build_framework_brain("callable", "myagent:agent")
    assert isinstance(brain, FrameworkBrain)


def test_build_framework_rejects_unknown(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        build_framework_brain("crewai-not-yet", "os:getcwd")


def test_pool_routes_to_framework_only_when_live():
    fb = FrameworkBrain(lambda g, t: FrameworkDecision(tool="x"))
    live = BrainPool(dry_run=False, framework_brain=fb)
    assert live.for_agent(_agent()) is fb
    # dry-run stays deterministic — framework never applies.
    assert isinstance(BrainPool(dry_run=True, framework_brain=fb).for_agent(_agent()), HeuristicBrain)


# ---- end to end: the user's agent drives the whole swarm ----


async def test_framework_brain_drives_a_full_run():
    def always_archive(goal: str, tools: list[ToolInfo]) -> FrameworkDecision:
        return FrameworkDecision(tool="archive_record", arguments={"record_id": "rec_1"}, reasoning="my agent")

    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "crm"},
            "population": {"size": 20, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"]},
            "report": {"trace_db": ":memory:", "out": "x.html"},
            "seed": 42,
        }
    )
    pool = BrainPool(dry_run=False, framework_brain=FrameworkBrain(always_archive))
    result = await run_simulation(cfg, dry_run=False, brains=pool)
    # Every agent did what the user's agent decided.
    assert all(a.realized_tool == "archive_record" for a in result.outcome.agents)
    assert result.report.performance["tool_calls"] >= 20


# ---- LangGraph adapter (guarded) ----


async def test_langgraph_adapter_captures_the_tool_call():
    pytest.importorskip("langchain_core")

    class _FakeGraph:
        def __init__(self, tools):
            self.tools = tools

        async def ainvoke(self, state):
            # Simulate the react agent choosing the first tool.
            self.tools[0].invoke({"record_id": "rec_9"})
            return state

    agent_fn = langgraph_agent_fn(lambda tools: _FakeGraph(tools))
    schema = {"type": "object", "properties": {"record_id": {"type": "string"}}}
    decision = await agent_fn("archive it", [ToolInfo("archive_record", "archive a record", schema)])
    assert decision.tool == "archive_record" and decision.arguments == {"record_id": "rec_9"}
