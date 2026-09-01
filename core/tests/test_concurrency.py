"""concurrency-core tests — standalone, imports only agent_reliability_core."""

from __future__ import annotations

import asyncio

import pytest
from agent_reliability_core.concurrency import (
    AgentClock,
    AsyncioExecutor,
    SimClock,
    schedule_offsets,
)


def test_curves():
    assert schedule_offsets(4, "steady", 4, 30) == [0, 0, 0, 0]
    ramp = schedule_offsets(4, "ramp", 4, 30)
    assert ramp[0] == 0 and ramp[-1] == 30 and ramp == sorted(ramp)
    assert schedule_offsets(5, "spike", 2, 30) == [0, 0, 30, 30, 30]
    with pytest.raises(ValueError):
        schedule_offsets(3, "nope", 3, 10)


def test_clocks_advance_monotonically():
    sim = SimClock()
    assert sim.now() == 0
    assert sim.advance(5) == 5 and sim.advance(3) == 8
    assert sim.advance(-1) == 8  # never goes backwards
    agent = AgentClock(start=100)
    assert agent.now() == 100 and agent.advance(20) == 120


async def test_asyncio_executor_caps_concurrency_and_isolates_failures():
    running = 0
    peak = 0

    async def work(i: int) -> int:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0)
        running -= 1
        if i == 3:
            raise RuntimeError("boom")
        return i

    factories = [(lambda i=i: work(i)) for i in range(10)]
    results = await AsyncioExecutor().run(factories, concurrency=2)
    assert peak <= 2  # semaphore cap honored
    # A failing task is isolated as an exception, never aborts the batch.
    assert isinstance(results[3], RuntimeError)
    assert results[0] == 0 and len(results) == 10
