"""Live integration: a real swarm driven by a local Ollama model.

Skipped unless the ``openai`` client is installed AND Ollama is reachable with at
least one model pulled. This is the end-to-end proof of the live path; it is not on
the blocking CI gate (live models are nightly/opt-in per TEST-PLAN §6).
"""

from __future__ import annotations

import pytest

pytest.importorskip("openai")  # the OpenAI-compatible client Ollama speaks


def _ollama_models() -> list[str]:
    try:
        import httpx

        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


_MODELS = _ollama_models()
pytestmark = pytest.mark.skipif(
    not _MODELS, reason="Ollama not reachable on :11434 or no models pulled"
)


async def test_live_ollama_swarm_against_mock_crm():
    from stampede.config import StampedeConfig
    from stampede.run import run_simulation

    model = _MODELS[0]
    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "crm"},
            "population": {"size": 2, "mix": {"naive": 1.0}, "models": [f"ollama:{model}"]},
            "concurrency": {"curve": "steady", "peak": 2, "hold": 0},
            "report": {"trace_db": ":memory:", "out": "x.html"},
            "seed": 42,
        }
    )
    result = await run_simulation(cfg, dry_run=False)
    # It ran live and produced a valid report (whatever the model decided).
    assert result.report.size == 2
    assert result.report.grade in {"A", "B", "C", "D", "F"}
    # Every agent reached a terminal state — a downed/odd model fails cleanly, not hangs.
    assert sum(s.n for s in result.report.success) == 2
