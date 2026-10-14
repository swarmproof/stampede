"""Traffic-mode goal synthesis (FR-GS-05): replay recorded tool calls as goals."""

from __future__ import annotations

import json

import pytest

from stampede.config import StampedeConfig
from stampede.goals.synth import synthesize
from stampede.run import run_simulation
from stampede.targets.base import ToolSet, ToolSpec

_SCHEMA = {"type": "object", "properties": {"record_id": {"type": "string"}}, "required": ["record_id"]}


def _ts() -> ToolSet:
    return ToolSet(tools=[
        ToolSpec(name="archive_record", description="archive", input_schema=_SCHEMA),
        ToolSpec(name="delete_record", description="delete", input_schema=_SCHEMA),
    ])


def _write(tmp_path, calls) -> str:
    p = tmp_path / "traffic.json"
    p.write_text(json.dumps(calls))
    return str(p)


def test_traffic_goals_replay_recorded_calls(tmp_path):
    path = _write(tmp_path, [
        {"tool": "archive_record", "arguments": {"record_id": "rec_7"}},
        {"tool": "delete_record", "arguments": {"record_id": "rec_8"}, "text": "nuke rec_8"},
    ])
    goals = synthesize(_ts(), mode="traffic", count=4, traffic=path)
    assert len(goals) == 4  # cycled to fill count
    assert goals[0].intent.expected_tool == "archive_record" and goals[0].labeled
    assert goals[0].args == {"record_id": "rec_7"} and "rec_7" in goals[0].text
    assert goals[1].text == "nuke rec_8"               # explicit text honored
    assert goals[2].intent.expected_tool == "archive_record"  # cycled back to the start


def test_traffic_skips_tools_the_target_doesnt_expose(tmp_path):
    path = _write(tmp_path, [
        {"tool": "nonexistent", "arguments": {}},
        {"tool": "archive_record", "arguments": {"record_id": "r1"}},
    ])
    goals = synthesize(_ts(), mode="traffic", count=2, traffic=path)
    assert all(g.intent.expected_tool == "archive_record" for g in goals)


def test_traffic_errors_when_nothing_matches(tmp_path):
    path = _write(tmp_path, [{"tool": "nope", "arguments": {}}])
    with pytest.raises(ValueError, match="no recorded calls"):
        synthesize(_ts(), mode="traffic", count=2, traffic=path)


def test_traffic_mode_requires_a_path():
    with pytest.raises(ValueError, match="needs goals.traffic"):
        synthesize(_ts(), mode="traffic", count=2)


def test_traffic_is_deterministic(tmp_path):
    path = _write(tmp_path, [{"tool": "archive_record", "arguments": {"record_id": "r1"}}])
    sig = lambda gs: [(g.text, g.args, g.intent.expected_tool) for g in gs]  # noqa: E731
    assert sig(synthesize(_ts(), mode="traffic", count=5, traffic=path)) == \
           sig(synthesize(_ts(), mode="traffic", count=5, traffic=path))


async def test_traffic_mode_drives_a_full_run(tmp_path):
    path = _write(tmp_path, [
        {"tool": "archive_record", "arguments": {"record_id": "rec_1"}},
        {"tool": "delete_record", "arguments": {"record_id": "rec_2"}},
    ])
    cfg = StampedeConfig.from_dict({
        "target": {"type": "mock", "world": "crm"},
        "population": {"size": 10, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"]},
        "goals": {"mode": "traffic", "traffic": path},
        "report": {"trace_db": ":memory:", "out": "x.html"},
        "seed": 42,
    })
    result = await run_simulation(cfg, dry_run=True)
    # every agent's goal came from the recording — the intended tools are the replayed ones
    assert {a.goal.intent.expected_tool for a in result.outcome.agents} <= {"archive_record", "delete_record"}
    assert result.report.success  # a valid report rendered
