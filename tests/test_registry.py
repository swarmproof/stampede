"""Persona-pack registry & sharing (FR-PF-07)."""

from __future__ import annotations

import pytest

from stampede.personas.loader import load_pack
from stampede.personas.registry import add_pack, list_installed, registry_dir

_PACK_YAML = """\
apiVersion: swarmproof.dev/persona/v1
kind: PersonaPack
metadata: {name: contrib, version: "2.0", description: "a community pack"}
personas:
  - name: gremlin
    description: "chaotic tester"
    temperament: {misread_rate: 0.9, goal_adherence: 0.1, patience: 1}
"""


def _stampede_home(tmp_path, monkeypatch):
    monkeypatch.setenv("STAMPEDE_HOME", str(tmp_path / "home"))
    return tmp_path


def test_registry_dir_honors_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STAMPEDE_HOME", str(tmp_path))
    assert registry_dir() == tmp_path / "personas"


def test_add_from_local_path_and_load_by_name(tmp_path, monkeypatch):
    _stampede_home(tmp_path, monkeypatch)
    src = tmp_path / "contrib.yaml"
    src.write_text(_PACK_YAML)

    installed = add_pack(str(src))
    assert installed.name == "contrib" and installed.version == "2.0"
    # Installed under its metadata name, resolvable by bare name via load_pack.
    pack = load_pack("contrib")
    assert "gremlin" in pack.personas
    assert pack.get("gremlin").temperament.misread_rate == 0.9


def test_list_installed(tmp_path, monkeypatch):
    _stampede_home(tmp_path, monkeypatch)
    (tmp_path / "p.yaml").write_text(_PACK_YAML)
    add_pack(str(tmp_path / "p.yaml"))
    names = [p.name for p in list_installed()]
    assert names == ["contrib"]


def test_add_rejects_malformed_pack(tmp_path, monkeypatch):
    _stampede_home(tmp_path, monkeypatch)
    bad = tmp_path / "bad.yaml"
    bad.write_text("apiVersion: swarmproof.dev/persona/vNOPE\npersonas: []\n")
    with pytest.raises(ValueError):  # unsupported apiVersion
        add_pack(str(bad))
    # Nothing landed in the registry.
    assert list_installed() == []


def test_add_missing_source_errors(tmp_path, monkeypatch):
    _stampede_home(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError):
        add_pack(str(tmp_path / "nope.yaml"))


async def test_installed_pack_drives_a_run(tmp_path, monkeypatch):
    _stampede_home(tmp_path, monkeypatch)
    (tmp_path / "contrib.yaml").write_text(_PACK_YAML)
    add_pack(str(tmp_path / "contrib.yaml"))

    from stampede.config import StampedeConfig
    from stampede.run import run_simulation

    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "mock", "world": "crm"},
            "population": {"size": 12, "mix": {"gremlin": 1.0}, "pack": "contrib", "models": ["dry-run:heuristic"]},
            "seed": 42,
        }
    )
    report = (await run_simulation(cfg, dry_run=True)).report
    # The community persona ran; high misread → high misuse.
    gremlin = next(s for s in report.success if s.persona == "gremlin")
    assert gremlin.n == 12 and gremlin.misuse_rate > 0.3
