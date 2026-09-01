"""Compat facade — the persona-pack schema now lives in agent-reliability-core.

Import from here or from ``agent_reliability_core.persona.schema`` directly; this
module re-exports the extracted types so existing ``stampede.personas.schema``
imports keep working (ADR-4)."""

from __future__ import annotations

from agent_reliability_core.persona.schema import (
    Calibration,
    Persona,
    PersonaPack,
    RetryPolicy,
    Temperament,
)

__all__ = ["Calibration", "Persona", "PersonaPack", "RetryPolicy", "Temperament"]
