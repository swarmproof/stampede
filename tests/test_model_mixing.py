"""Model mixing (FR-PF-04) — the observable effect of per-agent model bindings.

In ``--dry-run`` every agent decides heuristically, but each keeps its own binding,
so the cost meter prices each agent by its model. A swarm mixing a paid model with a
free one therefore costs more than an all-free swarm — proof the per-agent binding
flows end-to-end through the run."""

from __future__ import annotations

from stampede.config import StampedeConfig
from stampede.run import run_simulation


def _cfg(models: list[str]) -> StampedeConfig:
    return StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "crm"},
            "population": {"size": 40, "mix": {"naive": 1.0}, "models": models},
            "seed": 42,
        }
    )


async def test_all_free_models_cost_nothing():
    report = (await run_simulation(_cfg(["dry-run:heuristic"]), dry_run=True)).report
    assert report.total_usd == 0.0


async def test_mixing_a_paid_model_adds_cost():
    mixed = (await run_simulation(_cfg(["anthropic:claude-haiku", "dry-run:heuristic"]), dry_run=True)).report
    free = (await run_simulation(_cfg(["dry-run:heuristic"]), dry_run=True)).report
    # The half of the swarm bound to haiku is priced; the free half is not.
    assert mixed.total_usd > free.total_usd == 0.0
    assert mixed.models == ["anthropic:claude-haiku", "dry-run:heuristic"]


async def test_mixing_is_deterministic():
    a = (await run_simulation(_cfg(["openai:gpt-4o-mini", "ollama:llama3"]), dry_run=True)).report.to_dict()
    b = (await run_simulation(_cfg(["openai:gpt-4o-mini", "ollama:llama3"]), dry_run=True)).report.to_dict()
    assert a == b
