"""report-renderer tests — standalone, imports only agent_reliability_core.report.

Builds a Report by hand (no stampede) and renders it, proving the primitive is
domain-agnostic."""

from __future__ import annotations

from agent_reliability_core.report import (
    Badge,
    Callout,
    Cell,
    Column,
    Kpi,
    KpiRow,
    Note,
    Report,
    Table,
    Theme,
    Tone,
    render_html,
    render_terminal,
)


def _report() -> Report:
    return Report(
        title="Demo Report",
        subtitle="mock:crm · 40 agents",
        badge=Badge("B"),
        sections=[
            KpiRow([Kpi("97%", "success"), Kpi("31%", "misuse", Tone.WARN)]),
            Callout("Where agents went wrong."),
            Table(
                "Confusion",
                [Column("expected"), Column("called"), Column("rate", "right")],
                [[Cell("archive"), Cell("delete", tone=Tone.BAD), Cell("50%", bar=0.5, tone=Tone.ACCENT)]],
            ),
            Note("exactly-once holds", Tone.GOOD),
        ],
    )


def test_html_has_sections_badge_and_theme():
    html = render_html(_report())
    assert html.lower().startswith("<!doctype html>")
    assert "Demo Report" in html
    assert ">B<" in html  # the badge
    assert "Confusion" in html and "archive" in html
    assert 'class="bar"' in html  # the proportion bar
    assert "#6b1f2a" in html  # the default oxblood accent token


def test_theme_is_overridable():
    html = render_html(_report(), theme=Theme(accent="#0000ff"))
    assert "#0000ff" in html and "#6b1f2a" not in html


def test_terminal_renders_without_error(capsys):
    render_terminal(_report())
    out = capsys.readouterr().out
    assert "Demo Report" in out and "grade" in out
    assert "success" in out and "Confusion" in out
