# stampede — Roadmap

Status: updated 2026-10-14 · Legend: ✅ shipped · 🚧 partial / scaffolded · ⬜ not started

The implementation ran well ahead of the original roadmap — most of v0.1 and v0.2 and a chunk of v0.3 are shipped, plus a set of features that weren't on the original list (see *Shipped beyond the original roadmap*). Remaining items are mostly gated on external infra (Ray, Foundry).

## v0.1 (launch)
- ✅ MCPTarget + HTTPTarget adapters (+ in-process MockTarget worlds)
- ✅ 6 built-in personas (naive, expert, impatient, frugal, adversarial, drunk)
- ✅ Orchestrator with concurrency curves (ramp / spike / steady) + simulated time
- ✅ Chaos injector (kills, tool failures, latency, malformed responses; + rate-limit)
- ✅ Agent Readiness Report (HTML + terminal) with misuse map + cost profile
- ✅ Watchable live dashboard (streams the swarm live); one-command local run; provider-agnostic
- ⬜ Cairn case study #1 *(external)*
- ⬜ Launch on HN + the "wind tunnel" essay *(external)*

## v0.2
- 🚧 EVMTarget — the mock lending wallet-swarm + the Anvil **fork-guard** are shipped and tested; the live-fork signed-tx path + contract-ABI discovery need Foundry and land next
- ✅ Persona-pack registry & sharing (`stampede persona add/list/show`)
- ⬜ costbomb extracted as standalone *(embedded as the `adversarial:economic` cohort; standalone extraction pending)*
- 🚧 Distributed backend — the pluggable `Executor` protocol is in place; the Ray backend is not built (needs Ray)
- ✅ Run-diffing in CI (`stampede diff` — statistical, signal-vs-noise)

## v0.3
- ✅ mockworld integration — `target: {type: mockworld}` runs the full mockworld mock library in-process with deterministic `reset(seed)` (needs `stampede[mockworld]`)
- ✅ Framework adapters (LangGraph / CrewAI) — drive the swarm with your own agent
- ⬜ Hosted report sharing *(seed of the commercial tier)*

## Shipped beyond the original roadmap
Features and milestones delivered that weren't on the list above:

- ✅ **agent-reliability-core extraction (ADR-4)** — all four shared primitives (trace-format, concurrency-core, persona-pack, report-renderer) extracted into a standalone, independently-tested distribution the sibling repos consume
- ✅ Live LLM providers + **model mixing** (Anthropic / OpenAI-compatible / Ollama), verified live against Ollama
- ✅ **Persona grounding + realism score** + record mode (the "is this realistic?" answer)
- ✅ **Incident replay** — replay an agent-postmortems incident as a weighted chaos scenario
- ✅ **`--from-probe`** — turn an mcp-probe descriptor into a full run
- ✅ **Agent Ready badge** + machine-readable JSON summary (shields endpoint + self-contained SVG)
- ✅ Exactly-once recovery assertion; intent-labeled goal synthesis; the mandatory Safety Gate
- ✅ Deterministic zero-LLM `--dry-run` path + full CLI test coverage
- ✅ **Multi-step agents** (`max_steps`) — observe each result, decide again (create → use); framework agents replay their full captured sequence
- ✅ **Schema-aware + traffic goal synthesis** — concrete values for discovered tools; `goals.mode: traffic` replays recorded calls (`FR-GS-05`)
- ✅ **Type-aware heuristic args** — dry-run args respect schema types/enums
- ✅ **Reproducibility hardening** — `run_id` is an experiment fingerprint; one n-weighted misuse rate across terminal/badge/JSON; case-study figures locked by a drift test

## Remaining work

Everything below is gated **by choice** — external infra, a release, a product decision, or reserved for contributors. The infra-free engineering is complete; there are no half-built core features or reachable crash paths left.

**Needs external infra**
- 🚧 EVMTarget live-fork — signed-tx path + ABI→ToolSet (needs Foundry/Anvil; the mock lending world + fork-guard are shipped)
- 🚧 Ray executor backend — for 2,000+ agent runs (the pluggable `Executor` protocol is in place; needs Ray)

**Release**
- 🚧 Publish `agent-reliability-core` to PyPI — build, `twine check`, and the Trusted-Publishing release workflow are ready (`core/RELEASING.md`); tag `core-v0.1.0` to ship. Unblocks the one-step `pip install -e .`.

**Commercial / sibling**
- ⬜ costbomb standalone extraction (embedded as the `adversarial:economic` cohort today)
- ⬜ A2ATarget · governance-path chaos · hosted report sharing (the commercial tier)

**Infra-free feature work**
- ⬜ `LLMBrain` reactive-path hardening — genuinely state-threading multi-step (re-decide against *real* results, thread real IDs), vs the framework path's pre-planned replay

**Contributor-reserved** (`good-first-issue`)
- ⬜ #1 naive persona-pack example · #2 document the `stampede.yaml` schema · #4 "your first simulation" tutorial

**External (launch)**
- ⬜ Cairn case study #1 · HN launch + the "wind tunnel" essay
