"""Persona-pack registry & sharing (FR-PF-07) — the ecosystem flywheel.

Community packs live in a local registry dir (``$STAMPEDE_HOME/personas``, default
``~/.stampede/personas``). ``stampede persona add <source>`` validates a pack (local
path or URL) and installs it there under its ``metadata.name``; ``load_pack`` then
resolves a bare name against builtins **and** the registry, so ``population.pack:
<name>`` just works once a pack is installed.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from stampede.personas.loader import load_pack
from stampede.personas.schema import PersonaPack


def registry_dir() -> Path:
    """Where installed community packs live. Honors ``$STAMPEDE_HOME``."""
    home = os.environ.get("STAMPEDE_HOME")
    base = Path(home) if home else Path.home() / ".stampede"
    return base / "personas"


@dataclass
class InstalledPack:
    name: str
    path: Path
    version: str


def add_pack(source: str, *, dest: Path | None = None) -> InstalledPack:
    """Install a pack from a local path or URL into the registry.

    The pack is validated (must load as a ``PersonaPack``) before being written,
    so a broken pack never lands in the registry."""
    dest_dir = dest or registry_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    if source.startswith(("http://", "https://")):
        text = _fetch(source)
        tmp = dest_dir / ".incoming.yaml"
        tmp.write_text(text)
        pack = _validate(tmp)
        final = dest_dir / f"{pack.name}.yaml"
        tmp.replace(final)
    else:
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(f"persona pack source not found: {source}")
        pack = _validate(src)
        final = dest_dir / f"{pack.name}.yaml"
        shutil.copyfile(src, final)

    return InstalledPack(name=pack.name, path=final, version=pack.version)


def list_installed(dest: Path | None = None) -> list[InstalledPack]:
    dest_dir = dest or registry_dir()
    if not dest_dir.exists():
        return []
    out: list[InstalledPack] = []
    for path in sorted(dest_dir.glob("*.yaml")):
        try:
            pack = load_pack(str(path))
        except Exception:
            continue  # skip malformed files rather than crash `persona list`
        out.append(InstalledPack(name=pack.name, path=path, version=pack.version))
    return out


def _validate(path: Path) -> PersonaPack:
    return load_pack(str(path))  # raises on a malformed / unsupported pack


def _fetch(url: str) -> str:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError("fetching a pack by URL needs httpx: pip install 'stampede[dev]'") from exc
    resp = httpx.get(url, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.text
