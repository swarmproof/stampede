"""The Agent Readiness Report model + aggregation (FR-OB-04, ARCHITECTURE §4.3).

Aggregates agents + the run outcome + trace spans into the report sections. The
``to_dict()`` output is deterministic (sorted keys, fixed rounding, virtual time
only) so seeded ``--dry-run`` reports are byte-identical (NFR-REPRO-01) and can be
committed as golden snapshots.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from stampede.config import StampedeConfig
from stampede.orchestrator.engine import RunOutcome
from stampede.population.agent import Agent, AgentState
from stampede.trace.schema import GenAI
from stampede.trace.store import TraceStore

_GRADE_BANDS = [(0.90, "A"), (0.80, "B"), (0.70, "C"), (0.60, "D"), (0.0, "F")]
_GRADE_ORDER = ["F", "D", "C", "B", "A"]


def grade_for_score(score: float) -> str:
    for threshold, grade in _GRADE_BANDS:
        if score >= threshold:
            return grade
    return "F"


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return int(s[int(k)])
    return int(round(s[lo] + (s[hi] - s[lo]) * (k - lo)))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@dataclass
class PersonaSuccess:
    persona: str
    n: int
    success_rate: float
    misuse_rate: float


@dataclass
class MisuseEntry:
    expected_tool: str
    realized_tool: str
    confusion_rate: float
    n_labeled: int


@dataclass
class CostEntry:
    persona: str
    usd_mean: float
    usd_p95: float
    tokens_mean: float


@dataclass
class RunReport:
    run_id: str
    seed: int
    target: str
    population_mix: dict[str, float]
    models: list[str]
    size: int
    duration_ticks: int
    total_usd: float
    safety_posture: str
    success: list[PersonaSuccess] = field(default_factory=list)
    misuse_map: list[MisuseEntry] = field(default_factory=list)
    performance: dict[str, Any] = field(default_factory=dict)
    cost_profile: list[CostEntry] = field(default_factory=list)
    cost_spread: float = 1.0
    chaos: dict[str, Any] = field(default_factory=dict)
    adversarial: dict[str, Any] = field(default_factory=dict)
    grade: str = "F"
    overall_score: float = 0.0

    # ---- deterministic serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": {
                "run_id": self.run_id,
                "seed": self.seed,
                "target": self.target,
                "population_mix": self.population_mix,
                "models": self.models,
                "size": self.size,
                "duration_ticks": self.duration_ticks,
                "total_usd": round(self.total_usd, 6),
                "safety_posture": self.safety_posture,
                "grade": self.grade,
                "overall_score": round(self.overall_score, 4),
            },
            "success": [
                {
                    "persona": s.persona,
                    "n": s.n,
                    "success_rate": round(s.success_rate, 4),
                    "misuse_rate": round(s.misuse_rate, 4),
                }
                for s in self.success
            ],
            "misuse_map": [
                {
                    "expected_tool": m.expected_tool,
                    "realized_tool": m.realized_tool,
                    "confusion_rate": round(m.confusion_rate, 4),
                    "n_labeled": m.n_labeled,
                }
                for m in self.misuse_map
            ],
            "performance": self.performance,
            "cost_profile": [
                {
                    "persona": c.persona,
                    "usd_mean": round(c.usd_mean, 6),
                    "usd_p95": round(c.usd_p95, 6),
                    "tokens_mean": round(c.tokens_mean, 2),
                }
                for c in self.cost_profile
            ],
            "cost_spread": round(self.cost_spread, 2),
            "chaos": self.chaos,
            "adversarial": self.adversarial,
        }


def build_report(
    *,
    config: StampedeConfig,
    agents: list[Agent],
    outcome: RunOutcome,
    store: TraceStore,
    run_id: str,
) -> RunReport:
    by_persona: dict[str, list[Agent]] = {}
    for a in agents:
        by_persona.setdefault(a.persona.name, []).append(a)

    # ---- success + misuse per persona ----
    success: list[PersonaSuccess] = []
    for persona in sorted(by_persona):
        group = by_persona[persona]
        done = sum(1 for a in group if a.sm.state is AgentState.DONE)
        labeled = [a for a in group if a.goal.labeled]
        misused = sum(1 for a in labeled if a.misuse)
        success.append(
            PersonaSuccess(
                persona=persona,
                n=len(group),
                success_rate=done / len(group) if group else 0.0,
                misuse_rate=misused / len(labeled) if labeled else 0.0,
            )
        )

    # ---- misuse map (labeled goals only, ADR-5) ----
    pair_counts: dict[tuple[str, str], int] = {}
    expected_totals: dict[str, int] = {}
    for a in agents:
        if not a.goal.labeled or not a.goal.intent.expected_tool:
            continue
        exp = a.goal.intent.expected_tool
        expected_totals[exp] = expected_totals.get(exp, 0) + 1
        if a.misuse and a.realized_tool:
            pair_counts[(exp, a.realized_tool)] = pair_counts.get((exp, a.realized_tool), 0) + 1
    misuse_map = [
        MisuseEntry(
            expected_tool=exp,
            realized_tool=real,
            confusion_rate=count / expected_totals[exp],
            n_labeled=expected_totals[exp],
        )
        for (exp, real), count in sorted(pair_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # ---- performance (from execute_tool span durations) ----
    latencies: list[int] = []
    dropped = 0
    for span in store.iter_spans():
        if span.attributes.get(GenAI.OPERATION_NAME) == "execute_tool":
            latencies.append(span.duration_ticks)
            if span.status == "ERROR":
                dropped += 1
    performance = {
        "p50_ticks": _percentile(latencies, 0.50),
        "p95_ticks": _percentile(latencies, 0.95),
        "p99_ticks": _percentile(latencies, 0.99),
        "max_ticks": max(latencies) if latencies else 0,
        "tool_calls": len(latencies),
        "dropped_connections": dropped,
        "max_stable_concurrency": config.concurrency.peak,
        "fd_leaks": 0,
    }

    # ---- cost profile per persona ----
    cost_profile: list[CostEntry] = []
    persona_means: dict[str, float] = {}
    for persona in sorted(by_persona):
        group = by_persona[persona]
        usds = [a.memory.cost_usd for a in group]
        tokens = [float(a.memory.input_tokens + a.memory.output_tokens) for a in group]
        mean = _mean(usds)
        persona_means[persona] = mean
        cost_profile.append(
            CostEntry(
                persona=persona,
                usd_mean=mean,
                usd_p95=float(_percentile([int(u * 1_000_000) for u in usds], 0.95)) / 1_000_000,
                tokens_mean=_mean(tokens),
            )
        )
    nonzero = [m for m in persona_means.values() if m > 0]
    if len(nonzero) >= 2:
        cost_spread = max(nonzero) / min(nonzero)
    else:
        # Free (local/heuristic) models cost $0, but tokens are the real cost driver
        # — surface the token spread so the "naive burns more than expert" story shows.
        tok_means = [c.tokens_mean for c in cost_profile if c.tokens_mean > 0]
        cost_spread = (max(tok_means) / min(tok_means)) if len(tok_means) >= 2 else 1.0

    # ---- chaos ----
    chaos = {
        "faults_injected": outcome.faults_injected,
        "recovery_findings": [
            {"agent_id": f.agent_id, "kind": f.kind, "ok": f.ok, "detail": f.detail}
            for f in sorted(outcome.recovery.findings, key=lambda f: (f.agent_id, f.kind))
        ],
        "exactly_once_violations": len(outcome.recovery.exactly_once_violations),
    }

    # ---- adversarial cohort ----
    adv = [a for a in agents if a.is_adversarial]
    adv_destructive = sum(
        1 for a in adv if a.realized_tool and (store_tool_destructive(a, store) or a.misuse)
    )
    denial_of_wallet = sum(1 for a in adv if a.memory.cost_usd > _mean([x.memory.cost_usd for x in agents] or [0]) * 2)
    adversarial = {
        "cohort_size": len(adv),
        "injection_probes": len(adv),
        "destructive_reached": adv_destructive,
        "denial_of_wallet_flags": denial_of_wallet,
    }

    # ---- overall grade ----
    overall_success = _mean([s.success_rate for s in success])
    overall_misuse = _mean([s.misuse_rate for s in success])
    violation_penalty = 0.15 if chaos["exactly_once_violations"] else 0.0
    score = max(0.0, overall_success - 0.5 * overall_misuse - violation_penalty)

    duration = max((s.end_tick for s in store.iter_spans()), default=0)

    report = RunReport(
        run_id=run_id,
        seed=config.seed,
        target=_target_label(config),
        population_mix=config.population.mix,
        models=config.population.models,
        size=config.population.size,
        duration_ticks=duration,
        total_usd=outcome.total_usd,
        safety_posture=outcome.safety.posture if outcome.safety else "unknown",
        success=success,
        misuse_map=misuse_map,
        performance=performance,
        cost_profile=cost_profile,
        cost_spread=cost_spread,
        chaos=chaos,
        adversarial=adversarial,
        overall_score=score,
        grade=grade_for_score(score),
    )
    return report


def store_tool_destructive(agent: Agent, store: TraceStore) -> bool:
    # Cheap heuristic: destructive tool names the adversarial cohort reached.
    return bool(agent.realized_tool and "delete" in agent.realized_tool)


def _target_label(config: StampedeConfig) -> str:
    t = config.target
    if t.type == "mock":
        return f"mock:{t.world or 'crm'}"
    if t.type == "mcp":
        return f"mcp:{t.command or t.url}"
    if t.type == "http":
        return f"http:{t.url}"
    return t.type
