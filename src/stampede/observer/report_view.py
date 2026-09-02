"""Adapter: stampede's domain ``RunReport`` → the shared presentation ``Report``.

The only stampede-aware rendering code. It composes the Agent Readiness Report's
sections from the domain fields; core renders them in the shared theme (ADR-4).
"""

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
    Section,
    Table,
    Tone,
)

from stampede.observer.report import RunReport


def _overall(report: RunReport) -> tuple[float, float]:
    n = len(report.success) or 1
    succ = sum(s.success_rate for s in report.success) / n
    mis = sum(s.misuse_rate for s in report.success) / n
    return succ, mis


def to_report(r: RunReport) -> Report:
    succ, mis = _overall(r)
    viol = r.chaos.get("exactly_once_violations", 0)
    sections: list[Section] = [
        KpiRow(
            [
                Kpi(f"{succ * 100:.0f}%", "task success"),
                Kpi(f"{mis * 100:.0f}%", "misuse"),
                Kpi(f"{r.cost_spread:.1f}×", "cost spread"),
                Kpi(f"${r.total_usd:.4f}", "modeled spend"),
                Kpi(str(viol), "exactly-once violations", Tone.BAD if viol else Tone.NEUTRAL),
            ]
        )
    ]

    if r.misuse_map:
        sections.append(Callout("Where agents called the wrong tool for their goal — your descriptions may be ambiguous."))
        sections.append(
            Table(
                "Misuse map",
                [Column("goal expected"), Column("agents called"), Column("confusion", "right"), Column("n", "right")],
                [
                    [
                        Cell(m.expected_tool),
                        Cell(m.realized_tool),
                        Cell(f"{m.confusion_rate * 100:.0f}%", bar=m.confusion_rate, tone=Tone.ACCENT),
                        Cell(str(m.n_labeled)),
                    ]
                    for m in r.misuse_map
                ],
            )
        )

    sections.append(
        Table(
            "Task success by persona",
            [Column("persona"), Column("agents", "right"), Column("success", "right"), Column("misuse", "right")],
            [
                [Cell(s.persona), Cell(str(s.n)), Cell(f"{s.success_rate * 100:.0f}%"), Cell(f"{s.misuse_rate * 100:.0f}%")]
                for s in r.success
            ],
        )
    )

    sections.append(
        Table(
            "Cost profile",
            [Column("persona"), Column("mean $", "right"), Column("p95 $", "right"), Column("tokens", "right")],
            [
                [Cell(c.persona), Cell(f"${c.usd_mean:.4f}"), Cell(f"${c.usd_p95:.4f}"), Cell(f"{c.tokens_mean:.0f}")]
                for c in r.cost_profile
            ],
        )
    )

    perf = r.performance
    sections.append(
        KpiRow(
            [
                Kpi(str(perf["p50_ticks"]), "p50 ms"),
                Kpi(str(perf["p95_ticks"]), "p95 ms"),
                Kpi(str(perf["p99_ticks"]), "p99 ms"),
                Kpi(str(perf["dropped_connections"]), "dropped"),
                Kpi(str(perf["max_stable_concurrency"]), "peak concurrency"),
            ]
        )
    )

    incident = r.chaos.get("incident")
    if incident:
        sections.append(Note(f"incident replay — {incident.get('id')}: {incident.get('title')}", Tone.ACCENT))
    if r.chaos.get("faults_injected"):
        faults = ", ".join(f"{k}={v}" for k, v in sorted(r.chaos["faults_injected"].items()))
        tone = Tone.GOOD if viol == 0 else Tone.BAD
        tag = "exactly-once holds" if viol == 0 else f"{viol} exactly-once violation(s)"
        sections.append(Note(f"chaos: {faults}  ·  {tag}", tone))

    adv = r.adversarial
    sections.append(
        KpiRow(
            [
                Kpi(str(adv.get("cohort_size", 0)), "adversarial agents"),
                Kpi(str(adv.get("destructive_reached", 0)), "reached destructive tool"),
                Kpi(str(adv.get("denial_of_wallet_flags", 0)), "denial-of-wallet flags"),
            ]
        )
    )

    if r.realism is not None:
        rl = r.realism
        sections.append(
            Note(
                f"realism {rl['score']} "
                f"(sim misuse {rl['simulated']['misuse_rate']:.0%} vs recorded {rl['recorded']['misuse_rate']:.0%})"
            )
        )

    return Report(
        title="Agent Readiness Report",
        subtitle=f"{r.target} · {r.size} agents · seed {r.seed} · run {r.run_id}",
        badge=Badge(r.grade),
        sections=sections,
    )
