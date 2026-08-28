"""persona-pack — versioned agent *temperaments* as data (ADR-3, FR-PF-05).

Personas are the product's realism knob: their temperament params control how an
agent misreads and misuses a target, because realistic failure is the point. Packs
are versioned YAML with ``extends`` inheritance so the community can contribute and
compose them (the ecosystem flywheel). This package owns the schema and loader;
the six canonical temperaments ship in ``packs/core.yaml``.
"""

from __future__ import annotations

from stampede.personas.loader import list_builtin_packs, load_pack, sample_mix, write_pack
from stampede.personas.registry import add_pack, list_installed, registry_dir
from stampede.personas.schema import Calibration, Persona, PersonaPack, Temperament

__all__ = [
    "Calibration",
    "Persona",
    "PersonaPack",
    "Temperament",
    "add_pack",
    "list_builtin_packs",
    "list_installed",
    "load_pack",
    "registry_dir",
    "sample_mix",
    "write_pack",
]
