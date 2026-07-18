"""BrainPool routing + the live LLM path (via a fake provider, no network)."""

from __future__ import annotations

from stampede.goals.schema import Goal, Intent
from stampede.personas.loader import load_pack
from stampede.population.agent import Agent, ModelBinding
from stampede.population.brain import BrainPool, HeuristicBrain, LLMBrain, Observation
from stampede.population.providers import Completion, ToolCallRequest
from stampede.targets.mock import MockTarget


def _agent(model: str, persona: str = "naive") -> Agent:
    p = load_pack("core").get(persona)
    goal = Goal(
        id="g",
        text="archive record rec_1",
        intent=Intent(expected_tool="archive_record"),
        labeled=True,
        args={"record_id": "rec_1"},
    )
    return Agent(id="a-1", index=1, persona=p, binding=ModelBinding.parse(model), goal=goal, seed=42)


async def _crm():
    return await MockTarget("crm").discover()


# ---- routing ----


def test_dry_run_pool_is_always_heuristic():
    pool = BrainPool(dry_run=True)
    assert isinstance(pool.for_agent(_agent("ollama:llama3.1")), HeuristicBrain)
    assert isinstance(pool.for_agent(_agent("anthropic:claude-haiku")), HeuristicBrain)


def test_live_pool_routes_and_mixes_by_provider():
    pool = BrainPool(dry_run=False)
    # dry-run/heuristic bindings stay heuristic even in a live run (model mixing).
    assert isinstance(pool.for_agent(_agent("dry-run:heuristic")), HeuristicBrain)
    # a real provider binding gets an LLMBrain...
    b1 = pool.for_agent(_agent("ollama:llama3.1"))
    assert isinstance(b1, LLMBrain)
    # ...cached per provider name (same provider → same brain instance).
    b2 = pool.for_agent(_agent("ollama:qwen2.5"))
    assert b1 is b2


# ---- the LLM decision path (fake provider) ----


class _FakeProvider:
    def __init__(self, tool: str | None = "archive_record", raise_exc: Exception | None = None):
        self.tool = tool
        self.raise_exc = raise_exc

    async def complete(self, *, system, messages, tools, model, temperature=0.0) -> Completion:
        if self.raise_exc:
            raise self.raise_exc
        calls = [ToolCallRequest(self.tool, {"record_id": "rec_1"})] if self.tool else []
        return Completion(text="chose it", tool_calls=calls, input_tokens=11, output_tokens=4)


async def test_llmbrain_uses_model_tool_choice():
    brain = LLMBrain(_FakeProvider(tool="archive_record"))
    d = await brain.decide(_agent("ollama:llama3.1"), await _crm(), Observation(turn=0))
    assert d.tool == "archive_record"
    assert d.arguments == {"record_id": "rec_1"}
    assert d.input_tokens == 11 and d.output_tokens == 4


async def test_llmbrain_gives_up_when_no_tool_call():
    brain = LLMBrain(_FakeProvider(tool=None))
    d = await brain.decide(_agent("ollama:llama3.1"), await _crm(), Observation(turn=0))
    assert d.tool is None and d.give_up


async def test_llmbrain_survives_provider_error():
    # A downed provider fails THIS agent cleanly (NFR-REL-01), never the run.
    brain = LLMBrain(_FakeProvider(raise_exc=ConnectionError("ollama not reachable")))
    d = await brain.decide(_agent("ollama:llama3.1"), await _crm(), Observation(turn=0))
    assert d.tool is None and d.give_up
    assert "provider error" in d.reasoning
