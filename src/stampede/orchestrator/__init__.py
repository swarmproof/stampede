"""Orchestrator / concurrency-core (FR-OR-*).

Runs the swarm concurrently over **simulated time** with a configurable concurrency
curve, driving each agent through the Cairn six-state machine under chaos, and
recording everything as trace-format spans. ``asyncio`` is the default backend
(``AsyncioExecutor``); a Ray backend slots behind the same ``Executor`` protocol in
v0.2. Everything here is seedable so runs are reproducible (FR-OR-06).
"""

from __future__ import annotations

from stampede.orchestrator.clock import AgentClock, SimClock
from stampede.orchestrator.curves import schedule_offsets
from stampede.orchestrator.engine import Orchestrator, RunOutcome
from stampede.orchestrator.scheduler import AsyncioExecutor, Executor

__all__ = [
    "AgentClock",
    "AsyncioExecutor",
    "Executor",
    "Orchestrator",
    "RunOutcome",
    "SimClock",
    "schedule_offsets",
]
