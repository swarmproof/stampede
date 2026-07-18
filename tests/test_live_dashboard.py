"""Live dashboard streaming: the LiveHub pub/sub, the engine's lifecycle publishing,
and the dashboard WebSocket snapshot replay."""

from __future__ import annotations

import pytest

from stampede.config import StampedeConfig
from stampede.observer.live import LiveHub
from stampede.run import run_simulation

# ---- LiveHub pub/sub ----


async def test_livehub_fans_out_and_records_history():
    hub = LiveHub()
    q1 = hub.subscribe()
    q2 = hub.subscribe()
    hub.publish({"id": "a", "state": "PLANNING"})
    hub.publish({"id": "a", "state": "DONE"})
    assert (await q1.get())["state"] == "PLANNING"
    assert (await q1.get())["state"] == "DONE"
    assert (await q2.get())["state"] == "PLANNING"  # fanned out to every subscriber
    assert len(hub.snapshot()) == 2  # replayable history for late joiners
    hub.unsubscribe(q1)
    hub.publish({"id": "b", "state": "PLANNING"})
    assert q1.empty() and not q2.empty()  # unsubscribed queue stops receiving


# ---- engine publishes the lifecycle during a run (no browser needed) ----


async def test_engine_streams_agent_lifecycle_to_hub():
    hub = LiveHub()
    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "crm"},
            "population": {"size": 8, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"]},
            "chaos": {"inject": ["tool_timeout"], "kill_agents_at": ["random"], "assert_recovery": True},
            "seed": 42,
        }
    )
    await run_simulation(cfg, dry_run=True, hub=hub)
    events = hub.snapshot()
    assert events, "expected the engine to publish lifecycle events"

    ids = {e["id"] for e in events}
    assert len(ids) == 8  # every agent showed up in the swarm view

    # Each agent reached a terminal state in the stream.
    last_state = {}
    for e in events:
        last_state[e["id"]] = e["state"]
    assert all(s in {"DONE", "FAILED"} for s in last_state.values())

    # The "why did you call X?" reasoning was streamed for the decision.
    assert any(e.get("reasoning") for e in events)


async def test_hub_does_not_break_determinism():
    # Running with a hub must not change the report (publishing is observational).
    cfg = StampedeConfig.from_dict(
        {"population": {"size": 20, "mix": {"naive": 0.7, "expert": 0.3}, "models": ["dry-run:heuristic"]}, "seed": 7}
    )
    with_hub = (await run_simulation(cfg, dry_run=True, hub=LiveHub())).report.to_dict()
    without_hub = (await run_simulation(cfg, dry_run=True)).report.to_dict()
    assert with_hub == without_hub


# ---- dashboard WebSocket (snapshot replay) ----


def test_dashboard_ws_replays_snapshot():
    pytest.importorskip("fastapi")
    from starlette.testclient import TestClient

    from stampede.observer.dashboard import build_app

    hub = LiveHub()
    hub.publish({"id": "agent-0001", "persona": "naive", "state": "DONE"})
    hub.publish({"id": "agent-0002", "persona": "expert", "state": "FAILED"})
    app = build_app(hub, meta="mock:crm · seed 42")

    with TestClient(app).websocket_connect("/ws") as ws:
        assert ws.receive_json() == {"meta": "mock:crm · seed 42"}  # meta first
        first = ws.receive_json()
        second = ws.receive_json()
        assert {first["id"], second["id"]} == {"agent-0001", "agent-0002"}
