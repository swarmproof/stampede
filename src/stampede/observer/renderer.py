"""report-renderer — thin adapter over the shared renderer (FR-OB-04, ADR-4).

The rendering vocabulary + theme now live in ``agent_reliability_core.report``.
stampede maps its domain :class:`RunReport` to the shared presentation model
(:mod:`stampede.observer.report_view`) and delegates. Public signatures are
unchanged, so the CLI and tests are unaffected.
"""

from __future__ import annotations

from agent_reliability_core.report import render_html as _core_render_html
from agent_reliability_core.report import render_terminal as _core_render_terminal

from stampede.observer.report import RunReport
from stampede.observer.report_view import to_report


def render_html(report: RunReport) -> str:
    return _core_render_html(to_report(report))


def render_terminal(report: RunReport, console: object = None) -> None:
    _core_render_terminal(to_report(report), console)
