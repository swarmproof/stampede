# stampede — Roadmap

Status: updated 2026-09-04 · Legend: ✅ shipped · 🚧 partial / scaffolded · ⬜ not started

The implementation ran well ahead of the original roadmap — most of v0.1 and v0.2 and a chunk of v0.3 are shipped, plus a set of features that weren't on the original list (see *Shipped beyond the original roadmap*). Remaining items are mostly gated on external infra (Ray, Foundry) or a sibling repo (mockworld).

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
- ⬜ mockworld integration (`stampede` targets a `mockworld` world) *(needs the mockworld sibling)*
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

## Nearest up next
1. EVMTarget live-fork path (signed tx + ABI→ToolSet) against an Anvil fork.
2. Ray executor backend for 2,000+ agent runs.
3. costbomb standalone extraction; mockworld deep integration.
