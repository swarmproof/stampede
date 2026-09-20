"""End-to-end: a stampede swarm drives a real mockworld world (FR-TA-03, E2E).

Guards the full pipeline — build_target(mockworld) → dry-run swarm → RunReport —
against silent breakage. Skips cleanly without the mockworld extra.
"""

from __future__ import annotations

import pytest

from stampede.config import StampedeConfig
from stampede.run import run_simulation

pytest.importorskip("mockworld", reason="install stampede[mockworld]")


def _cfg(world: str, **extra) -> StampedeConfig:
    return StampedeConfig.from_dict(
        {
            "target": {"type": "mockworld", "world": world},
            "population": {"size": 30, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"]},
            "seed": 7,
            **extra,
        }
    )


async def test_swarm_drives_mockworld_crm_and_produces_a_misuse_map():
    report = (await run_simulation(_cfg("crm"), dry_run=True)).report
    # The report's tools come from the real mockworld crm mock (not a hand-coded world).
    tools = {e.realized_tool for e in report.misuse_map} | {e.expected_tool for e in report.misuse_map}
    assert {"archive_record", "delete_record"} & tools
    assert report.size == 30 and report.seed == 7


async def test_mockworld_run_is_deterministic():
    a = (await run_simulation(_cfg("payments"), dry_run=True)).report.to_dict()
    b = (await run_simulation(_cfg("payments"), dry_run=True)).report.to_dict()
    assert a == b  # reset(seed) → a mockworld run is bit-reproducible through stampede
