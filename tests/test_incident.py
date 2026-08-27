"""Incident replay as a chaos source (FR-CH-05)."""

from __future__ import annotations

import random

import pytest

from stampede.chaos.incident import Incident
from stampede.chaos.injector import ChaosPolicy, FaultKind
from stampede.config import ChaosConfig, StampedeConfig
from stampede.run import run_simulation

_INCIDENT_YAML = """\
apiVersion: swarmproof.dev/incident/v1
kind: Incident
metadata: {id: INC-1, title: "test outage", date: 2026-06-01}
faults:
  - {kind: rate_limit, blast_radius: 0.5}
  - {kind: tool_timeout, blast_radius: 0.3}
  - {kind: agent_kill, blast_radius: 0.2, at_step: 1}
"""


def _write_incident(tmp_path) -> str:
    p = tmp_path / "inc.yaml"
    p.write_text(_INCIDENT_YAML)
    return str(p)


# ---- loading ----


def test_incident_loads_and_validates(tmp_path):
    inc = Incident.load(_write_incident(tmp_path))
    assert inc.id == "INC-1"
    assert {f.kind for f in inc.faults} == {"rate_limit", "tool_timeout", "agent_kill"}
    kill = next(f for f in inc.faults if f.kind == "agent_kill")
    assert kill.at_step == 1 and kill.blast_radius == 0.2


def test_unknown_fault_kind_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "apiVersion: swarmproof.dev/incident/v1\nfaults:\n  - {kind: nuke, blast_radius: 1.0}\n"
    )
    with pytest.raises(ValueError):
        Incident.load(bad)


# ---- policy replay ----


def test_apply_incident_rewrites_the_policy(tmp_path):
    policy = ChaosPolicy(ChaosConfig(inject=["latency"], rate=0.15))
    policy.apply_incident(Incident.load(_write_incident(tmp_path)))
    # Only the incident's invoke-faults are enabled now.
    assert set(policy.enabled) == {FaultKind.RATE_LIMIT, FaultKind.TIMEOUT}
    assert policy.rate == pytest.approx(0.8)  # 0.5 + 0.3
    assert policy.kill_fraction == 0.2 and policy.kill_at_step == 1
    assert policy.incident == {"id": "INC-1", "title": "test outage"}


def test_incident_fault_mix_matches_blast_radius(tmp_path):
    policy = ChaosPolicy(ChaosConfig()).apply_incident(Incident.load(_write_incident(tmp_path)))
    rng = random.Random(0)
    counts = {FaultKind.RATE_LIMIT: 0, FaultKind.TIMEOUT: 0, FaultKind.PASS: 0}
    for _ in range(4000):
        counts[policy.before_invoke(rng).kind] += 1
    faults = counts[FaultKind.RATE_LIMIT] + counts[FaultKind.TIMEOUT]
    # ~80% of invokes faulted (0.5 + 0.3), and rate_limit ~5:3 more than timeout.
    assert 0.74 < faults / 4000 < 0.86
    assert counts[FaultKind.RATE_LIMIT] > counts[FaultKind.TIMEOUT]


def test_kill_pinned_to_incident_step(tmp_path):
    policy = ChaosPolicy(ChaosConfig()).apply_incident(Incident.load(_write_incident(tmp_path)))
    # For agents that get killed, the step is pinned to at_step (1), capped by max_steps.
    steps = [policy.kill_step_for(random.Random(s), max_steps=6) for s in range(50)]
    killed = [s for s in steps if s is not None]
    assert killed and all(s == 1 for s in killed)


# ---- end to end ----


async def test_run_replays_incident_and_reports_it(tmp_path):
    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "payments"},
            "population": {"size": 40, "mix": {"naive": 0.6, "expert": 0.4}, "models": ["dry-run:heuristic"]},
            "chaos": {"incident": _write_incident(tmp_path), "assert_recovery": True},
            "seed": 42,
        }
    )
    report = (await run_simulation(cfg, dry_run=True)).report
    d = report.to_dict()
    assert d["chaos"]["incident"] == {"id": "INC-1", "title": "test outage"}
    # The incident's faults actually fired.
    faults = d["chaos"]["faults_injected"]
    assert faults.get("rate_limit", 0) > 0
    assert faults.get("agent_kill", 0) > 0


async def test_incident_run_is_deterministic(tmp_path):
    inc = _write_incident(tmp_path)

    def cfg() -> StampedeConfig:
        return StampedeConfig.from_dict(
            {
                "target": {"type": "mock", "world": "crm"},
                "population": {"size": 40, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"]},
                "chaos": {"incident": inc, "assert_recovery": True},
                "seed": 7,
            }
        )

    a = (await run_simulation(cfg(), dry_run=True)).report.to_dict()
    b = (await run_simulation(cfg(), dry_run=True)).report.to_dict()
    assert a == b
