# stampede — DELIVERY PLAN

*From scaffold to "Show HN" to open-Gauntlet.*

Status: v1.1 design pass · Date: 2026-07-13
Companions: `PRD.md` (REQ-IDs), `ARCHITECTURE.md` (components), `TEST-PLAN.md` (DoD gates).
Context: stampede is Portfolio Phase D, the XL flagship, targeted Weeks 6–16, built in public, alongside Xerberus. Effort sizing is in **ideal engineer-days (IED)** for a senior dev; calendar is longer given part-time capacity.

Notation: **⊕** = work added beyond `SPEC.md`.

---

## 1. Milestone map

| Milestone | Theme | Ships | Rough effort |
|---|---|---|---|
| **v0.1** | *The wind tunnel* (launch) | MCP+HTTP targets, 6 personas, orchestrator+chaos, Agent Readiness Report, live dashboard, Cairn + mockworld demo, one-command run, CI dry-run gate | ~48 IED |
| **v0.2** | *The premium + the flywheel* | EVMTarget (open-Gauntlet), persona grounding + registry, costbomb extracted, Ray backend, run-diffing, record mode, badge, `--from-probe`, incident replay | ~34 IED |
| **v0.3** | *The world + the commercial seed* | mockworld deep integration, framework adapters, A2ATarget, governance chaos, hosted report sharing | ~26 IED |

---

## 2. Work breakdown (epics → tasks)

Each task cites the REQ-ID(s) it satisfies and a size (S ≤1d, M 2–3d, L 4–6d).

### v0.1 epics

**E1 — Foundations & shared primitives** *(build these first; everything depends on them)*
- T1.1 (M) Repo scaffold, `pip`-installable package, CI stub, `stampede init` writing `stampede.yaml`. `FR-CLI-01/03`
- T1.2 (L) **trace-format** as OTel GenAI profile + `swarmproof.*` attr registry + a schema validator. `FR-OB-01`, `NFR-INTEROP-01`, `ADR-1`
- T1.3 (M) **persona-pack** `v1` YAML schema + loader + `extends` inheritance + validator. `FR-PF-05`, `ADR-3`
- T1.4 (M) **concurrency-core** `Scheduler`/`Executor` protocol + `AsyncioExecutor` + `SimClock`. `FR-OR-01/02/04`
- T1.5 (M) **report-renderer** skeleton: `RunReport`→HTML(Jinja)+terminal(Rich), oxblood theme tokens. `FR-OB-04`
- T1.6 (S) Provider-agnostic **ModelProvider** layer (Anthropic + OpenAI-compat + Ollama) + context cache. `FR-PF-04`, `NFR-COST-02`

**E2 — Target Adapters + Safety**
- T2.1 (L) `MCPTarget` (stdio + HTTP/SSE): initialize, discover, invoke, reset, health. `FR-TA-01/03`
- T2.2 (M) `HTTPTarget` (OpenAPI→ToolSet). `FR-TA-02`
- T2.3 (M) ⊕ **Target Safety Gate** (allowlist + ack + budget wiring). `FR-TA-05`, `NFR-SEC-01`, `ADR-6`
- T2.4 (S) ⊕ Per-agent state isolation policy + `reset()` between waves. `FR-TA-06`

**E3 — Population + Goals**
- T3.1 (M) **Population Factory**: build N agents from pack/mix + model list + private memory. `FR-PF-01/02`
- T3.2 (M) The **6 built-in personas** authored + tuned. `FR-PF-03`
- T3.3 (M) ⊕ **Goal Synthesis** subsystem: LLM mode (from tools) + `template` deterministic mode + intent labels. `FR-GS-01/02/03/04`, `ADR-5`
- T3.4 (M) Embed **costbomb** attack library as `adversarial:economic` cohort. `FR-PF-08`

**E4 — Orchestrator + Chaos**
- T4.1 (M) Concurrency curves (ramp/spike/steady) + waves over SimClock. `FR-OR-01/02`
- T4.2 (M) Per-agent **six-state machine** (Cairn dogfood). `FR-OR-03`
- T4.3 (S) ⊕ Seeded determinism contract + graceful global stop (budget/SIGINT). `FR-OR-06/07`
- T4.4 (L) **Chaos Injector**: kills/timeout/failure/latency/malformed + ⊕ **rate_limit**; config-driven. `FR-CH-01/02/03`
- T4.5 (M) **Recovery assertion** + **exactly-once** hook (state survival + side-effect uniqueness). `FR-CH-04`

