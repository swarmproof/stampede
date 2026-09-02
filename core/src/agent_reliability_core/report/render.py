"""Renderers over the presentation model — HTML (Jinja) + terminal (Rich).

Both iterate ``report.sections`` generically, so any tool that adapts its domain
report into :mod:`agent_reliability_core.report.model` gets the same oxblood look.
Needs the ``[render]`` extra (jinja2 + rich)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_reliability_core.report.model import Callout, KpiRow, Note, Report, Table, Tone
from agent_reliability_core.report.theme import DEFAULT_THEME, Theme

_TEMPLATES = Path(__file__).parent / "templates"


def render_html(report: Report, theme: Theme = DEFAULT_THEME) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("report.html.j2")
    # `tone(...)` resolves a Tone to a hex for inline styles.
    return template.render(report=report, t=theme, tone=theme.hex_for)


def _bar(fraction: float, width: int = 8) -> str:
    filled = max(0, min(width, round(fraction * width)))
    return "█" * filled + "░" * (width - filled)


def render_terminal(report: Report, console: Any = None, theme: Theme = DEFAULT_THEME) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table as RichTable

    console = console or Console()

    head = f"[bold]{report.title}[/bold]"
    if report.badge:
        head += f"  ·  grade [bold]{report.badge.value}[/bold]"
    if report.subtitle:
        head += f"\n{report.subtitle}"
    console.print(Panel.fit(head, border_style=theme.rich_for(Tone.ACCENT)))

    for section in report.sections:
        if isinstance(section, KpiRow):
            grid = RichTable.grid(padding=(0, 3))
            grid.add_row(
                *[
                    f"[{theme.rich_for(k.tone)}][bold]{k.value}[/bold][/{theme.rich_for(k.tone)}] {k.label}"
                    for k in section.items
                ]
            )
            console.print(grid)
        elif isinstance(section, Callout):
            console.print(section.text)
        elif isinstance(section, Note):
            style = theme.rich_for(section.tone)
            console.print(f"[{style}]{section.text}[/{style}]" if style != "default" else section.text)
        elif isinstance(section, Table):
            t = RichTable(title=section.title or None, title_style=theme.rich_for(Tone.ACCENT), header_style="dim")
            for col in section.columns:
                t.add_column(col.name, justify=col.align)
            for row in section.rows:
                cells = []
                for cell in row:
                    text = f"{_bar(cell.bar)} {cell.text}" if cell.bar is not None else cell.text
                    style = theme.rich_for(cell.tone)
                    cells.append(f"[{style}]{text}[/{style}]" if style != "default" else text)
                t.add_row(*cells)
            console.print(t)
