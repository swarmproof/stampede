"""Incident replay (⊕ FR-CH-05) — turn a real post-mortem into a chaos scenario.

Ingests an **agent-postmortems** incident (a small versioned YAML) and replays its
fault mix against the swarm: "run last month's real outage against your current
stack." Each fault carries a *blast radius* (the fraction of invokes/agents it hit),
which becomes the weight the chaos policy injects it at.

The schema is intentionally tiny and stable so the ``agent-postmortems`` sibling can
emit it directly.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_SUPPORTED_API = "swarmproof.dev/incident/v1"

# Fault kinds an incident may name (mirror the chaos fault library + agent_kill).
INCIDENT_FAULTS = {
    "tool_timeout",
    "tool_failure",
    "latency",
    "malformed_output",
    "rate_limit",
    "agent_kill",
}


class IncidentFault(BaseModel):
    kind: str
    blast_radius: float = Field(0.15, ge=0.0, le=1.0)  # fraction of invokes/agents hit
    at_step: int | None = None  # for agent_kill: pin the kill to this step


class Incident(BaseModel):
    api_version: str = _SUPPORTED_API
    id: str = "INC-unknown"
    title: str = ""
    date: str = ""
    faults: list[IncidentFault] = Field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> Incident:
        raw = yaml.safe_load(Path(path).read_text()) or {}
        api = raw.get("apiVersion", _SUPPORTED_API)
        if api != _SUPPORTED_API:
            raise ValueError(
                f"unsupported incident apiVersion {api!r} in {path} "
                f"(this build speaks {_SUPPORTED_API})"
            )
        meta = raw.get("metadata", {})
        faults = [IncidentFault(**f) for f in raw.get("faults", [])]
        unknown = {f.kind for f in faults} - INCIDENT_FAULTS
        if unknown:
            raise ValueError(f"incident {path} names unknown fault kinds: {sorted(unknown)}")
        return cls(
            api_version=api,
            id=meta.get("id", "INC-unknown"),
            title=meta.get("title", ""),
            date=str(meta.get("date", "")),
            faults=faults,
        )
