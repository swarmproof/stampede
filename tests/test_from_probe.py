"""`--from-probe` — mcp-probe descriptor → MCPTarget config (FR-CLI-07)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from stampede.targets.from_probe import (
    target_config_from_probe_file,
    target_from_probe,
)

# ---- descriptor mapping ----


def test_nested_stdio_descriptor():
    t = target_from_probe(
        {"apiVersion": "swarmproof.dev/probe/v1", "target": {"transport": "stdio", "command": "python s.py"}}
    )
    assert t.type == "mcp" and t.transport == "stdio" and t.command == "python s.py"


def test_flat_descriptor_is_accepted():
    t = target_from_probe({"transport": "stdio", "command": "uv run server"})
    assert t.type == "mcp" and t.command == "uv run server"


def test_http_descriptor():
    t = target_from_probe({"target": {"transport": "http", "url": "http://localhost:9000/mcp"}})
    assert t.type == "mcp" and t.transport == "http" and t.url == "http://localhost:9000/mcp"


def test_missing_fields_error():
    with pytest.raises(ValueError):
        target_from_probe({"target": {"transport": "stdio"}})  # no command
    with pytest.raises(ValueError):
        target_from_probe({"target": {"transport": "http"}})  # no url
    with pytest.raises(ValueError):
        target_from_probe({"target": {"transport": "carrier-pigeon"}})


def test_from_probe_file_roundtrip(tmp_path):
    p = tmp_path / "probe.json"
    p.write_text(json.dumps({"target": {"transport": "stdio", "command": "python s.py"}}))
    t = target_config_from_probe_file(p)
    assert t.command == "python s.py"


# ---- end to end against the real echo MCP server (guarded) ----


async def test_from_probe_drives_the_probed_server(tmp_path):
    pytest.importorskip("mcp")
    from stampede.config import StampedeConfig
    from stampede.run import run_simulation

    server = Path(__file__).resolve().parents[1] / "examples" / "echo_server.py"  # noqa: ASYNC240
    probe = tmp_path / "probe.json"
    probe.write_text(  # noqa: ASYNC240 — tmp-file write in a test; blocking is fine
        json.dumps({"target": {"transport": "stdio", "command": f"{sys.executable} {server}"}})
    )

    cfg = StampedeConfig.from_dict(
        {"population": {"size": 8, "mix": {"naive": 1.0}, "models": ["dry-run:heuristic"]}, "seed": 42}
    )
    cfg.target = target_config_from_probe_file(probe)
    result = await run_simulation(cfg, dry_run=True)
    # The probe descriptor drove a real MCP run against the discovered server.
    assert result.report.performance["tool_calls"] >= 8
