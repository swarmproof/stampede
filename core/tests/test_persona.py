"""persona-pack tests — standalone, imports only agent_reliability_core.persona."""

from __future__ import annotations

import pytest
from agent_reliability_core.persona import (
    Temperament,
    list_builtin_packs,
    load_pack,
    sample_mix,
    write_pack,
)

_CONTRIB = """\
apiVersion: swarmproof.dev/persona/v1
kind: PersonaPack
metadata: {name: contrib, version: "2.0"}
personas:
  - {name: gremlin, temperament: {misread_rate: 0.9, patience: 1}}
"""


def test_builtin_core_pack_loads_with_six_personas():
    assert "core" in list_builtin_packs()
    pack = load_pack("core")
    assert set(pack.personas) == {"naive", "expert", "impatient", "frugal", "adversarial", "drunk"}


def test_extends_inheritance():
    pack = load_pack("core")
    # impatient extends naive, overriding only patience + retry.
    assert pack.get("impatient").temperament.patience == 2
    assert pack.get("impatient").temperament.misread_rate == pack.get("naive").temperament.misread_rate


def test_sample_mix_is_deterministic_and_exact():
    pack = load_pack("core")
    mix = {"naive": 0.6, "expert": 0.4}
    a = [p.name for p in sample_mix(pack, mix, 50, seed=42)]
    b = [p.name for p in sample_mix(pack, mix, 50, seed=42)]
    assert a == b
    assert a.count("naive") == 30 and a.count("expert") == 20


def test_search_paths_resolve_installed_packs(tmp_path):
    # The generic seam that lets a consumer (stampede's registry) add its dir
    # without this primitive depending on it.
    (tmp_path / "contrib.yaml").write_text(_CONTRIB)
    with pytest.raises(FileNotFoundError):
        load_pack("contrib")  # not found without the search path
    pack = load_pack("contrib", search_paths=[tmp_path])
    assert pack.get("gremlin").temperament.misread_rate == 0.9


def test_write_pack_roundtrip(tmp_path):
    pack = load_pack("core")
    out = tmp_path / "core.yaml"
    write_pack(pack, out)
    assert load_pack(str(out)).get("expert").temperament.misread_rate == pack.get("expert").temperament.misread_rate


def test_temperament_bounds():
    with pytest.raises(ValueError):
        Temperament(misread_rate=1.5)  # 0..1
