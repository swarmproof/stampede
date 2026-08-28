"""``--from-probe`` — upgrade an mcp-probe target descriptor into a run (FR-CLI-07).

mcp-probe (the CI quality suite for MCP servers) already knows how to reach a
server. Rather than re-specify the connection, ``stampede run --from-probe out.json``
reads mcp-probe's JSON descriptor and turns it straight into an ``MCPTarget`` config,
so a probe result flows directly into a full behavioural simulation.

The descriptor schema (``swarmproof.dev/probe/v1``) is intentionally small; the
loader also accepts a flat ``{transport, command|url}`` shape for convenience.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stampede.config import TargetConfig


def load_probe(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def target_from_probe(descriptor: dict[str, Any]) -> TargetConfig:
    """Map an mcp-probe descriptor to a stampede ``TargetConfig`` (an MCPTarget)."""
    # Accept either a nested {"target": {...}} block or a flat descriptor.
    t = descriptor.get("target", descriptor)
    transport = t.get("transport", "stdio")

    if transport == "stdio":
        command = t.get("command")
        if not command:
            raise ValueError("probe descriptor: stdio transport needs a 'command'")
        return TargetConfig(type="mcp", transport="stdio", command=command)

    if transport in {"http", "sse"}:
        url = t.get("url")
        if not url:
            raise ValueError(f"probe descriptor: {transport} transport needs a 'url'")
        return TargetConfig(type="mcp", transport=transport, url=url)

    raise ValueError(f"probe descriptor: unsupported transport {transport!r}")


def target_config_from_probe_file(path: str | Path) -> TargetConfig:
    return target_from_probe(load_probe(path))
