"""persona-pack — versioned agent *temperaments* as data (ADR-3, ADR-4, FR-PF-05).

The schema (``swarmproof.dev/persona/v1``) and loader for shareable persona packs:
``extends`` inheritance, seeded mix sampling, and (de)serialization. Consumed by
stampede's population factory and by costbomb's adversarial cohort. The community
*registry* (install/add) is a consumer concern — pass its directory via
``load_pack(..., search_paths=[...])`` rather than coupling this primitive to it.
"""

from __future__ import annotations

from agent_reliability_core.persona.loader import (
    list_builtin_packs,
    load_pack,
    sample_mix,
    write_pack,
)
from agent_reliability_core.persona.schema import (
    Calibration,
    Persona,
    PersonaPack,
    Temperament,
)

__all__ = [
    "Calibration",
    "Persona",
    "PersonaPack",
    "Temperament",
    "list_builtin_packs",
    "load_pack",
    "sample_mix",
    "write_pack",
]
