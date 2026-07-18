"""End-to-end acceptance scenarios (TEST-PLAN §4). Real (small, seeded) swarms
against local mock targets, asserting the report — all zero-LLM/deterministic."""

from __future__ import annotations

import json
import time

from stampede.config import StampedeConfig
from stampede.run import run_simulation
from stampede.targets.mock import MockTarget


def _cfg(**over) -> StampedeConfig:
    base = {
        "target": {"type": "mock", "world": "crm"},
        "population": {
            "size": 50,
            "mix": {"naive": 0.6, "expert": 0.3, "adversarial": 0.1},
            "models": ["dry-run:heuristic"],
        },
        "concurrency": {"curve": "ramp", "peak": 50, "hold": 30},
        "seed": 42,
    }
    base.update(over)
    return StampedeConfig.from_dict(base)


# ---- 4.1 flagship: swarm vs mock crm → misuse map ----


async def test_flagship_misuse_map_is_nonzero_with_persona_gradient():
    result = await run_simulation(_cfg(), dry_run=True)
    r = result.report
    assert r.misuse_map, "expected a non-empty misuse map"
    # archive↔delete confusion is present.
    pairs = {(m.expected_tool, m.realized_tool) for m in r.misuse_map}
    assert ("archive_record", "delete_record") in pairs or ("delete_record", "archive_record") in pairs
    # expert misuses less than naive.
    by = {s.persona: s for s in r.success}
    assert by["expert"].misuse_rate < by["naive"].misuse_rate


# ---- 4.3 deterministic CI smoke ----


async def test_dry_run_reports_are_byte_identical():
    a = (await run_simulation(_cfg(seed=7), dry_run=True)).report.to_dict()
    b = (await run_simulation(_cfg(seed=7), dry_run=True)).report.to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


async def test_dry_run_50_agents_under_30s():
    t0 = time.perf_counter()
    await run_simulation(_cfg(), dry_run=True)
    assert time.perf_counter() - t0 < 30.0  # NFR-PERF-03


async def test_harness_scales_to_200_agents():
    cfg = _cfg(population={"size": 200, "mix": {"naive": 0.5, "expert": 0.5}, "models": ["dry-run:heuristic"]})
    t0 = time.perf_counter()
    result = await run_simulation(cfg, dry_run=True)
    assert len(result.report.success) == 2
    assert sum(s.n for s in result.report.success) == 200  # NFR-PERF-01
    assert time.perf_counter() - t0 < 30.0


# ---- 4.4 safety gate ----


async def test_safety_gate_blocks_production():
    from stampede.targets.safety import SafetyViolation

    cfg = _cfg(target={"type": "http", "url": "https://api.acme-prod.com"})
    try:
        await run_simulation(cfg, dry_run=True)
        raise AssertionError("expected the Safety Gate to block this run")
    except SafetyViolation:
        pass


# ---- 4.2 chaos + recovery + exactly-once (incl. the negative test) ----


async def test_exactly_once_holds_on_good_target():
    cfg = _cfg(
        target={"type": "mock", "world": "payments"},
        chaos={"kill_agents_at": ["random"], "inject": ["tool_timeout", "rate_limit"], "assert_recovery": True},
    )
    result = await run_simulation(cfg, dry_run=True, target=MockTarget("payments", exactly_once=True))
    assert result.report.chaos["exactly_once_violations"] == 0


async def test_exactly_once_violation_detected_on_broken_target():
    # Negative test: a target that never dedupes → double-charges after a kill.
    cfg = _cfg(
        target={"type": "mock", "world": "payments"},
        chaos={"kill_agents_at": ["random"], "inject": ["tool_timeout"], "assert_recovery": True},
    )
    result = await run_simulation(cfg, dry_run=True, target=MockTarget("payments", exactly_once=False))
    assert result.report.chaos["exactly_once_violations"] > 0


# ---- 4.5 cost cap ----


async def test_budget_hard_stop_produces_partial_report():
    cfg = _cfg(
        population={"size": 40, "mix": {"naive": 1.0}, "models": ["anthropic:claude-opus"]},
        report={"budget_usd": 0.001, "out": "x.html", "trace_db": ":memory:"},
    )
    result = await run_simulation(cfg, dry_run=True)
    # Modeled spend stops near the cap and a valid report still renders.
    assert result.outcome.stopped_early
    assert result.report.grade in {"A", "B", "C", "D", "F"}


# ---- trace-format shape ----


async def test_spans_carry_genai_and_swarmproof_attrs():
    result = await run_simulation(_cfg(population={"size": 5, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"]}), dry_run=True)
    spans = result.store.all_spans()
    tool_spans = [s for s in spans if s.attributes.get("gen_ai.operation.name") == "execute_tool"]
    assert tool_spans
    s = tool_spans[0]
    assert "gen_ai.tool.name" in s.attributes
    assert s.attributes.get("swarmproof.run.id", "").startswith("run_seed")
    # OTLP/JSON serialization round-trips.
    from stampede.observer.export import to_otlp_json

    doc = to_otlp_json(spans)
    assert doc["resourceSpans"][0]["scopeSpans"][0]["spans"]
