"""Facade over ``agent_reliability_core.persona`` (ADR-4).

The pack schema + loader are extracted to core. stampede layers its **community
registry** on top: :func:`load_pack` here adds the installed-pack directory to
core's ``search_paths`` so ``population.pack: <installed-name>`` resolves after a
``stampede persona add``. The pure functions (``sample_mix``, ``write_pack``,
``list_builtin_packs``) are re-exported unchanged.
"""

from __future__ import annotations

from agent_reliability_core.persona.loader import (
    list_builtin_packs,
    sample_mix,
    write_pack,
)
from agent_reliability_core.persona.loader import load_pack as _core_load_pack
from agent_reliability_core.persona.schema import PersonaPack

__all__ = ["list_builtin_packs", "load_pack", "sample_mix", "write_pack"]


def load_pack(name_or_path: str) -> PersonaPack:
    """Load a pack by path/builtin name, also searching the community registry."""
    # Lazy import avoids a loader↔registry cycle (registry imports this module).
    from stampede.personas.registry import registry_dir

    return _core_load_pack(name_or_path, search_paths=[registry_dir()])