**E5 — Observer: dashboard + report**
- T5.1 (L) **Live dashboard**: FastAPI + WebSocket + Vue/React swarm view + live metrics. `FR-OB-03`
- T5.2 (M) **Per-agent inspector** ("why did you call X?" from reasoning span). `FR-OB-03`
- T5.3 (L) **Agent Readiness Report**: success-by-persona, **misuse map**, perf, **cost profile**, chaos, adversarial. `FR-OB-04`
- T5.4 (S) OTLP / agentevals export. `FR-OB-05`
- T5.5 (S) SQLite trace store (WAL). `FR-OB-02`

**E6 — CLI, cost, CI**
- T6.1 (S) `stampede run --live`, `--fail-under`, `--budget`. `FR-CLI-02/08`
- T6.2 (S) ⊕ `--dry-run` zero-LLM deterministic path. `FR-CLI-04`, `NFR-PERF-03`, `NFR-REPRO-01`
- T6.3 (S) ⊕ `stampede plan` pre-run cost estimator. `FR-CLI-05`, `NFR-COST-03`

**E7 — Case studies & launch**
- T7.1 (M) **Cairn** case study #1 (real target, real findings). `G-7`
- T7.2 (M) **mockworld**-backed public demo (the delete-vs-archive misuse GIF). `G-7`, `UC-M10`
- T7.3 (M) Demo GIF (<90s swarm crashing+recovering), "wind tunnel" essay, HN Show, X thread.

### v0.2 epics (condensed)
- E8 `EVMTarget` (Anvil fork + funded wallets + fork-guard) + open-Gauntlet demo. `FR-TA-04`
- E9 ⊕ Persona **grounding/calibration** + realism score; **record mode**. `FR-PF-06`, `FR-OB-07/09`
- E10 Persona **registry** + `persona add`. `FR-PF-07`
- E11 **costbomb** extracted to standalone CLI. `FR-PF-08`
- E12 **Ray** executor backend. `FR-OR-05`
- E13 ⊕ **Statistical run-diffing** + `stampede diff` + CI regression gate. `FR-OB-06`, `FR-CLI-06`
- E14 `Agent Ready` **badge** + JSON summary. `FR-OB-08`
- E15 `--from-probe` handoff. `FR-CLI-07`
- E16 **agent-postmortems** incident replay as chaos. `FR-CH-05`
- E17 Extract `agent-reliability-core` (trace-format first). `ADR-4`

### v0.3 epics (condensed)
- E18 **mockworld** deep integration (`mockworldTarget`). `FR-TA-07`
- E19 Framework adapters (LangGraph/CrewAI). `NG-3`-respecting drivers.
- E20 ⊕ `A2ATarget`. `FR-TA-08`
- E21 ⊕ Governance-path chaos. `FR-CH-06`
- E22 Hosted report sharing (commercial seed).

---

## 3. Sequencing & dependency graph

```
E1 (primitives) ──┬──► E2 (targets+safety) ──┐
                  ├──► E3 (population+goals) ─┼──► E4 (orchestrator+chaos) ──► E5 (observer) ──► E6 (cli) ──► E7 (launch)
                  └──────────────────────────┘
                                                        │
v0.2:  E8 needs E2+E4 ; E9 needs E5(record) ; E11 needs E3(costbomb) ; E12 needs E4 ; E13 needs E5+E1(seed) ; E17 needs stable E1
v0.3:  E18 needs mockworld v0.1 ; E19/E20 need E2 ; E22 needs E5(report) + E13
```

Critical path to launch: **E1 → E4 → E5 → E7** (primitives → orchestrator/chaos → observer/report → demo). E2 and E3 parallelize against E1 once the protocols land. The report (T5.3) and the demo (T7.x) are the launch-gating artifacts — protect their time.

---

## 4. Definition of Done (per milestone)

