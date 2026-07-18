"""The report renderer — HTML (Jinja) + terminal — must render a real report
without error and surface the headline numbers (validates the template)."""

from __future__ import annotations

from stampede.config import StampedeConfig
from stampede.observer.renderer import render_html, render_terminal
from stampede.run import run_simulation


async def _report():
    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "crm"},
            "population": {"size": 20, "mix": {"naive": 0.7, "expert": 0.3}, "models": ["anthropic:claude-haiku"]},
            "chaos": {"inject": ["tool_timeout"], "kill_agents_at": ["random"], "assert_recovery": True},
            "seed": 3,
        }
    )
    return (await run_simulation(cfg, dry_run=True)).report


async def test_html_report_renders_with_key_sections():
    report = await _report()
    html = render_html(report)
    assert "<!doctype html>" in html.lower()
    assert "Agent Readiness Report" in html
    assert "Misuse map" in html
    assert report.run_id in html
    assert f">{report.grade}<" in html  # the grade badge


async def test_terminal_render_does_not_raise(capsys):
    report = await _report()
    render_terminal(report)
    out = capsys.readouterr().out
    assert "Agent Readiness Report" in out
    assert "%" in out  # some percentage made it to the terminal
