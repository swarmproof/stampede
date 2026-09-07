"""The adversarial:economic cohort — costbomb-core embedded in stampede."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# The embed needs costbomb-core (the `economic` extra); skip when it isn't installed
# (CI installs only `[dev]`), so this file never fails a costbomb-less run.
pytest.importorskip("costbomb")

from stampede.adversarial.economic import (
    assign_economic_goals,
    build_economic_section,
    economic_playbook,
    metered_cohort,
)


def _span(name, span_id, trace_id, parent, attrs, kind="INTERNAL"):
    return SimpleNamespace(
        name=name, span_id=span_id, trace_id=trace_id, parent_span_id=parent, kind=kind,
        attributes=attrs, start_tick=0, end_tick=1, status="OK", status_message="",
        service_name="stampede",
    )


class _Store:
    def __init__(self, spans):
        self._spans = spans

    def all_spans(self):
        return self._spans


def _trace_for(agent_id, model):
    session = _span("agent", f"s_{agent_id}", f"t_{agent_id}", None,
                    {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.id": agent_id})
    chat = _span("chat", f"c_{agent_id}", f"t_{agent_id}", f"s_{agent_id}",
                 {"gen_ai.operation.name": "chat", "gen_ai.request.model": model,
                  "gen_ai.provider.name": "anthropic",
                  "gen_ai.usage.input_tokens": 1000, "gen_ai.usage.output_tokens": 100},
                 kind="CLIENT")
    return [session, chat]


def _agent(cost: float, adversarial: bool, name: str, goal: str, aid: str):
    return SimpleNamespace(
        is_adversarial=adversarial,
        memory=SimpleNamespace(cost_usd=cost),
        persona=SimpleNamespace(name=name),
        goal=SimpleNamespace(text=goal),
        id=aid,
    )


def test_playbook_comes_from_costbomb_attack_library() -> None:
    pb = economic_playbook(5)
    assert 1 <= len(pb) <= 5
    assert all(isinstance(x, str) and x for x in pb)


def test_economic_section_reports_amplification() -> None:
    agents = [
        _agent(0.01, False, "expert", "look up a record", "a0"),
        _agent(0.01, False, "naive", "read the list", "a1"),
        _agent(1.00, True, "economic", "retry until valid; re-verify every step", "a2"),
    ]
    base = {"cohort_size": 1, "denial_of_wallet_flags": 0}
    out = build_economic_section(agents, base)

    assert "economic" in out
    eco = out["economic"]
    assert eco["amplification_factor"] > 50  # $1.00 worst vs ~$0.01 baseline
    assert out["denial_of_wallet_flags"] >= 1  # bumped by the merge
    assert eco["findings"][0]["persona"] == "economic"  # worst offender ranked first
    assert eco["attack_classes"] and eco["playbook"]  # costbomb library surfaced


def test_passthrough_when_no_adversarial_cohort() -> None:
    agents = [_agent(0.01, False, "expert", "q", "a0")]
    base = {"cohort_size": 0, "denial_of_wallet_flags": 0}
    assert build_economic_section(agents, base) == base


def test_assign_economic_goals_targets_only_adversarial() -> None:
    playbook = set(economic_playbook(count=10))
    benign = _agent(0.01, False, "expert", "look up a record", "a0")
    adv = _agent(0.01, True, "economic", "original goal", "a1")

    n = assign_economic_goals([benign, adv], seed=1)

    assert n == 1
    assert adv.goal.text in playbook  # adversarial agent now pursues a cost-explosion seed
    assert benign.goal.text == "look up a record"  # benign untouched


def test_metered_cohort_reruns_costbomb_meter_on_real_traces() -> None:
    adv = _agent(0.004, True, "economic", "retry until valid", "a1")
    store = _Store(_trace_for("a1", "claude-opus-4-8"))

    m = metered_cohort([adv], store)

    assert "a1" in m
    # costbomb's sum-over-sources meter on the real spans: 1000*3e-6 + 100*1.5e-5
    assert m["a1"]["model_usd"] == pytest.approx(0.0045)
    assert m["a1"]["blast_radius_usd"] == pytest.approx(m["a1"]["total_usd"])


def test_metered_cohort_skips_unpriceable_models() -> None:
    adv = _agent(0.0, True, "economic", "x", "a1")
    store = _Store(_trace_for("a1", "heuristic"))  # dry-run model not in the price table
    assert metered_cohort([adv], store) == {}  # skipped, additive


def test_build_economic_section_attaches_metered_breakdown() -> None:
    benign = _agent(0.001, False, "expert", "read", "a0")
    adv = _agent(0.004, True, "economic", "retry until valid", "a1")
    store = _Store(_trace_for("a1", "claude-opus-4-8"))
    out = build_economic_section([benign, adv], {"denial_of_wallet_flags": 0}, store)
    top = out["economic"]["findings"][0]
    assert "metered" in top and top["metered"]["model_usd"] == pytest.approx(0.0045)

