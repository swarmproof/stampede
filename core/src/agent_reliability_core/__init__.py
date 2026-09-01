"""agent-reliability-core — the shared primitives of the Swarm Proof toolkit.

Extracted from stampede at v0.2 (ADR-4). Depending on this package instead of
vendoring keeps the portfolio's shared contracts in one place.

Primitives extracted so far:

* ``agent_reliability_core.trace`` — **trace-format**, the OpenTelemetry GenAI
  profile (``gen_ai.*`` + the ``swarmproof.*`` extension) mcp-probe, costbomb and
  mockworld all emit into.
* ``agent_reliability_core.concurrency`` — **concurrency-core**, the virtual-time
  clocks, concurrency curves, and the ``Executor`` protocol the swarm runs on
  (stampede's orchestrator and mcp-probe's load engine).
* ``agent_reliability_core.persona`` — **persona-pack**, the versioned temperament
  schema + loader (``extends``, seeded mix, (de)serialization) consumed by
  stampede's population factory and costbomb's adversarial cohort.

trace-format and concurrency-core are stdlib-only; persona-pack adds pydantic +
pyyaml. report-renderer follows.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