**v0.1 DoD** — all MUST reqs pass their TEST-PLAN acceptance criteria, AND:
- [ ] `pip install stampede && stampede init && stampede run --target <mockworld> --live` works in < 5 min on a clean laptop. `NFR-DX-01`
- [ ] The e2e "swarm vs mockworld" scenario (TEST-PLAN §4.1) produces a report with a non-trivial **misuse map** and **cost profile**.
- [ ] `--dry-run` run is bit-identical across two invocations and finishes < 30s / 50 agents. `NFR-REPRO-01`, `NFR-PERF-03`
- [ ] Chaos kill + recovery scenario asserts exactly-once and the report shows PASS/FAIL.
- [ ] Safety Gate blocks an off-allowlist target without `acknowledge_non_production`.
- [ ] trace-format validates against the OTel-profile validator and imports into one real OTel backend.
- [ ] Cairn case-study report published; <90s demo GIF recorded.
- [ ] CI green: unit + integration + dry-run smoke gate.

**v0.2 DoD** — EVMTarget runs a wallet-swarm against an Anvil fork and refuses non-fork RPC; a persona reports a realism score after grounding; `stampede diff` flags a *seeded* regression but not seeded noise; costbomb ships standalone; badge + JSON emitted; primitives extracted to `agent-reliability-core` with siblings consuming them.

**v0.3 DoD** — a mockworld world is a one-flag target; ≥1 framework adapter driving real agents; hosted report link shareable.

---

## 5. Effort sizing summary

| Milestone | Epics | ~IED | Notes |
|---|---|---|---|
| v0.1 | E1–E7 | ~48 | E1 (primitives) ~13, E5 (observer/UI) ~11 are the heavy ones; UI is the schedule risk. |
| v0.2 | E8–E17 | ~34 | EVMTarget (~8) + grounding (~7) + extraction (~5) dominate. |
| v0.3 | E18–E22 | ~26 | Mostly integration + the commercial-seed hosting. |

---

## 6. Skills / resources needed

- **Python async** (asyncio `TaskGroup`, cancellation, backpressure) — orchestrator core.
- **MCP protocol** fluency (JSON-RPC, SSE lifecycle) — native to the author.
- **LLM provider integration** + prompt engineering for temperaments.
- **Front-end** (Vue/React + WebSocket) for the live dashboard — the one area that may warrant help; it's the launch-gating spectacle.
- **EVM/Foundry** (Anvil forking, web3.py, test wallets) for v0.2 — author's finance background applies.
- **OpenTelemetry** semantics — for the trace-format profile.
- **Design/DevRel** for the report styling, demo GIF, and "wind tunnel" essay.

---

## 7. Launch checklist

**Pre-launch artifacts**
- [ ] <90s **demo GIF** above the README fold: the swarm hitting a target live, crashing, recovering. (The single most important asset.)
- [ ] The **"wind tunnel" essay** (flagship, on the site + The Trust Layer).
- [ ] Cairn case-study report (a real, screenshotable Agent Readiness Report).
- [ ] Public leaderboard-style teaser: run stampede against a few well-known public MCP servers, publish the misuse maps (mirrors the mcp-probe leaderboard play).
- [ ] `stampede.yaml` examples for MCP + HTTP + mockworld in the README, quickstart ≤10 lines.
- [ ] 3–5 seeded `good-first-issue`s (persona contributions especially — seeds the flywheel).
- [ ] `CITATION.cff` current; awesome-agent-reliability entry live; sibling cross-links in README.

**Launch day**
- [ ] "Show HN: stampede — simulate a herd of AI agents against your system before real ones arrive."
- [ ] X thread with the swarm-dashboard GIF ("building a wind tunnel for agents" series finale).
- [ ] r/LocalLLaMA + r/mcp posts.
- [ ] Submissions to Latent Space / TLDR AI.
- [ ] A Trust Layer issue built around the Cairn simulation results.
- [ ] Talk/demo: a live swarm crashing and recovering against Cairn on stage.

**Post-launch (30–60 d)**
- [ ] Track the north star: distinct repos committing a `stampede.yaml`.
- [ ] Court 3 external persona-pack contributions.
- [ ] Ship v0.2 EVMTarget teaser ("open Gauntlet") to keep the DeFi audience warm.
