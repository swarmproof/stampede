"""Load persona packs, resolve ``extends`` inheritance, sample a mix (FR-PF-05)."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml

from stampede.personas.schema import Calibration, Persona, PersonaPack, Temperament

_PACKS_DIR = Path(__file__).parent / "packs"
_SUPPORTED_API = "swarmproof.dev/persona/v1"

# Temperament field names (for override-merge). Kept explicit so an unknown key in
# a contributed pack fails loudly rather than being silently dropped.
_TEMPERAMENT_FIELDS = set(Temperament.model_fields)


def list_builtin_packs() -> list[str]:
    return sorted(p.stem for p in _PACKS_DIR.glob("*.yaml"))


def load_pack(name_or_path: str) -> PersonaPack:
    """Load a pack by builtin name (``"core"``) or by filesystem path."""
    path = Path(name_or_path)
    if not path.exists():
        path = _PACKS_DIR / f"{name_or_path}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"persona pack {name_or_path!r} not found "
            f"(builtins: {', '.join(list_builtin_packs())})"
        )
    raw = yaml.safe_load(path.read_text()) or {}
    return _build_pack(raw, source=str(path))


def _build_pack(raw: dict[str, Any], source: str) -> PersonaPack:
    api = raw.get("apiVersion", _SUPPORTED_API)
    if api != _SUPPORTED_API:
        raise ValueError(
            f"unsupported persona-pack apiVersion {api!r} in {source} "
            f"(this build speaks {_SUPPORTED_API})"
        )
    meta = raw.get("metadata", {})
    name = meta.get("name", "unnamed")
    version = str(meta.get("version", "0.0"))
    pack_ref = f"{name}@{version}"

    raw_personas: list[dict[str, Any]] = raw.get("personas", [])
    by_name = {p["name"]: p for p in raw_personas}

    resolved: dict[str, Persona] = {}
    resolving: set[str] = set()

    def resolve(pname: str) -> dict[str, Any]:
        """Return a fully-merged raw persona dict (temperament + fields)."""
        if pname in resolved:
            return _persona_to_raw(resolved[pname])
        if pname in resolving:
            raise ValueError(f"circular persona extends chain at {pname!r} in {source}")
        if pname not in by_name:
            raise ValueError(f"persona {pname!r} extends unknown persona in {source}")
        resolving.add(pname)

        node = by_name[pname]
        parent_name = node.get("extends")
        base: dict[str, Any] = (
            resolve(parent_name)
            if parent_name
            else {"description": "", "temperament": {}, "attacks": [], "prompt_template": ""}
        )

        merged_temperament = {**base.get("temperament", {}), **(node.get("temperament") or {})}
        unknown = set(merged_temperament) - _TEMPERAMENT_FIELDS
        if unknown:
            raise ValueError(
                f"persona {pname!r} in {source} has unknown temperament keys: {sorted(unknown)}"
            )
        merged = {
            "name": pname,
            "description": node.get("description", base.get("description", "")),
            "temperament": merged_temperament,
            "attacks": node.get("attacks", base.get("attacks", [])),
            "prompt_template": node.get("prompt_template", base.get("prompt_template", "")),
        }
        resolving.discard(pname)
        persona = Persona(
            name=pname,
            description=merged["description"],
            temperament=Temperament(**merged_temperament),
            attacks=list(merged["attacks"]),
            prompt_template=merged["prompt_template"],
            pack=pack_ref,
            calibration=Calibration(**(node.get("calibration") or {})),
        )
        resolved[pname] = persona
        return merged

    for pname in by_name:
        resolve(pname)

    cal_raw = raw.get("calibration", {}) or {}
    return PersonaPack(
        api_version=api,
        kind=raw.get("kind", "PersonaPack"),
        name=name,
        version=version,
        description=meta.get("description", ""),
        license=meta.get("license", "Apache-2.0"),
        personas=resolved,
        calibration=Calibration(**cal_raw),
    )


def _persona_to_raw(p: Persona) -> dict[str, Any]:
    return {
        "description": p.description,
        "temperament": p.temperament.model_dump(),
        "attacks": list(p.attacks),
        "prompt_template": p.prompt_template,
    }


def sample_mix(
    pack: PersonaPack, mix: dict[str, float], size: int, seed: int
) -> list[Persona]:
    """Assign ``size`` agents to personas by weight — deterministic in ``seed``.

    Uses the largest-remainder (Hamilton) method so counts sum to exactly ``size``,
    then a seeded shuffle so wave ordering is reproducible (FR-OR-06).
    """
    for pname in mix:
        pack.get(pname)  # validate every named persona exists (clear error if not)

    total = sum(mix.values())
    exact = {name: size * w / total for name, w in mix.items()}
    floors = {name: int(v) for name, v in exact.items()}
    assigned = sum(floors.values())
    remainder = size - assigned
    # Hand out the leftover seats to the largest fractional remainders, ties by name.
    order = sorted(exact, key=lambda n: (-(exact[n] - floors[n]), n))
    for name in order[:remainder]:
        floors[name] += 1

    agents: list[Persona] = []
    for name in sorted(floors):  # sorted → deterministic base order before shuffle
        agents.extend([pack.get(name)] * floors[name])
    random.Random(seed).shuffle(agents)
    return agents


def write_pack(pack: PersonaPack, path: str | Path) -> None:
    """Serialize a (resolved) pack to swarmproof.dev/persona/v1 YAML — used by
    ``stampede ground`` to emit a calibrated pack that ``load_pack`` reads back."""
    personas = []
    for name in sorted(pack.personas):
        p = pack.personas[name]
        entry: dict[str, Any] = {
            "name": p.name,
            "description": p.description,
            "temperament": p.temperament.model_dump(),
        }
        if p.attacks:
            entry["attacks"] = list(p.attacks)
        if p.prompt_template:
            entry["prompt_template"] = p.prompt_template
        if p.calibration.grounded_against or p.calibration.realism_score is not None:
            entry["calibration"] = p.calibration.model_dump()
        personas.append(entry)
    doc = {
        "apiVersion": pack.api_version,
        "kind": pack.kind,
        "metadata": {
            "name": pack.name,
            "version": pack.version,
            "description": pack.description,
            "license": pack.license,
        },
        "personas": personas,
    }
    Path(path).write_text(yaml.safe_dump(doc, sort_keys=False, default_flow_style=False))
