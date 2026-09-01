"""concurrency-core — the shared swarm-scheduling primitive (ADR-4).

Virtual-time clocks (``SimClock`` / ``AgentClock``), concurrency curves
(``schedule_offsets``: ramp / spike / steady), and a pluggable ``Executor``
protocol (``AsyncioExecutor`` default). stampede's orchestrator and mcp-probe's
load engine both drive the swarm through this one primitive.
"""

from __future__ import annotations

from agent_reliability_core.concurrency.clock import AgentClock, SimClock
from agent_reliability_core.concurrency.curves import schedule_offsets
from agent_reliability_core.concurrency.scheduler import AsyncioExecutor, Executor

__all__ = [
    "AgentClock",
    "AsyncioExecutor",
    "Executor",
    "SimClock",
    "schedule_offsets",
]
