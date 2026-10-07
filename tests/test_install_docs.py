"""Regression guard for #36: the from-source install must set up the vendored core first.

stampede depends on `agent-reliability-core`, which is not published — it's vendored
in-tree at ./core. A bare `pip install -e .` therefore can't resolve it, so the README
quickstart must install ./core first. This test keeps the one-step regression from
silently returning.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_core_is_vendored_and_named_as_the_dependency():
    core_pyproject = (ROOT / "core" / "pyproject.toml").read_text()
    assert 'name = "agent-reliability-core"' in core_pyproject
    assert "agent-reliability-core" in (ROOT / "pyproject.toml").read_text()  # stampede depends on it


def test_readme_installs_core_before_stampede():
    readme = (ROOT / "README.md").read_text()
    core_idx = readme.find("pip install -e './core")
    assert core_idx != -1, "README must document installing the in-tree ./core first (#36)"
    stampede_idx = readme.find("pip install -e .", core_idx + 1)
    assert stampede_idx != -1 and core_idx < stampede_idx, "the ./core install must precede `pip install -e .`"
