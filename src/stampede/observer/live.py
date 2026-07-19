"""LiveHub — the pub/sub that makes the swarm *watchable while it runs* (FR-OB-03).

The engine publishes a small agent-state event at each lifecycle transition; the
dashboard's WebSocket subscribers stream those to the browser in real time. A
bounded history lets a browser that connects mid-run (or after) replay the current
state. Publishing never touches span content, so it does not affect determinism.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stampede.population.agent import Agent


def agent_event(agent: Agent, **extra: Any) -> dict[str, Any]:
    """A compact, JSON-safe snapshot of an agent's current state for the swarm view."""
    event = {
        "id": agent.id,
        "persona": agent.persona.name,
        "state": agent.sm.state.value,
        "goal": agent.goal.id,
        "tool": agent.realized_tool,
        "misuse": agent.misuse,
        "killed": agent.killed,
    }
    event.update(extra)
    return event


class LiveHub:
    """A tiny async fan-out. Subscribers each get their own queue of events."""

    def __init__(self, history_limit: int = 5000) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: list[dict[str, Any]] = []
        self._history_limit = history_limit

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        self._history.append(event)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit :]
        for q in self._subscribers:
            q.put_nowait(event)  # unbounded queues → never blocks the run

    def snapshot(self) -> list[dict[str, Any]]:
        """Current event history — replayed to a late-joining subscriber."""
        return list(self._history)
