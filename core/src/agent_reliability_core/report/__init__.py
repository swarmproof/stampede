"""report-renderer — the shared visual vocabulary (ADR-4, FR-OB-04).

A closed set of section shapes (``KpiRow`` / ``Table`` / ``Callout`` / ``Note`` +
a ``Badge``) plus the oxblood ``Theme`` and two renderers (HTML + terminal). A tool
adapts its own domain report into a :class:`Report` and gets the portfolio's look
for free. Rendering needs the ``[render]`` extra (jinja2 + rich); the model + theme
are dependency-free.
"""

from __future__ import annotations

from agent_reliability_core.report.model import (
    Badge,
    Callout,
    Cell,
    Column,
    Kpi,
    KpiRow,
    Note,
    Report,
    Section,
    Table,
    Tone,
)
from agent_reliability_core.report.render import render_html, render_terminal
from agent_reliability_core.report.theme import DEFAULT_THEME, Theme

__all__ = [
    "DEFAULT_THEME",
    "Badge",
    "Callout",
    "Cell",
    "Column",
    "Kpi",
    "KpiRow",
    "Note",
    "Report",
    "Section",
    "Table",
    "Theme",
    "Tone",
    "render_html",
    "render_terminal",
]
