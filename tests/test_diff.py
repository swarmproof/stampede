"""Statistical run-diffing (FR-OB-06, TEST-PLAN §4.6) — flag signal, not noise."""

from __future__ import annotations

from stampede.config import StampedeConfig
from stampede.observer.diff import diff_reports, two_proportion_test
from stampede.run import run_simulation

# ---- the z-test math ----


def test_two_proportion_test_basics():
    # identical proportions → no difference, p = 1.
    diff, z, p = two_proportion_test(0.5, 100, 0.5, 100)
    assert diff == 0.0 and z == 0.0 and p == 1.0
    # a large, well-powered shift is highly significant.
    diff, z, p = two_proportion_test(0.30, 100, 0.60, 100)
    assert diff == 0.30 and z > 4 and p < 0.001
    # a tiny shift over small samples is not significant.
    _, _, p_small = two_proportion_test(0.42, 25, 0.46, 25)
    assert p_small > 0.05


def _report(grade: str, run_id: str, success: list[dict]) -> dict:
    return {"meta": {"grade": grade, "run_id": run_id, "total_usd": 0.0}, "success": success}


# ---- diff_reports: signal vs noise vs improvement ----


def test_flags_significant_misuse_regression():
    baseline = _report("B", "base", [{"persona": "naive", "n": 60, "success_rate": 0.95, "misuse_rate": 0.25}])
    candidate = _report("D", "cand", [{"persona": "naive", "n": 60, "success_rate": 0.95, "misuse_rate": 0.60}])
    d = diff_reports(baseline, candidate)
    assert d.regressed
    reg = d.regressions[0]
    assert reg.persona == "naive" and reg.metric == "misuse_rate" and reg.delta > 0


def test_reseed_noise_is_not_flagged():
    baseline = _report("B", "base", [{"persona": "naive", "n": 30, "success_rate": 0.97, "misuse_rate": 0.42}])
    candidate = _report("B", "cand", [{"persona": "naive", "n": 30, "success_rate": 0.97, "misuse_rate": 0.46}])
    d = diff_reports(baseline, candidate)
    assert not d.regressed  # small delta over small n → within the noise band


def test_improvement_is_not_a_regression():
    baseline = _report("D", "base", [{"persona": "naive", "n": 60, "success_rate": 0.60, "misuse_rate": 0.55}])
    candidate = _report("A", "cand", [{"persona": "naive", "n": 60, "success_rate": 0.95, "misuse_rate": 0.15}])
    d = diff_reports(baseline, candidate)
    assert not d.regressed  # misuse dropped, success rose — the *right* direction


def test_only_common_personas_are_compared():
    baseline = _report("B", "base", [{"persona": "naive", "n": 40, "success_rate": 0.9, "misuse_rate": 0.3}])
    candidate = _report("B", "cand", [{"persona": "expert", "n": 40, "success_rate": 0.99, "misuse_rate": 0.05}])
    d = diff_reports(baseline, candidate)
    assert d.findings == []  # no shared persona → nothing to compare


# ---- end-to-end: a reseed on a stable target must not false-alarm ----


async def test_reseed_produces_no_regression_end_to_end():
    def cfg(seed: int) -> StampedeConfig:
        return StampedeConfig.from_dict(
            {
                "target": {"type": "mock", "world": "crm"},
                "population": {"size": 200, "mix": {"naive": 0.6, "expert": 0.4}, "models": ["dry-run:heuristic"]},
                "seed": seed,
            }
        )

    a = (await run_simulation(cfg(7), dry_run=True)).report.to_dict()
    b = (await run_simulation(cfg(11), dry_run=True)).report.to_dict()
    d = diff_reports(a, b)
    # Same target + population, different RNG seed → changes stay within the band.
    assert not d.regressed, [(f.persona, f.metric, f.delta, f.p_value) for f in d.regressions]
