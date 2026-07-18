"""Unit scope for goals, brain/misuse, chaos, safety, cost (TEST-PLAN §2)."""

from __future__ import annotations

import random

import pytest

from stampede.chaos.injector import ChaosPolicy, FaultKind
from stampede.config import ChaosConfig, SafetyConfig
from stampede.goals.synth import synthesize
from stampede.population.agent import Agent, ModelBinding
from stampede.population.brain import HeuristicBrain, Observation, _confusable
from stampede.population.providers import cost_usd, price_for
from stampede.targets.base import SafetyDescriptor
from stampede.targets.mock import MockTarget
from stampede.targets.safety import SafetyGate, SafetyViolation


async def _crm_toolset():
    return await MockTarget("crm").discover()


# ---- goal synthesis ----


async def test_template_goals_are_labeled_with_intent():
    toolset = await _crm_toolset()
    goals = synthesize(toolset, extra=[], mode="template", count=10, seed=1)
    assert len(goals) >= 10
    labeled = [g for g in goals if g.labeled]
    assert labeled and all(g.intent.expected_tool for g in labeled)
    # archive + delete intents both appear (drives the misuse map)
    intents = {g.intent.expected_tool for g in goals}
    assert {"archive_record", "delete_record"} <= intents


async def test_extra_goal_unlabeled_unless_names_a_tool():
    toolset = await _crm_toolset()
    goals = synthesize(toolset, extra=["do something vague"], mode="template", count=6, seed=1)
    extra = next(g for g in goals if g.id == "g_extra_0")
    assert extra.labeled is False  # excluded from the misuse denominator (ADR-5)


async def test_template_goals_are_deterministic():
    toolset = await _crm_toolset()
    a = synthesize(toolset, [], "template", 12, 5)
    b = synthesize(toolset, [], "template", 12, 5)
    assert [(g.id, g.text) for g in a] == [(g.id, g.text) for g in b]


# ---- brain / misuse ----


async def test_confusable_maps_archive_to_delete():
    toolset = await _crm_toolset()
    wrong = _confusable("archive_record", toolset)
    assert wrong is not None and wrong.name == "delete_record"
    wrong2 = _confusable("delete_record", toolset)
    assert wrong2 is not None and wrong2.name == "archive_record"


def _agent(persona_name: str, expected_tool: str) -> Agent:
    from stampede.goals.schema import Goal, Intent
    from stampede.personas.loader import load_pack

    persona = load_pack("core").get(persona_name)
    goal = Goal(
        id="g",
        text="archive it",
        intent=Intent(expected_tool=expected_tool),
        labeled=True,
        args={"record_id": "rec_1"},
    )
    return Agent(id="agent-0001", index=1, persona=persona, binding=ModelBinding.parse("dry-run:h"), goal=goal, seed=42)


async def test_expert_misreads_far_less_than_naive_over_many_agents():
    toolset = await _crm_toolset()
    brain = HeuristicBrain()

    async def misuse_rate(persona: str) -> float:
        hits = 0
        n = 200
        for i in range(n):
            a = _agent(persona, "archive_record")
            a.index = i  # vary the seed stream per agent
            d = await brain.decide(a, toolset, Observation(turn=0))
            if d.tool != "archive_record":
                hits += 1
        return hits / n

    assert await misuse_rate("expert") < await misuse_rate("naive")


# ---- chaos ----


def test_chaos_pass_when_no_faults_configured():
    policy = ChaosPolicy(ChaosConfig(inject=[]))
    action = policy.before_invoke(random.Random(1))
    assert action.kind is FaultKind.PASS


def test_chaos_fault_probability_roughly_honors_rate():
    policy = ChaosPolicy(ChaosConfig(inject=["tool_timeout", "rate_limit"], rate=0.3))
    rng = random.Random(0)
    faults = sum(1 for _ in range(2000) if policy.before_invoke(rng).is_fault)
    assert 0.25 < faults / 2000 < 0.35  # ~30%


def test_kill_plan_is_seeded():
    policy = ChaosPolicy(ChaosConfig(kill_agents_at=["random"]))
    a = policy.kill_step_for(random.Random(3), 5)
    b = policy.kill_step_for(random.Random(3), 5)
    assert a == b


# ---- safety gate ----


def test_safety_allows_localhost_and_mock():
    gate = SafetyGate(SafetyConfig())
    assert gate.check(SafetyDescriptor(kind="mock", endpoint="mock:crm")).allowed
    assert gate.check(SafetyDescriptor(kind="http", endpoint="localhost:8000")).allowed


def test_safety_blocks_offlist_without_ack():
    gate = SafetyGate(SafetyConfig())
    with pytest.raises(SafetyViolation):
        gate.check(SafetyDescriptor(kind="http", endpoint="api.acme-prod.com"))


def test_safety_ack_permits_offlist():
    gate = SafetyGate(SafetyConfig(acknowledge_non_production=True))
    posture = gate.check(SafetyDescriptor(kind="http", endpoint="api.acme-prod.com"))
    assert posture.allowed and posture.posture == "acknowledged-non-production"


def test_safety_refuses_non_fork_evm():
    gate = SafetyGate(SafetyConfig())
    with pytest.raises(SafetyViolation):
        gate.check(SafetyDescriptor(kind="evm", endpoint="mainnet", evm_is_fork=False))


# ---- cost ----


def test_price_table_and_cost_math():
    assert price_for("ollama", "llama3") == (0.0, 0.0)
    assert price_for("dry-run", "heuristic") == (0.0, 0.0)
    # 1M input + 1M output at haiku prices
    c = cost_usd("anthropic", "claude-haiku", 1_000_000, 1_000_000)
    assert c == pytest.approx(0.80 + 4.00)
