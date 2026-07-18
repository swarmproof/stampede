"""Virtual clocks (FR-OR-02). Simulated time, never wall clock — keeps runs
deterministic and compresses hours of agent activity into minutes.

``SimClock`` is the global virtual timeline waves are scheduled against.
``AgentClock`` is a per-agent local clock (started at the agent's wave offset) that
each action advances; spans read their ticks from it, so timings are deterministic
regardless of the order asyncio happens to interleave agents.
"""

from __future__ import annotations


class SimClock:
    """Global virtual timeline. ``compression`` documents the wall→virtual ratio."""

    def __init__(self, compression: float = 60.0) -> None:
        self._tick = 0
        self.compression = compression

    def now(self) -> int:
        return self._tick

    def advance(self, dt: int) -> int:
        self._tick += max(0, dt)
        return self._tick


class AgentClock:
    """Per-agent local clock. Latencies accrue here → deterministic span ticks."""

    def __init__(self, start: int = 0) -> None:
        self._tick = start

    def now(self) -> int:
        return self._tick

    def advance(self, dt: int) -> int:
        self._tick += max(0, dt)
        return self._tick
