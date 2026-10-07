"""Regression guard for #37: one aggregate misuse rate, consistent across every surface."""

from __future__ import annotations

from stampede.config import StampedeConfig
from stampede.observer.badge import summary
from stampede.observer.report_view import _overall
from stampede.run import run_simulation


def _cfg() -> StampedeConfig:
    # A persona gradient where misuse concentrates in the largest group (naive),
    # so the n-weighted rate and the old unweighted mean genuinely differ.
    return StampedeConfig.from_dict({
        "target": {"type": "mock", "world": "crm"},
        "population": {
            "size": 50,
            "mix": {"naive": 0.7, "expert": 0.2, "adversarial": 0.1},
            "models": ["dry-run:heuristic"],
        },
        "report": {"trace_db": ":memory:", "out": "x.html"},
        "seed": 42,
    })


async def test_aggregate_misuse_matches_ground_truth_and_every_surface():
    result = await run_simulation(_cfg(), dry_run=True)
    report = result.report

    # ground truth: misused ÷ labeled over ALL agents (the n-weighted rate)
    labeled = [a for a in result.outcome.agents if a.goal.labeled]
    expected = sum(1 for a in labeled if a.misuse) / len(labeled)
    assert abs(report.misuse_rate - expected) < 1e-9

    # every surface reports the SAME number (terminal view, badge/summary, JSON)
    assert _overall(report)[1] == report.misuse_rate                    # terminal KPI
    assert summary(report)["misuse_rate"] == round(report.misuse_rate, 4)  # badge/CI summary
    assert report.to_dict()["meta"]["misuse_rate"] == round(report.misuse_rate, 4)  # exported JSON


async def test_aggregate_differs_from_the_old_unweighted_mean():
    # The bug was an unweighted average across personas; with an uneven mix + a
    # dominant misusing persona, the correct weighted rate must not equal it.
    report = (await run_simulation(_cfg(), dry_run=True)).report
    unweighted = sum(s.misuse_rate for s in report.success) / len(report.success)
    assert report.misuse_rate != unweighted
