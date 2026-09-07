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
)


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

