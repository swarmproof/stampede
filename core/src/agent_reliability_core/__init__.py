"""agent-reliability-core — the shared primitives of the Swarm Proof toolkit.

Extracted from stampede at v0.2 (ADR-4), starting with **trace-format** — the
OpenTelemetry GenAI profile (``gen_ai.*`` + the ``swarmproof.*`` extension) that
mcp-probe, costbomb and mockworld all emit into. Depending on this package instead
of vendoring keeps the portfolio's telemetry contract in one place.

Dependency-free (stdlib only). The persona-pack, report-renderer and
concurrency-core primitives follow here as they stabilize.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
