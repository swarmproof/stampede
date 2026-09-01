"""serve_live — the concurrent dashboard-server + swarm orchestration (FR-OB-03).

Exercises the real path: uvicorn binds an ephemeral port, the swarm runs while the
server is up, and on_report fires with the finished result. Guarded on the
``[dashboard]`` extra; not on the CI blocking path."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from stampede.config import StampedeConfig


async def test_serve_live_serves_and_reports():
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    from stampede.run import serve_live

    cfg = StampedeConfig.from_dict(
        {"target": {"type": "mock", "world": "crm"}, "population": {"size": 8, "mix": {"naive": 1.0}}, "seed": 42}
    )
    done = asyncio.Event()
    captured: dict = {}

    def on_report(result) -> None:
        captured["report"] = result.report
        done.set()

    # port=0 → an ephemeral port, so the test never collides with a real server.
    task = asyncio.create_task(serve_live(cfg, dry_run=True, on_report=on_report, port=0))
    try:
        await asyncio.wait_for(done.wait(), timeout=20)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    # The run completed under the live server and reported back.
    assert captured["report"].size == 8
    assert sum(s.n for s in captured["report"].success) == 8
