"""Agent Ready badge + JSON summary (FR-OB-08)."""

from __future__ import annotations

import pytest

from stampede.config import StampedeConfig
from stampede.observer.badge import shields_endpoint, summary, svg_badge
from stampede.run import run_simulation


async def _report():
    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "crm"},
            "population": {"size": 30, "mix": {"naive": 0.6, "expert": 0.4}, "models": ["dry-run:heuristic"]},
            "seed": 42,
        }
    )
    return (await run_simulation(cfg, dry_run=True)).report


async def test_summary_shape_and_pass_flag():
    report = await _report()
    s = summary(report)
    assert s["tool"] == "stampede"
    assert s["grade"] == report.grade
    assert 0.0 <= s["task_success"] <= 1.0
    assert 0.0 <= s["misuse_rate"] <= 1.0
    assert s["run_id"].startswith("run_seed")
    assert s["agent_ready"] is (report.grade in {"A", "B", "C"})


async def test_shields_endpoint_schema_and_colors():
    report = await _report()
    for grade, color in [("A", "brightgreen"), ("B", "green"), ("C", "yellow"), ("D", "orange"), ("F", "red")]:
        report.grade = grade
        ep = shields_endpoint(report)
        assert ep["schemaVersion"] == 1
        assert ep["label"] == "agent ready"
        assert ep["message"] == grade
        assert ep["color"] == color


async def test_svg_badge_is_valid_and_shows_grade():
    report = await _report()
    report.grade = "A"
    svg = svg_badge(report)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "agent ready" in svg
    assert ">A<" in svg  # the grade text
    assert "#4c1" in svg  # grade-A green


async def test_badge_and_summary_are_deterministic():
    r1, r2 = await _report(), await _report()
    assert svg_badge(r1) == svg_badge(r2)
    assert summary(r1) == summary(r2)


def test_summary_agent_ready_false_below_c():
    pytest.importorskip("stampede")  # trivial guard; keeps this a sync test
    from stampede.observer.report import RunReport

    report = RunReport(
        run_id="run_x", seed=1, target="mock:crm", population_mix={}, models=[], size=1,
        duration_ticks=0, total_usd=0.0, safety_posture="allowlisted", grade="F",
    )
    assert summary(report)["agent_ready"] is False
