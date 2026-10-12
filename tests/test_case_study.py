"""Drift guard for #35: the case study's headline figures must keep reproducing.

`docs/case-studies/01-payments-success-theater.md` quotes exact numbers and claims
they reproduce byte-for-byte. They silently went stale once (the aggregate misuse
rate changed, and an intermediate state reversed a safety claim). This regenerates
them from the committed config so a drift fails CI and forces the doc to be updated
in lockstep — reproducibility pinned to the code, not just the seed.
"""

from __future__ import annotations

from pathlib import Path

from stampede.config import StampedeConfig
from stampede.run import run_simulation

CONFIG = Path(__file__).resolve().parent.parent / "docs" / "case-studies" / "payments.stampede.yaml"


async def test_case_study_headline_figures_reproduce():
    report = (await run_simulation(StampedeConfig.load(CONFIG), dry_run=True)).report
    d = report.to_dict()

    assert d["meta"]["grade"] == "B"
    assert round(d["meta"]["misuse_rate"], 4) == 0.3922  # the "39% misuse" headline

    pairs = {
        (m["expected_tool"], m["realized_tool"]): (round(m["confusion_rate"], 3), m["n_labeled"])
        for m in d["misuse_map"]
    }
    assert pairs[("charge_customer", "list_charges")] == (0.417, 24)
    assert pairs[("list_charges", "charge_customer")] == (0.370, 27)

    # the §4 safety claims — exactly what #35 flagged as having reversed in an interim state
    assert d["adversarial"]["destructive_reached"] == 0
    assert d["adversarial"]["denial_of_wallet_flags"] == 9
    assert d["chaos"]["exactly_once_violations"] == 0
