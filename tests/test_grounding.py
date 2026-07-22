"""Persona grounding / realism (FR-PF-06, FR-OB-07, TEST-PLAN §4.8)."""

from __future__ import annotations

from stampede.config import StampedeConfig
from stampede.personas.loader import load_pack, write_pack
from stampede.population.grounding import (
    RecordedTraffic,
    fit_misread_rate,
    fit_persona,
    realism_score,
)
from stampede.run import run_simulation

# ---- the fit math ----


def test_fit_misread_inverts_the_decision_model():
    # With adherence a, sim misuse = 1 - (1-misread)(0.5+0.5a); fit recovers misread.
    for adherence in (0.6, 0.95):
        target = 0.35
        mr = fit_misread_rate(target, adherence)
        sim = 1 - (1 - mr) * (0.5 + 0.5 * adherence)
        # Either the fit hits the target, or it clamps at 0 (target below the floor).
        assert abs(sim - target) < 1e-9 or mr == 0.0
    assert 0.0 <= fit_misread_rate(0.9, 0.6) <= 1.0  # always clamped


def test_realism_score_rewards_closeness():
    rec = RecordedTraffic(misuse_rate=0.30, give_up_rate=0.0, avg_tokens=500)
    near = RecordedTraffic(misuse_rate=0.31, give_up_rate=0.0, avg_tokens=505)
    far = RecordedTraffic(misuse_rate=0.80, give_up_rate=0.3, avg_tokens=50)
    assert realism_score(near, rec) > realism_score(far, rec)
    assert realism_score(rec, rec) == 1.0


# ---- RecordedTraffic sources ----


def test_recorded_from_json_roundtrip(tmp_path):
    rec = RecordedTraffic(misuse_rate=0.4, give_up_rate=0.1, avg_tokens=320, sample_size=50, source="x")
    p = tmp_path / "rec.json"
    rec.to_json(p)
    assert RecordedTraffic.from_json(p) == rec


async def test_recorded_from_spans_and_report_agree():
    cfg = StampedeConfig.from_dict(
        {"population": {"size": 30, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"]}, "seed": 42}
    )
    result = await run_simulation(cfg, dry_run=True)
    from_spans = RecordedTraffic.from_spans(result.store.all_spans())
    from_report = RecordedTraffic.from_report(result.report.to_dict())
    # Both routes distill the same run → misuse rates match closely.
    assert abs(from_spans.misuse_rate - from_report.misuse_rate) < 0.05
    assert from_spans.sample_size == 30


# ---- write_pack roundtrip ----


def test_grounded_pack_roundtrips(tmp_path):
    rec = RecordedTraffic(misuse_rate=0.25, source="rec")
    pack = load_pack("core")
    grounded = pack.model_copy(update={"personas": {"naive": fit_persona(pack.get("naive"), rec)}})
    out = tmp_path / "grounded.yaml"
    write_pack(grounded, out)
    reloaded = load_pack(str(out))
    assert reloaded.get("naive").calibration.grounded_against == "rec"
    assert reloaded.get("naive").temperament.misread_rate == grounded.get("naive").temperament.misread_rate


# ---- the full loop: grounding improves realism (TEST-PLAN §4.8) ----


async def test_grounding_improves_realism(tmp_path):
    def cfg(pack: str, grounded_against: str | None) -> StampedeConfig:
        return StampedeConfig.from_dict(
            {
                "target": {"type": "mock", "world": "crm"},
                "population": {
                    "size": 60,
                    "mix": {"naive": 1.0},
                    "models": ["dry-run:heuristic"],
                    "pack": pack,
                    "grounded_against": grounded_against,
                },
                "seed": 42,
            }
        )

    # A recording whose misuse (25%) is far from ungrounded naive (~52%).
    baseline = (await run_simulation(cfg("core", None), dry_run=True)).report.to_dict()
    sim0 = RecordedTraffic.from_report(baseline)
    recording = RecordedTraffic(
        misuse_rate=0.25, give_up_rate=sim0.give_up_rate, avg_tokens=sim0.avg_tokens, source="real"
    )
    rec_path = tmp_path / "real.json"
    recording.to_json(rec_path)

    # Ungrounded run scored against the recording.
    ungrounded = (await run_simulation(cfg("core", str(rec_path)), dry_run=True)).report
    assert ungrounded.realism is not None

    # Fit → grounded pack, then run with it.
    src = load_pack("core")
    grounded_pack = src.model_copy(
        update={"personas": {"naive": fit_persona(src.get("naive"), recording)}}
    )
    pack_path = tmp_path / "grounded.yaml"
    write_pack(grounded_pack, pack_path)
    grounded = (await run_simulation(cfg(str(pack_path), str(rec_path)), dry_run=True)).report
    assert grounded.realism is not None

    # The calibrated population matches the recording better than the default did.
    assert grounded.realism["score"] > ungrounded.realism["score"]
    assert grounded.realism["simulated"]["misuse_rate"] < ungrounded.realism["simulated"]["misuse_rate"]


async def test_no_realism_panel_without_grounding():
    cfg = StampedeConfig.from_dict({"population": {"size": 10, "mix": {"naive": 1.0}}, "seed": 1})
    report = (await run_simulation(cfg, dry_run=True)).report
    assert report.realism is None
    assert "realism" not in report.to_dict()
