"""Agent Ready badge + machine-readable summary (FR-OB-08).

Three renderings of a run's headline result, so a team can put "did the swarm pass?"
in front of people and machines:

* :func:`summary` — a compact JSON dict for CI to gate on / diff.
* :func:`shields_endpoint` — the shields.io *endpoint* schema, so a README can embed
  ``https://img.shields.io/endpoint?url=<raw summary url>``.
* :func:`svg_badge` — a self-contained flat SVG (no shields.io dependency) to commit
  or serve directly.

All three are deterministic (the report itself is, per NFR-REPRO-01).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stampede.observer.report import RunReport

# Grade → (shields color name, SVG hex). Matches shields.io's flat palette.
_GRADE_COLOR = {
    "A": ("brightgreen", "#4c1"),
    "B": ("green", "#97ca00"),
    "C": ("yellow", "#dfb317"),
    "D": ("orange", "#fe7d37"),
    "F": ("red", "#e05d44"),
}


def _overall(report: RunReport) -> tuple[float, float]:
    n = len(report.success) or 1
    success = sum(s.success_rate for s in report.success) / n
    misuse = sum(s.misuse_rate for s in report.success) / n
    return success, misuse


def summary(report: RunReport) -> dict[str, Any]:
    """A machine-readable one-object summary for CI/READMEs."""
    success, misuse = _overall(report)
    return {
        "tool": "stampede",
        "run_id": report.run_id,
        "target": report.target,
        "size": report.size,
        "grade": report.grade,
        "overall_score": round(report.overall_score, 4),
        "task_success": round(success, 4),
        "misuse_rate": round(misuse, 4),
        "cost_spread": report.cost_spread,
        "total_usd": round(report.total_usd, 6),
        "exactly_once_violations": report.chaos.get("exactly_once_violations", 0),
        "agent_ready": report.grade in {"A", "B", "C"},  # C is the default pass bar
    }


def shields_endpoint(report: RunReport, label: str = "agent ready") -> dict[str, Any]:
    """shields.io endpoint schema: embed via img.shields.io/endpoint?url=…"""
    color, _hex = _GRADE_COLOR.get(report.grade, ("lightgrey", "#9f9f9f"))
    return {"schemaVersion": 1, "label": label, "message": report.grade, "color": color}


def _text_width(text: str) -> int:
    # Approximate Verdana-11 advance width; good enough for a tidy flat badge.
    return int(len(text) * 6.5) + 10


def svg_badge(report: RunReport, label: str = "agent ready") -> str:
    """A self-contained flat SVG badge — no external service required."""
    _color, hexc = _GRADE_COLOR.get(report.grade, ("lightgrey", "#9f9f9f"))
    message = report.grade
    lw, mw = _text_width(label), _text_width(message)
    total = lw + mw
    # Text anchors sit at the horizontal centre of each segment (×10 for the scale).
    lx = lw * 10 // 2
    mx = (lw + mw // 2) * 10
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{total}" height="20" role="img" aria-label="{label}: {message}">'
        f"<title>{label}: {message}</title>"
        f'<linearGradient id="s" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)">'
        f'<rect width="{lw}" height="20" fill="#555"/>'
        f'<rect x="{lw}" width="{mw}" height="20" fill="{hexc}"/>'
        f'<rect width="{total}" height="20" fill="url(#s)"/></g>'
        f'<g fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        f'text-rendering="geometricPrecision" font-size="110">'
        f'<text x="{lx}" y="150" transform="scale(.1)" fill="#010101" fill-opacity=".3" '
        f'textLength="{(lw - 10) * 10}">{label}</text>'
        f'<text x="{lx}" y="140" transform="scale(.1)" textLength="{(lw - 10) * 10}">{label}</text>'
        f'<text x="{mx}" y="150" transform="scale(.1)" fill="#010101" fill-opacity=".3">{message}</text>'
        f'<text x="{mx}" y="140" transform="scale(.1)">{message}</text>'
        f"</g></svg>"
    )
