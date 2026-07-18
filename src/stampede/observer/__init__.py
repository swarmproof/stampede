"""Observer — trace + report + dashboard (FR-OB-*).

Aggregates a run into the **Agent Readiness Report** (the screenshotable
deliverable): task success by persona, the misuse map, concurrency performance,
the cost profile, and chaos/adversarial findings. The report renders to HTML and
the terminal; a live dashboard streams spans while a run is in flight; traces
export to any OTel backend over OTLP.
"""

from __future__ import annotations

from stampede.observer.renderer import render_html, render_terminal
from stampede.observer.report import RunReport, build_report, grade_for_score

__all__ = ["RunReport", "build_report", "grade_for_score", "render_html", "render_terminal"]
