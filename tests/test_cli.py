"""End-to-end CLI coverage — the Typer layer: arg parsing, flag→config wiring,
file outputs, and exit codes. These lock the surface users actually touch."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from stampede.cli import app

runner = CliRunner()


def _run(args, tmp_path, monkeypatch, env=None):
    monkeypatch.chdir(tmp_path)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    return runner.invoke(app, args)


# ---- init ----


def test_init_writes_config(tmp_path, monkeypatch):
    r = _run(["init"], tmp_path, monkeypatch)
    assert r.exit_code == 0
    assert (tmp_path / "stampede.yaml").exists()
    # A second init without --force refuses.
    r2 = _run(["init"], tmp_path, monkeypatch)
    assert r2.exit_code == 1
    assert _run(["init", "--force"], tmp_path, monkeypatch).exit_code == 0


# ---- run: outputs + exit codes ----


def test_run_dry_run_writes_report_and_json(tmp_path, monkeypatch):
    r = _run(["run", "--dry-run", "--target", "mock:crm", "--size", "20", "--json", "out.json"], tmp_path, monkeypatch)
    assert r.exit_code == 0
    assert "Agent Readiness Report" in r.stdout
    assert (tmp_path / "stampede-report.html").exists()
    data = json.loads((tmp_path / "out.json").read_text())
    assert data["meta"]["grade"] in {"A", "B", "C", "D", "F"}


def test_run_badge_summary_record_outputs(tmp_path, monkeypatch):
    r = _run(
        ["run", "--dry-run", "--target", "mock:crm", "--size", "15",
         "--badge", "b.svg", "--summary", "s.json", "--record", "rec.json"],
        tmp_path, monkeypatch,
    )
    assert r.exit_code == 0
    assert (tmp_path / "b.svg").read_text().startswith("<svg")
    assert json.loads((tmp_path / "s.json").read_text())["tool"] == "stampede"
    assert "misuse_rate" in json.loads((tmp_path / "rec.json").read_text())


def test_run_fail_under_gates_exit_code(tmp_path, monkeypatch):
    # mock:crm grades ~B/C → --fail-under A fails, --fail-under F passes.
    below = _run(["run", "--dry-run", "--target", "mock:crm", "--size", "20", "--fail-under", "A"], tmp_path, monkeypatch)
    assert below.exit_code == 1
    ok = _run(["run", "--dry-run", "--target", "mock:crm", "--size", "20", "--fail-under", "F"], tmp_path, monkeypatch)
    assert ok.exit_code == 0


def test_run_safety_gate_blocks_production(tmp_path, monkeypatch):
    r = _run(["run", "--dry-run", "--target", "https://api.acme-prod.com"], tmp_path, monkeypatch)
    assert r.exit_code == 2
    assert "Safety Gate" in r.stdout


def test_run_evm_wallet_swarm(tmp_path, monkeypatch):
    (tmp_path / "evm.yaml").write_text(
        "target: {type: evm, world: lending}\npopulation: {size: 20, mix: {naive: 0.6, adversarial: 0.4}, models: [dry-run:heuristic]}\nseed: 42\n"
    )
    r = _run(["run", "--dry-run", "-c", "evm.yaml"], tmp_path, monkeypatch)
    assert r.exit_code == 0 and "Agent Readiness Report" in r.stdout


# ---- plan ----


def test_plan(tmp_path, monkeypatch):
    _run(["init"], tmp_path, monkeypatch)
    r = _run(["plan"], tmp_path, monkeypatch)
    assert r.exit_code == 0 and "estimated spend" in r.stdout


# ---- diff: noise vs regression exit codes ----


def test_diff_noise_vs_regression(tmp_path, monkeypatch):
    _run(["run", "--dry-run", "--target", "mock:crm", "--size", "200", "--json", "a.json"], tmp_path, monkeypatch)
    # A reseed → within the noise band → exit 0.
    (tmp_path / "b.json").write_text((tmp_path / "a.json").read_text())
    assert _run(["diff", "a.json", "b.json"], tmp_path, monkeypatch).exit_code == 0
    # A worsened candidate → significant regression → exit 1.
    worse = json.loads((tmp_path / "a.json").read_text())
    for s in worse["success"]:
        s["misuse_rate"] = min(1.0, s["misuse_rate"] + 0.4)
    (tmp_path / "worse.json").write_text(json.dumps(worse))
    reg = _run(["diff", "a.json", "worse.json"], tmp_path, monkeypatch)
    assert reg.exit_code == 1 and "regression" in reg.stdout.lower()


# ---- persona commands ----


def test_persona_list_add_show(tmp_path, monkeypatch):
    home = tmp_path / "home"
    listing = _run(["persona", "list"], tmp_path, monkeypatch, env={"STAMPEDE_HOME": str(home)})
    assert listing.exit_code == 0 and "core" in listing.stdout

    (tmp_path / "contrib.yaml").write_text(
        "apiVersion: swarmproof.dev/persona/v1\nkind: PersonaPack\n"
        'metadata: {name: contrib, version: "2.0"}\n'
        "personas:\n  - {name: gremlin, temperament: {misread_rate: 0.9}}\n"
    )
    add = _run(["persona", "add", "contrib.yaml"], tmp_path, monkeypatch, env={"STAMPEDE_HOME": str(home)})
    assert add.exit_code == 0 and "installed" in add.stdout
    show = _run(["persona", "show", "contrib"], tmp_path, monkeypatch, env={"STAMPEDE_HOME": str(home)})
    assert show.exit_code == 0 and "gremlin" in show.stdout


# ---- ground ----


def test_ground_writes_grounded_pack(tmp_path, monkeypatch):
    (tmp_path / "rec.json").write_text('{"misuse_rate": 0.2, "give_up_rate": 0.0, "avg_tokens": 500, "sample_size": 100, "source": "real"}')
    r = _run(["ground", "rec.json", "--pack", "core", "--personas", "naive", "--out", "g.yaml"], tmp_path, monkeypatch)
    assert r.exit_code == 0
    assert (tmp_path / "g.yaml").exists()
    assert "misread" in r.stdout


# ---- error-UX paths ----


def test_run_with_no_config_and_no_target_errors(tmp_path, monkeypatch):
    r = _run(["run", "--dry-run"], tmp_path, monkeypatch)
    assert r.exit_code == 2 and "stampede init" in r.stdout


def test_persona_show_unknown_errors(tmp_path, monkeypatch):
    r = _run(["persona", "show", "does-not-exist"], tmp_path, monkeypatch, env={"STAMPEDE_HOME": str(tmp_path / "h")})
    assert r.exit_code == 1


def test_persona_add_missing_file_errors(tmp_path, monkeypatch):
    r = _run(["persona", "add", "nope.yaml"], tmp_path, monkeypatch, env={"STAMPEDE_HOME": str(tmp_path / "h")})
    assert r.exit_code == 1 and "could not add" in r.stdout
