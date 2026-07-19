"""Statistical run-diffing (⊕ FR-OB-06) — signal, not noise.

Naive snapshot diffing flags every delta as a change, so RNG reseeds read as
regressions and CI trust dies. Instead we treat each per-persona rate as a
*proportion over n agents* (which has a known binomial variance) and run a pooled
**two-proportion z-test**: a metric is only flagged when the shift is both
statistically significant (p < alpha) and larger than a minimum effect size — and
in the *worse* direction. A reseed on a stable target moves rates within the noise
band and is not flagged; a genuinely worse target moves them beyond it and is.

No scipy: the normal CDF is ``0.5·(1 + erf(z/√2))`` from the stdlib.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Metrics that are proportions over the per-persona n (variance is known).
# worse_when_up: does an increase mean the target got *worse*?
_PROPORTION_METRICS = {"misuse_rate": True, "success_rate": False}


def _phi(x: float) -> float:
    """Standard normal CDF via the error function (no scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_proportion_test(p1: float, n1: int, p2: float, n2: int) -> tuple[float, float, float]:
    """Pooled two-proportion z-test. Returns ``(diff, z, p_value)`` where
    ``diff = p2 - p1`` (candidate minus baseline)."""
    diff = p2 - p1
    if n1 <= 0 or n2 <= 0:
        return diff, 0.0, 1.0
    pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2))
    z = (diff / se) if se != 0.0 else (math.copysign(math.inf, diff) if diff else 0.0)
    p_value = 2.0 * (1.0 - _phi(abs(z)))  # two-sided
    return diff, z, p_value


@dataclass
class MetricFinding:
    persona: str
    metric: str
    baseline: float
    candidate: float
    delta: float
    p_value: float
    significant: bool
    regression: bool  # significant AND worse direction AND |delta| >= min_effect

    @property
    def verdict(self) -> str:
        if self.regression:
            return "REGRESSION"
        if self.significant:
            return "improved" if not _worse(self.metric, self.delta) else "shift"
        return "noise"


@dataclass
class DiffReport:
    findings: list[MetricFinding]
    grade_baseline: str
    grade_candidate: str
    baseline_run: str
    candidate_run: str
    total_usd_delta: float
    alpha: float
    min_effect: float

    @property
    def regressions(self) -> list[MetricFinding]:
        return [f for f in self.findings if f.regression]

    @property
    def regressed(self) -> bool:
        return bool(self.regressions)


def _worse(metric: str, delta: float) -> bool:
    worse_when_up = _PROPORTION_METRICS.get(metric, True)
    return delta > 0 if worse_when_up else delta < 0


def diff_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    alpha: float = 0.05,
    min_effect: float = 0.10,
) -> DiffReport:
    """Compare two RunReport dicts (``report.to_dict()`` output)."""
    b_by = {s["persona"]: s for s in baseline.get("success", [])}
    c_by = {s["persona"]: s for s in candidate.get("success", [])}

    findings: list[MetricFinding] = []
    for persona in sorted(set(b_by) & set(c_by)):
        b, c = b_by[persona], c_by[persona]
        n1, n2 = int(b.get("n", 0)), int(c.get("n", 0))
        for metric in _PROPORTION_METRICS:
            p1, p2 = float(b.get(metric, 0.0)), float(c.get(metric, 0.0))
            delta, _z, p_value = two_proportion_test(p1, n1, p2, n2)
            significant = p_value < alpha and abs(delta) >= min_effect
            regression = significant and _worse(metric, delta)
            findings.append(
                MetricFinding(
                    persona=persona,
                    metric=metric,
                    baseline=p1,
                    candidate=p2,
                    delta=delta,
                    p_value=p_value,
                    significant=significant,
                    regression=regression,
                )
            )

    b_meta, c_meta = baseline.get("meta", {}), candidate.get("meta", {})
    return DiffReport(
        findings=findings,
        grade_baseline=b_meta.get("grade", "?"),
        grade_candidate=c_meta.get("grade", "?"),
        baseline_run=b_meta.get("run_id", "baseline"),
        candidate_run=c_meta.get("run_id", "candidate"),
        total_usd_delta=round(c_meta.get("total_usd", 0.0) - b_meta.get("total_usd", 0.0), 6),
        alpha=alpha,
        min_effect=min_effect,
    )
