"""Integration: stampede against a real MCP server over stdio (TEST-PLAN §3).

Skipped unless the ``mcp`` SDK is installed (the ``[mcp]`` extra). Exercises the
real MCPTarget worker/session path: initialize → list_tools → concurrent call_tool
with a swarm — and asserts the misuse map surfaces on live MCP tools.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")  # noqa: F841 — skip the module if the SDK is absent

from stampede.config import StampedeConfig  # noqa: E402
from stampede.run import run_simulation  # noqa: E402

_SERVER = Path(__file__).resolve().parents[1] / "examples" / "echo_server.py"


async def test_swarm_against_real_mcp_server():
    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mcp", "transport": "stdio", "command": f"{sys.executable} {_SERVER}"},
            "population": {"size": 15, "mix": {"naive": 0.7, "expert": 0.3}, "models": ["dry-run:heuristic"]},
            "concurrency": {"curve": "ramp", "peak": 10, "hold": 5},
            "seed": 42,
        }
    )
    result = await run_simulation(cfg, dry_run=True)
    r = result.report
    # Discovered the real tools and drove them.
    tool_calls = r.performance["tool_calls"]
    assert tool_calls >= 15
    # The archive↔delete confusion shows up on the live server's tools.
    tools_seen = {m.expected_tool for m in r.misuse_map} | {m.realized_tool for m in r.misuse_map}
    assert "archive_record" in tools_seen or "delete_record" in tools_seen
