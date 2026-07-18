"""stampede — the wind tunnel for the agent economy.

Generate a population of realistic (and adversarial) agents and turn them loose
on your MCP server, API, or protocol in a sandbox, then read the Agent Readiness
Report of where they succeed, get confused, and break you.

Public entry points live in :mod:`stampede.cli`; the programmatic run API is
:func:`stampede.run.run_simulation`.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
