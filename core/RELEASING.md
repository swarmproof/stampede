# Releasing `agent-reliability-core`

The shared primitives (`trace`, `persona`, `report`, `concurrency`) are published to
PyPI as **`agent-reliability-core`**. They live in-tree under `core/` (the canonical
source) and are built from there.

Once published, stampede's `pip install -e .` resolves the dependency from PyPI, so
the from-source install becomes one step again (closes #36).

## One-time setup (PyPI Trusted Publishing)

No API token is stored anywhere; the release workflow authenticates to PyPI via OIDC.
Configure a **pending trusted publisher** on PyPI *before the first release* (it lets
you publish a project that doesn't exist yet):

1. PyPI → *Your projects* → *Publishing* → *Add a pending publisher*.
2. Fill in:
   - **PyPI project name:** `agent-reliability-core`
   - **Owner:** `swarmproof`  ·  **Repository:** `stampede`
   - **Workflow name:** `release-core.yml`
   - **Environment:** `pypi`
3. (Recommended) In the GitHub repo, add a `pypi` *environment* with required reviewers
   so a human approves each publish.

## Cut a release

```bash
# 1. Bump the version in core/pyproject.toml  (e.g. 0.1.0 → 0.1.1)
# 2. Tag and push — the tag drives the workflow:
git tag core-v0.1.0
git push origin core-v0.1.0
```

`.github/workflows/release-core.yml` then builds, `twine check`s, and publishes
`core/dist/*` to PyPI. The tag version **must** match `core/pyproject.toml`.

## Manual fallback (if you'd rather not use CI)

```bash
python -m build core/
python -m twine check core/dist/*
python -m twine upload core/dist/*        # needs a PyPI API token in ~/.pypirc or env
```

## Verify after publishing

```bash
pip install agent-reliability-core[render]
python -c "from agent_reliability_core.persona.loader import load_pack; print(load_pack('core'))"
```

Then stampede installs in one step:

```bash
pip install -e .        # resolves agent-reliability-core from PyPI
```
