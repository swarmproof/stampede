"""report-renderer — HTML (Jinja) + terminal (Rich) (FR-OB-04).

The shared renderer for the portfolio. HTML is the screenshotable Agent Readiness
Report (oxblood-editorial); the terminal view gives the same story in-shell with
clear, actionable language (NFR-DX-03) rather than a raw metrics dump.
"""

from __future__ import annotations

from pathlib import Path

from stampede.observer.report import RunReport

_TEMPLATES = Path(__file__).parent / "templates"


def _cols(table, *specs) -> None:
    """Add Rich columns; a spec is a name, or a (name, justify) tuple."""
    for spec in specs:
        name, justify = spec if isinstance(spec, tuple) else (spec, "left")
        table.add_column(name, justify=justify)


def _overall(report: RunReport) -> tuple[float, float]:
    n = len(report.success) or 1
    succ = sum(s.success_rate for s in report.success) / n
    mis = sum(s.misuse_rate for s in report.success) / n
    return succ, mis


def render_html(report: RunReport) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("report.html.j2")
    d = report.to_dict()
    succ, mis = _overall(report)
    return template.render(r=report, m=d["meta"], overall_success=succ, overall_misuse=mis)


def render_terminal(report: RunReport) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    succ, mis = _overall(report)
    d = report.to_dict()

    console.print(
        Panel.fit(
            f"[bold]Agent Readiness Report[/bold]  ·  grade [bold]{report.grade}[/bold]\n"
            f"{d['meta']['target']}  ·  {report.size} agents  ·  seed {report.seed}  ·  "
            f"run {report.run_id}",
            border_style="red",
        )
    )

    kpi = Table.grid(padding=(0, 3))
    kpi.add_row(
        f"[bold]{succ * 100:.0f}%[/bold] task success",
        f"[bold]{mis * 100:.0f}%[/bold] misuse",
        f"[bold]{report.cost_spread:.1f}×[/bold] cost spread",
        f"[bold]${report.total_usd:.4f}[/bold] modeled spend",
    )
    console.print(kpi)

    if report.misuse_map:
        t = Table(title="Misuse map — wrong tool for the goal", title_style="red", header_style="dim")
        _cols(t, "expected", "called", ("confusion", "right"), ("n", "right"))
        for m in report.misuse_map:
            t.add_row(m.expected_tool, m.realized_tool, f"{m.confusion_rate * 100:.0f}%", str(m.n_labeled))
        console.print(t)

    t = Table(title="Task success by persona", title_style="red", header_style="dim")
    _cols(t, "persona", ("n", "right"), ("success", "right"), ("misuse", "right"))
    for s in report.success:
        t.add_row(s.persona, str(s.n), f"{s.success_rate * 100:.0f}%", f"{s.misuse_rate * 100:.0f}%")
    console.print(t)

    t = Table(title="Cost profile", title_style="red", header_style="dim")
    _cols(t, "persona", ("mean $", "right"), ("p95 $", "right"), ("tokens", "right"))
    for c in report.cost_profile:
        t.add_row(c.persona, f"${c.usd_mean:.4f}", f"${c.usd_p95:.4f}", f"{c.tokens_mean:.0f}")
    console.print(t)

    perf = report.performance
    console.print(
        f"[dim]perf[/dim] p50={perf['p50_ticks']}ms  p95={perf['p95_ticks']}ms  "
        f"p99={perf['p99_ticks']}ms  dropped={perf['dropped_connections']}  "
        f"peak={perf['max_stable_concurrency']}"
    )
    if report.chaos.get("faults_injected"):
        viol = report.chaos["exactly_once_violations"]
        tag = "[green]exactly-once holds[/green]" if viol == 0 else f"[red]{viol} violation(s)[/red]"
        console.print(f"[dim]chaos[/dim] faults={report.chaos['faults_injected']}  {tag}")
    if report.realism is not None:
        r = report.realism
        console.print(
            f"[dim]realism[/dim] [bold]{r['score']}[/bold]  "
            f"(sim misuse {r['simulated']['misuse_rate']:.0%} vs recorded {r['recorded']['misuse_rate']:.0%})"
        )
