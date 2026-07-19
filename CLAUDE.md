# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is (read first)

**stampede** is *the wind tunnel for the agent economy*: a tool that generates a population of realistic (and adversarial) LLM agents and turns them loose on a target — an MCP server, HTTP API, or onchain protocol — in a sandbox, then produces an **Agent Readiness Report** and a **watchable live dashboard** of where the target succeeds, confuses agents, and breaks.

The repo now contains a working **v0.1 implementation** of the critical path (`E1 primitives → E4 orchestrator/chaos → E5 observer/report → E6 CLI`) alongside the design docs. The deterministic zero-LLM `--dry-run` pipeline runs end-to-end and is the CI-gated, tested path; live-LLM providers and the dashboard are real but experimental/scaffolded. The design docs remain the source of truth — honor the architecture and invariants below rather than reinventing them, and preserve the docs' cross-reference contract when editing them.

## Commands

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"   # dev install
.venv/bin/stampede init                                     # write a starter stampede.yaml
.venv/bin/stampede run --dry-run                            # zero-LLM deterministic run → report
.venv/bin/stampede run --dry-run --target mock:payments     # the exactly-once world
.venv/bin/stampede plan                                     # pre-run cost estimate
.venv/bin/stampede run --dry-run --json a.json              # save a report for diffing
.venv/bin/stampede diff a.json b.json                       # statistical run-diff (CI regression gate)
.venv/bin/pytest -q                                         # full suite (zero-LLM, deterministic)
.venv/bin/pytest tests/test_e2e.py -q                       # DoD e2e scenarios only
.venv/bin/pytest -q -k determinism                          # a single test by keyword
.venv/bin/ruff check src tests                              # lint (CI gate)
.venv/bin/mypy src/stampede                                 # type-check (CI gate)
.venv/bin/pytest --cov=stampede --cov-report=term-missing   # coverage
```

Optional extras: `.[mcp]` (real MCP servers), `.[otel]` (OTLP export), `.[dashboard]` (live UI), `.[providers]` (Anthropic/OpenAI live swarms). Run against a real MCP server: `stampede run --target "python examples/echo_server.py" --dry-run` (needs `pip install mcp`).

## Code map (package → component)

`src/stampede/` mirrors the `ARCHITECTURE.md` components one-to-one:

| Package | Component / role |
|---|---|
| `trace/` | trace-format primitive — OTel GenAI profile (`schema`), SQLite store, `Tracer`, OTLP `export` |
| `personas/` | persona-pack primitive — v1 schema, loader (`extends` + seeded mix), `packs/core.yaml` (the 6 temperaments) |
| `targets/` | Target Adapters (`mock`, `http`, `mcp`) + `base` protocol + `safety` gate |
| `goals/` | Goal Synthesis — template (deterministic) mode + the intent/misuse oracle |
| `population/` | Population Factory, `Agent` + six-state machine, `brain` (heuristic + LLM), `providers` + cost model |
| `orchestrator/` | concurrency-core — `SimClock`, curves, `scheduler`, and `engine` (the run loop) |
| `chaos/` | fault `injector` + `recovery` (exactly-once) |
| `observer/` | `report` aggregation, `renderer` (HTML/terminal), `dashboard`, `export` |
| `run.py` | wires the whole pipeline; `cli.py` | the `init`/`run`/`plan` CLI |

Determinism is load-bearing: seeded IDs (blake2b, no wall-clock), per-agent RNGs, and virtual time make `--dry-run` reports byte-identical (NFR-REPRO-01). Never introduce `time.time()`/`random.random()`/wall-clock into the run or report path.

## Document map (source of truth)

Read in this order for a cold start:

| File | Role |
|---|---|
| `README.md` | The pitch, quickstart, and portfolio context. |
| `SPEC.md` | The original v1.0 design + PRD (the baseline everything extends). |
| `docs/PRD.md` | Requirements with **stable IDs** (`FR-*`, `NFR-*`, `G-*`, `UC-*`). The ID authority. |
| `docs/ARCHITECTURE.md` | Components, `Protocol` interfaces, data models/schemas, ADRs, the OTel trace-format. The "how". |
| `docs/DELIVERY-PLAN.md` | Milestones (v0.1/v0.2/v0.3), epics→tasks (each citing REQ-IDs + size), sequencing, DoD gates. |
| `docs/TEST-PLAN.md` | Verification / acceptance criteria per requirement (the DoD proof). |
| `docs/RESEARCH.md` | Rationale and competitive/market grounding (the "why"). |
| `ROADMAP.md` | The short public roadmap (subset of DELIVERY-PLAN). |
| `.github/good-first-issues.md` | Seeded onboarding issues. |

## Document contract (must preserve when editing docs)

- **Requirement IDs are stable references.** IDs like `FR-TA-05`, `NFR-SEC-01`, `G-7`, `ADR-6` are defined in `PRD.md` / `ARCHITECTURE.md` and cited across every other doc. Never renumber or reuse an ID; add new ones instead. When you change a requirement, update every doc that cites its ID.
- **The `⊕` glyph means "added beyond the original `SPEC.md`."** Keep using it consistently for scope that isn't in the v1.0 baseline; don't strip it from existing entries.
- Each doc carries a `Status:` / `Date:` header and a `Companions:` line — keep those current when making a design pass.

## Planned architecture (for when you implement)

stampede is a **pipeline**: `stampede.yaml → Safety Gate → Target.discover() → Goal Synthesis → Population Factory → Orchestrator drives Agents ⇄ (Chaos-wrapped) Target → Observer records trace-format → dashboard + report.`

Core components (each is a pluggable `Protocol` — structural typing, not inheritance):
- **Target Adapter** — `MCPTarget` (stdio + HTTP/SSE, v0.1 priority), `HTTPTarget` (OpenAPI→ToolSet, v0.1), `EVMTarget` (Anvil fork, v0.2). Interface: `discover() -> ToolSet`, `invoke(call, ctx) -> ToolResult`, `reset(seed)`, `health()`, `isolation()`, `safety_descriptor()`.
- **Target Safety Gate** — runs *before* any connect; allowlist + explicit non-production ack; EVM fork check; budget wiring.
- **Goal Synthesis** — turns a target's tools into **intent-labeled** goals (`llm` / `template` / `traffic` modes). The intent label is the misuse oracle.
- **Population Factory** — builds N heterogeneous `Agent`s from a persona pack + goals + a model list; provider-agnostic `ModelProvider` (Anthropic / OpenAI-compatible / Ollama).
- **Orchestrator (concurrency-core)** — runs the swarm over a `SimClock` with `ramp|spike|steady` curves; per-agent six-state machine; seedable determinism; `AsyncioExecutor` default, `RayExecutor` (v0.2).
- **Chaos Injector** — wraps invokes/lifecycles: `agent_kill`, `tool_timeout`, `tool_failure`, `latency`, `malformed_output`, `rate_limit`; then asserts recovery (hooks `exactly-once`).
- **Observer** — Tracer (OTel spans → SQLite), live FastAPI+WebSocket+Vue/React dashboard, and the `RunReport`→HTML/terminal report-renderer.

The four **shared primitives** stampede *defines* for the rest of the portfolio: **trace-format**, **persona-pack**, **concurrency-core**, **report-renderer**. These are vendored now and extracted to `agent-reliability-core` at v0.2 (`ADR-4`).

## Design invariants (do not violate in any implementation)

These are load-bearing decisions repeated across the docs — an implementer can easily break them by accident:
- **`trace-format` is an OTel GenAI *profile*, not a bespoke schema** (`ADR-1`). Emit standard `gen_ai.*` attributes; put all stampede-specific context under the `swarmproof.*` namespace. Binding on sibling repos.
- **The Safety Gate is mandatory and on by default** (`ADR-6`, `FR-TA-05`, `NG-6`). An adversarial/chaos swarm must never hit unguarded prod/mainnet — allowlist or explicit ack required; `EVMTarget` refuses non-fork RPC. This is a *defensive/authorized-testing* tool; adversarial payloads are sandbox-scoped only.
- **Personas are data (versioned YAML with `extends`), not code subclasses** (`ADR-3`). Temperament params (`patience`, `retry_policy`, `token_budget`, `risk_appetite`, `misread_rate`, `goal_adherence`) live in the pack schema (`swarmproof.dev/persona/v1`).
- **Misuse = realized tool ≠ expected intent, on *labeled* goals only** (`ADR-5`). Intent labels are attached at goal-synthesis time; unlabeled goals are excluded from the misuse-rate denominator (report it transparently).
- **Cost is the real scaling ceiling, not CPU.** Default bulk agents to small/local models; honor the `budget_usd` hard-stop; keep the zero-LLM deterministic `--dry-run` path working for CI.
- **Determinism via `seed`.** A fixed seed must reproduce goal assignment, persona sampling, chaos schedule, and dry-run decisions.

## Implementation notes (what's built vs. deferred)

- **Built & tested (v0.1 critical path):** MockTarget (`crm`/`payments` worlds), HTTPTarget, MCPTarget (stdio + Streamable HTTP, via a single owning worker task — the SDK's anyio session can't be used across concurrent agent tasks), Safety Gate, persona pack + 6 temperaments, template goal synthesis, population factory, orchestrator (curves/SimClock/six-state/budget stop), chaos + exactly-once recovery, trace-format + SQLite store + OTLP/JSON export, Agent Readiness Report (HTML+terminal), and the `init`/`run`/`plan` CLI.
- **Real but experimental:** live LLM brains (`population/brain.py` `LLMBrain` + `providers.py`) — one provider per swarm, off the CI path (dry-run is the tested path). The dashboard (`observer/dashboard.py`) is a post-run scaffold.
- **Deferred to v0.2+ (raise `NotImplementedError` or absent):** EVMTarget, Ray executor, run-diffing, grounding/realism, record mode, persona registry.
- **Stack:** Python 3.11+, `asyncio`; core deps kept light (pydantic, pyyaml, typer, rich, jinja2) so `pip install` + `--dry-run` needs no keys/network; heavy integrations are extras (`mcp`, `otel`, `dashboard`, `providers`, `evm`, `ray`).
- The CI gates (`.github/workflows/ci.yml`) mirror TEST-PLAN §6: ruff + mypy + pytest across 3.11/3.12/3.13, plus a dry-run smoke job asserting byte-identical reports and a safety-gate block.

The critical path to launch is `E1 (primitives) → E4 (orchestrator+chaos) → E5 (observer/report) → E7 (demo)` — build the shared primitives (E1) first; everything depends on them.

## Conventions

- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, ...), atomic, imperative mood. The recent history uses `docs:`-scoped commits since the repo is docs-only so far.
- **Toolkit principles** (from `CONTRIBUTING.md`): *provider-agnostic* (no single-vendor lock-in), *honest over impressive* (document boundaries, don't overpromise), *watchable & reproducible* (seedable, screenshot-worthy outputs).

## Portfolio context

stampede is the flagship of the **Swarm Proof** toolkit (org: `github.com/swarmproof`) — seven interlocking projects for agent-economy reliability: `mockworld`, `mcp-probe`, `costbomb`, `exactly-once`, `agent-postmortems`, `awesome-agent-reliability`. stampede *defines* the shared primitives the others consume and *embeds* costbomb's attack library as its `adversarial:economic` cohort. See `ARCHITECTURE.md §6` for the full interlock table.
