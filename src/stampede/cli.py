"""The ``stampede`` CLI (FR-CLI-*). ``init`` · ``run`` · ``plan``.

One-command local run is the adoption wedge (NFR-DX-01), so the defaults point at a
safe in-process mock world and the deterministic heuristic brain — ``pip install
stampede && stampede init && stampede run --dry-run`` works with zero keys.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from stampede.config import StampedeConfig
from stampede.observer.renderer import render_html, render_terminal
from stampede.run import STARTER_YAML, plan_cost, run_simulation
from stampede.targets.safety import SafetyViolation

app = typer.Typer(
    add_completion=False,
    help="stampede — the wind tunnel for the agent economy.",
    no_args_is_help=True,
)
console = Console()

_GRADE_RANK = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}


def _load(config_path: str) -> StampedeConfig:
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]no config at {config_path}[/red] — run [bold]stampede init[/bold] first.")
        raise typer.Exit(2)
    return StampedeConfig.load(path)


def _apply_target_override(config: StampedeConfig, target: str) -> None:
    if target.startswith("mock:"):
        config.target.type = "mock"
        config.target.world = target.split(":", 1)[1]
    elif target.startswith(("http://", "https://")):
        config.target.type = "http"
        config.target.url = target
    else:
        # A launch command → an MCP server over stdio (SPEC quickstart form).
        config.target.type = "mcp"
        config.target.transport = "stdio"
        config.target.command = target


@app.command()
def init(
    path: str = typer.Option("stampede.yaml", "--path", "-p", help="where to write the config"),
    force: bool = typer.Option(False, "--force", help="overwrite an existing file"),
) -> None:
    """Write a starter ``stampede.yaml`` (FR-CLI-01)."""
    dest = Path(path)
    if dest.exists() and not force:
        console.print(f"[yellow]{path} already exists[/yellow] — pass --force to overwrite.")
        raise typer.Exit(1)
    dest.write_text(STARTER_YAML)
    console.print(f"[green]wrote {path}[/green] — now run [bold]stampede run --dry-run[/bold].")


@app.command()
def run(
    config: str = typer.Option("stampede.yaml", "--config", "-c"),
    target: str = typer.Option(None, "--target", "-t", help="override target (mock:crm | URL | command)"),
    size: int = typer.Option(None, "--size", "-n", help="override population size"),
    budget: float = typer.Option(None, "--budget", help="hard USD cap for the run"),
    dry_run: bool = typer.Option(False, "--dry-run", help="zero-LLM deterministic run (CI)"),
    live: bool = typer.Option(False, "--live", help="serve the watchable dashboard after the run"),
    out: str = typer.Option(None, "--out", help="HTML report path (overrides config)"),
    json_out: str = typer.Option(None, "--json", help="also write the report as JSON"),
    otlp: str = typer.Option(None, "--otlp", help="export traces to an OTLP/HTTP endpoint"),
    fail_under: str = typer.Option(None, "--fail-under", help="exit nonzero below this grade (A-F)"),
) -> None:
    """Run a swarm against the target and produce the Agent Readiness Report (FR-CLI-02)."""
    # A target on the CLI is enough to run — no stampede.yaml required (SPEC quickstart).
    cfg = StampedeConfig() if (target and not Path(config).exists()) else _load(config)
    if target:
        _apply_target_override(cfg, target)
    if size:
        cfg.population.size = size
        cfg.concurrency.peak = min(cfg.concurrency.peak or size, size)
    if budget is not None:
        cfg.report.budget_usd = budget
    if out:
        cfg.report.out = out

    def emit(result) -> int:
        """Render + persist the report; return the --fail-under exit code."""
        render_terminal(result.report)
        html_path = Path(cfg.report.out)
        html_path.write_text(render_html(result.report))
        console.print(f"\n[green]report →[/green] {html_path}")
        if json_out:
            Path(json_out).write_text(json.dumps(result.report.to_dict(), indent=2, sort_keys=True))
            console.print(f"[green]json   →[/green] {json_out}")
        if otlp:
            from stampede.observer.export import export_otlp

            http_code = export_otlp(result.store.all_spans(), otlp)
            console.print(f"[green]otlp   →[/green] {otlp} (HTTP {http_code})")
        if result.outcome.stopped_early:
            console.print(f"[yellow]run stopped early: {result.outcome.reason}[/yellow]")
        if fail_under:
            want = fail_under.strip().upper()
            if _GRADE_RANK.get(result.report.grade, 0) < _GRADE_RANK.get(want, 0):
                console.print(f"[red]grade {result.report.grade} is below --fail-under {want}[/red]")
                return 1
        return 0

    exit_state = {"code": 0}
    try:
        if live:
            # Run the swarm and the watchable dashboard concurrently; report when
            # the run finishes, then hold the dashboard open until Ctrl-C.
            from stampede.run import serve_live

            def on_report(result) -> None:
                exit_state["code"] = emit(result)

            asyncio.run(serve_live(cfg, dry_run=dry_run, on_report=on_report))
        else:
            result = asyncio.run(run_simulation(cfg, dry_run=dry_run))
            exit_state["code"] = emit(result)
    except SafetyViolation as exc:
        console.print(f"\n[red bold]Safety Gate blocked this run.[/red bold]\n{exc}\n")
        raise typer.Exit(2) from exc

    raise typer.Exit(exit_state["code"])


@app.command()
def plan(
    config: str = typer.Option("stampede.yaml", "--config", "-c"),
    size: int = typer.Option(None, "--size", "-n"),
) -> None:
    """Estimate what a run would cost before spending a cent (FR-CLI-05)."""
    cfg = _load(config)
    if size:
        cfg.population.size = size
    est = plan_cost(cfg)
    console.print(
        f"[bold]stampede plan[/bold] — {est['size']} agents on {', '.join(est['models'])}"
    )
    console.print(f"  estimated spend : [bold]${est['estimated_usd']}[/bold]")
    console.print(f"  budget cap      : ${est['budget_usd']}  "
                  f"({'within budget' if est['within_budget'] else 'OVER BUDGET'})")
    for persona, usd in est["per_persona_usd"].items():
        console.print(f"    {persona:<14} ${usd}")


def main() -> None:  # module entry-point convenience
    app()


if __name__ == "__main__":
    main()
