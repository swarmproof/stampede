"""The stampede adapter RunReport → the shared presentation Report (ADR-4)."""

from __future__ import annotations

from agent_reliability_core.report import Badge, KpiRow, Table

from stampede.config import StampedeConfig
from stampede.observer.report_view import to_report
from stampede.run import run_simulation


async def _run_report():
    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "crm"},
            "population": {"size": 40, "mix": {"naive": 0.6, "expert": 0.2, "adversarial": 0.2}, "models": ["anthropic:claude-haiku"]},
            "chaos": {"inject": ["tool_timeout"], "kill_agents_at": ["random"], "assert_recovery": True},
            "seed": 42,
        }
    )
    return (await run_simulation(cfg, dry_run=True)).report


async def test_adapter_builds_the_expected_sections():
    view = to_report(await _run_report())
    assert view.title == "Agent Readiness Report"
    assert isinstance(view.badge, Badge) and view.badge.value in {"A", "B", "C", "D", "F"}
    titles = [s.title for s in view.sections if isinstance(s, Table)]
    assert "Task success by persona" in titles
    assert "Cost profile" in titles
    assert "Misuse map" in titles  # crm produces misuse
    # first section is the headline KPI row.
    assert isinstance(view.sections[0], KpiRow)
    assert any(k.label == "task success" for k in view.sections[0].items)


async def test_misuse_map_cells_carry_confusion_bars():
    view = to_report(await _run_report())
    misuse = next(s for s in view.sections if isinstance(s, Table) and s.title == "Misuse map")
    # the confusion column (index 2) has a 0..1 bar on every row.
    assert misuse.rows and all(row[2].bar is not None for row in misuse.rows)
