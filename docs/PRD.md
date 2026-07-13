# stampede — Product Requirements Document

*The wind tunnel for the agent economy.*

Status: v1.1 (design pass on top of `SPEC.md`) · Date: 2026-07-13
Companion docs: `RESEARCH.md` (why), `ARCHITECTURE.md` (how), `DELIVERY-PLAN.md` (when), `TEST-PLAN.md` (proof).

Notation: **⊕** marks requirements/features added beyond the original `SPEC.md`. Requirement IDs are stable references used across all docs.

---

## 1. Vision, goals, non-goals

### 1.1 Vision
Every team shipping software *for agents* runs it through stampede first — turning a herd of realistic and adversarial agents loose on their MCP server, API, or protocol in a sandbox — and publishes the resulting **Agent Readiness Report** the way web teams publish a Lighthouse score. "Point a swarm at it before real ones arrive" becomes a standard pre-ship reflex.

### 1.2 Goals (v0.1 launch)
- **G-1** Generate configurable, heterogeneous, stateful agent populations from persona packs + goals.
- **G-2** Run them concurrently against a target (MCPTarget + HTTPTarget) with configurable concurrency curves and simulated time.
- **G-3** Inject chaos (kills, tool failures, latency, malformed responses, rate-limits) and assert recovery.
- **G-4** Produce the **Agent Readiness Report** (HTML + terminal): task success by persona, misuse map, cost profile, concurrency perf, adversarial + chaos findings.
- **G-5** Provide a **watchable live dashboard** with per-agent "why did you call X?" inspection.
- **G-6** One-command local run; provider-agnostic; local-model-friendly; a zero-LLM `--dry-run` CI smoke path.
- **G-7** Ship **Cairn as case study #1** and a mockworld-backed public demo.
- **G-8 ⊕** Emit the OTel-GenAI-profile **trace-format**; ground personas against recorded real traffic (answer the "unreliable simulation" critique).

### 1.3 Non-goals
- **NG-1** Not an agent *evaluation* framework (integrates agentevals; does not replace).
- **NG-2** Not a hosted SaaS in v0.1 (that's the later commercial tier).
- **NG-3** Not a general multi-agent-system orchestration standard/framework — stampede *drives* agents, it does not help you *build* them.
- **NG-4** Not a replacement for k6 on pure stateless HTTP throughput.
- **NG-5** Not a deep security scanner (integrates mcp-scan / defers to specialists; own only light + behavioral security).
- **NG-6 ⊕** Not a production traffic tool — hard sandbox posture; refuses to point the adversarial swarm at unguarded production/mainnet by default.

---

## 2. Personas (who uses it)

Condensed from `RESEARCH.md §5`. Primary = drives v0.1 scope.

| ID | Persona | Priority | Core need |
|---|---|---|---|
| U1 | MCP server / tool-API builder | **Primary** | Misuse map + cost profile before publish |
| U2 | Agent-platform / framework team | High | CI regression gate on reliability |
| U3 | Protocol / DeFi engineer | High (premium, v0.2) | Wallet-agent swarm on a fork |
| U4 | AI researcher | Medium | Reproducible, citable population runs |
| U5 ⊕ | Third-party MCP adopter | Medium | Vet a vendor's server |
| U6 ⊕ | SRE / reliability owner | Medium | Chaos game-day + recovery proof |
| U7 ⊕ | Security / red-teamer | Medium | Adversarial cohort findings |
| U8 ⊕ | DevRel / vendor | Low | Screenshotable report + badge |

---

## 3. Functional requirements

Grouped by subsystem. Each has an ID, a MoSCoW tier, and the target milestone.

### 3.1 Target Adapter (`FR-TA`)

| ID | Requirement | MoSCoW | Milestone |
|---|---|---|---|
| FR-TA-01 | Provide an `MCPTarget` connecting over **stdio** and **HTTP/SSE**, performing MCP `initialize`, discovering tools/resources/prompts, exposing them to agents. | Must | v0.1 |
| FR-TA-02 | Provide an `HTTPTarget` that ingests an OpenAPI/REST spec and exposes endpoints as an agent toolset. | Must | v0.1 |
| FR-TA-03 | Target Adapter interface: `discover() -> ToolSet`, `invoke(tool, args, agent_ctx) -> Result`, `reset()`, `health()`. Protocol-agnostic. | Must | v0.1 |
| FR-TA-04 | `EVMTarget` pointing at an Anvil/Foundry **mainnet fork**; agents hold funded test wallets; tool calls become transactions. | Should | v0.2 |
| FR-TA-05 ⊕ | **Target Safety Gate**: an allowlist + explicit non-production acknowledgement; `EVMTarget` refuses a non-fork RPC by default (verifies fork marker / `chainId`). | Must | v0.1 |
| FR-TA-06 ⊕ | **Per-agent target state isolation policy**: use session/tenant isolation where the target supports it; else `reset()` between waves; document confounding otherwise. | Should | v0.1 |
| FR-TA-07 | `mockworldTarget` convenience: point stampede directly at a mockworld world. | Could | v0.3 |
| FR-TA-08 ⊕ | `A2ATarget` for Agent-to-Agent protocol endpoints. | Could | v0.3+ |

### 3.2 Population Factory (`FR-PF`)

| ID | Requirement | MoSCoW | Milestone |
|---|---|---|---|
| FR-PF-01 | Build **N** `Agent` instances from a persona pack (or mix, e.g. `60% naive / 30% expert / 10% adversarial`) + a goal set. | Must | v0.1 |
| FR-PF-02 | Each agent has: a model binding (provider-agnostic), a temperament (system prompt + behavioral params: retry policy, patience, token budget, risk appetite), private memory, and a goal. | Must | v0.1 |
| FR-PF-03 | Ship **6 built-in personas**: `naive`, `expert`, `impatient`, `frugal`, `adversarial`, `drunk`. | Must | v0.1 |
| FR-PF-04 | **Model mixing** across the swarm (Anthropic + OpenAI-compatible + Ollama), distributed per the `models:` list. | Must | v0.1 |
| FR-PF-05 | Persona packs are **versioned YAML** with a defined schema; support `extends` (inheritance) and composition. | Must | v0.1 |
| FR-PF-06 ⊕ | **Persona grounding/calibration**: fit temperament params (patience, retry, error-rate) to a recorded real-traffic distribution; emit a per-persona *realism score*. | Should | v0.2 |
| FR-PF-07 | Persona-pack **registry & sharing** (`stampede persona add <pack>`). | Should | v0.2 |
| FR-PF-08 | `adversarial:economic` cohort = **costbomb** attack library embedded (denial-of-wallet). | Should | v0.1 (embedded) → extract v0.2 |

### 3.3 Goal Synthesis (`FR-GS`) ⊕ *elevated from a SPEC one-liner*

| ID | Requirement | MoSCoW | Milestone |
|---|---|---|---|
| FR-GS-01 | Auto-generate realistic goals from the target's tool descriptions + resources. | Must | v0.1 |
| FR-GS-02 | Accept author-supplied extra goals in `stampede.yaml`. | Must | v0.1 |
| FR-GS-03 ⊕ | Each goal carries a **difficulty** and an **intent label** (expected tool / expected effect) — the ground-truth oracle for the misuse map. | Must | v0.1 |
| FR-GS-04 ⊕ | A deterministic **template/grammar goal generator** (no LLM) for the `--dry-run` path. | Should | v0.1 |
| FR-GS-05 ⊕ | Derive goals from **recorded real traffic** (record mode) for maximum realism. | Could | v0.2 |

### 3.4 Orchestrator / concurrency-core (`FR-OR`)

| ID | Requirement | MoSCoW | Milestone |
|---|---|---|---|
| FR-OR-01 | Run agents concurrently with a **concurrency curve**: `ramp` / `spike` / `steady`, with `peak` and `hold`. | Must | v0.1 |
| FR-OR-02 | **Simulated time**: a virtual clock compresses long activity into minutes; schedule agents in waves. | Must | v0.1 |
| FR-OR-03 | Per-agent **state machine** (aligns with Cairn's six-state model — dogfood the protocol). | Must | v0.1 |
| FR-OR-04 | Async Python (**asyncio**) core; hundreds of stateful agents on a laptop. | Must | v0.1 |
| FR-OR-05 | Pluggable executor backend; optional **Ray/worker** backend for scale. | Should | v0.2 |
| FR-OR-06 ⊕ | **Seeded determinism contract**: a fixed seed + fixed model/temperature + deterministic scheduler yields a reproducible run (exactly reproducible in `--dry-run`). | Must | v0.1 |
| FR-OR-07 ⊕ | **Graceful global stop** on `budget_usd` breach or `Ctrl-C`, flushing partial results into a valid report. | Must | v0.1 |

### 3.5 Chaos Injector (`FR-CH`)

| ID | Requirement | MoSCoW | Milestone |
|---|---|---|---|
| FR-CH-01 | Inject: **agent kills** (random / specified step), **tool-call failures/timeouts**, **latency degradation**, **malformed/contradictory tool responses**. | Must | v0.1 |
| FR-CH-02 ⊕ | Inject **rate-limiting** as a first-class fault (ReliabilityBench: largest reliability impact). | Must | v0.1 |
| FR-CH-03 | Config-driven via the `chaos:` block in `stampede.yaml`. | Must | v0.1 |
| FR-CH-04 | **Assert recovery**: after chaos, check state survival and that side-effects were **exactly-once** (hooks into `exactly-once`). | Must | v0.1 |
| FR-CH-05 | Ingest an **agent-postmortems** incident as a chaos scenario ("replay last month's real incident against your stack"). | Should | v0.2 |
| FR-CH-06 ⊕ | Governance-path faults: policy-decision-point unreachable, result-queue replay (per 2026 agent-chaos playbooks). | Could | v0.2 |

### 3.6 Observer — trace + UI + report (`FR-OB`)

| ID | Requirement | MoSCoW | Milestone |
|---|---|---|---|
| FR-OB-01 ⊕ | Emit every agent decision/tool-call/result/failure as a span in the **OTel-GenAI-profile trace-format** (`gen_ai.*` + `swarmproof.*`). | Must | v0.1 |
| FR-OB-02 | Trace store: **SQLite** default; Postgres adapter for large runs. | Must (SQLite) | v0.1 / v0.2 |
| FR-OB-03 | **Live dashboard** (local web UI): swarm view (agents as dots hitting tools), live metrics, per-agent inspector ("why did you call X?" from the agent's reasoning trace). | Must | v0.1 |
| FR-OB-04 | **Agent Readiness Report** (HTML + terminal) via the shared oxblood-styled **report-renderer**: task success by persona; **misuse map**; concurrency perf (p50/p95/p99, dropped connections); **cost profile** (per-persona $); adversarial + chaos findings. | Must | v0.1 |
| FR-OB-05 | Export traces to **agentevals / OTel backends** (OTLP). | Should | v0.1 |
| FR-OB-06 ⊕ | **Statistical run-diffing**: compare two runs; flag a metric as regressed only on a significant shift (effect size + confidence interval), not any delta. | Should | v0.2 |
| FR-OB-07 ⊕ | **Realism-score panel**: report how closely the population matched recorded real traffic (when grounding is used). | Could | v0.2 |
| FR-OB-08 | **`Agent Ready` badge** + machine-readable JSON summary for CI/READMEs. | Should | v0.2 |
| FR-OB-09 ⊕ | **Record mode**: capture real agent traffic against a target as trace-format, for grounding + replay. | Should | v0.2 |

### 3.7 CLI & configuration (`FR-CLI`)

| ID | Requirement | MoSCoW | Milestone |
|---|---|---|---|
| FR-CLI-01 | `stampede init` writes a starter `stampede.yaml`. | Must | v0.1 |
| FR-CLI-02 | `stampede run --target … --size N --live` — one-command run. | Must | v0.1 |
| FR-CLI-03 | `stampede.yaml` schema per SPEC §2.3 (target, population, goals, concurrency, chaos, report). | Must | v0.1 |
| FR-CLI-04 | `--dry-run` — zero-LLM heuristic agents, deterministic, for CI smoke. | Must | v0.1 |
| FR-CLI-05 ⊕ | `stampede plan` — **pre-run cost estimate** (population × prices × est. turns) before spending. | Should | v0.1 |
| FR-CLI-06 | `stampede diff run-a run-b` — run-diffing (see FR-OB-06). | Should | v0.2 |
| FR-CLI-07 | `stampede --from-probe <mcp-probe-output>` — upgrade a probe target into a full simulation. | Should | v0.2 |
| FR-CLI-08 | `--fail-under <grade>` / `--budget <usd>` — CI gating flags. | Must | v0.1 |

---

## 4. Non-functional requirements

| ID | Category | Requirement | Target |
|---|---|---|---|
| NFR-PERF-01 | Performance | Sustain a stateful swarm on a developer laptop (16 GB). | ≥ **200** concurrent stateful agents (asyncio), ≥ **2,000** with Ray backend. |
| NFR-PERF-02 | Performance | Dashboard event latency (agent action → visible on live view). | < **500 ms** p95. |
| NFR-PERF-03 | Performance | `--dry-run` full smoke run. | < **30 s** for a 50-agent run, zero network/LLM. |
| NFR-COST-01 | Cost | Enforce `budget_usd` as a **hard pre-spend stop**, never a post-hoc report. | 0 overspend beyond one in-flight turn. |
| NFR-COST-02 | Cost | Default bulk agents to small/local models; cache identical agent contexts. | Documented cost per 100-agent run per model tier. |
| NFR-COST-03 ⊕ | Cost | `stampede plan` estimate within ±25% of actual on the reference demo. | ±25% |
| NFR-REPRO-01 ⊕ | Reproducibility | Seeded `--dry-run` runs are **bit-identical** report-to-report. | 100% |
| NFR-REPRO-02 ⊕ | Reproducibility | Seeded LLM runs (fixed model+temp+seed) reproduce aggregate metrics within CI noise band. | Documented noise band per metric. |
| NFR-SEC-01 ⊕ | Security/Safety | Adversarial cohort + chaos cannot target an unguarded production/mainnet endpoint without explicit acknowledgement. | Enforced by Target Safety Gate (FR-TA-05). |
| NFR-SEC-02 | Security | Secrets (API keys, RPC URLs) never written to traces/reports; redaction on export. | 100% redaction, tested. |
| NFR-SEC-03 ⊕ | Security | stampede's adversarial payloads are clearly scoped as *test* payloads and documented; no live-exploit-against-third-parties framing. | Documented usage policy. |
| NFR-DX-01 | Developer experience | Time from `pip install` to first watchable run against the sample target. | < **5 min**, ≤ 10 lines. |
| NFR-DX-02 | DX | Provider-agnostic: any OpenAI-compatible endpoint + Anthropic SDK + Ollama. | Works with all three. |
| NFR-DX-03 | DX | Clear, actionable report language ("your descriptions are ambiguous: X vs Y at 34%") not raw metrics dumps. | Qualitative review gate. |
| NFR-INTEROP-01 ⊕ | Interoperability | trace-format is a strict **OTel GenAI profile**; traces import into standard OTel backends unmodified. | Validated against ≥1 OTel backend. |
| NFR-REL-01 | Reliability | A crashed agent / failed tool never crashes the run; partial results always produce a valid report. | 0 run-aborting agent-level failures. |

---

## 5. The complete feature set (MoSCoW, by tier)

### 5.1 MUST (v0.1 — the launch minimum that makes it a category, not a load tester)
1. MCPTarget + HTTPTarget + Target Safety Gate.
2. Population Factory: 6 personas, model mixing, versioned persona-pack schema.
3. Goal Synthesis with intent labels + deterministic dry-run generator.
4. Orchestrator: concurrency curves, simulated time, per-agent state machine, seeded determinism, graceful stop.
5. Chaos Injector: kills / failures / latency / malformed / **rate-limit**; assert-recovery + exactly-once hook.
6. Observer: OTel-GenAI trace-format, SQLite store, **live dashboard**, **Agent Readiness Report** (misuse map + cost profile + perf + chaos), agentevals/OTLP export.
7. CLI: `init`, `run --live`, `--dry-run`, `plan`, `--fail-under`/`--budget`.
8. Cairn case study #1 + mockworld-backed public demo.

### 5.2 SHOULD (v0.2)
- EVMTarget (open-Gauntlet), persona grounding/calibration + realism score, persona registry, costbomb extracted, Ray backend, statistical run-diffing, record mode, `Agent Ready` badge + JSON, `--from-probe`, agent-postmortems incident replay, Postgres store.

### 5.3 COULD (v0.3+)
- mockworld deep integration, official framework adapters (LangGraph/CrewAI), A2ATarget, governance-path chaos, hosted report sharing (commercial seed), goal-gen from recorded traffic.

### 5.4 WON'T (this cycle)
- Agent-building framework, hosted SaaS control plane, deep security scanning, distributed consensus guarantees, non-EVM chain targets.

### 5.5 Features MISSING from the SPEC that this PRD adds ⊕
| Feature | Requirement | Why it's needed |
|---|---|---|
| Persona grounding / realism score | FR-PF-06, FR-OB-07 | Answers the "Lost in Simulation" validity critique — the thesis's biggest risk. |
| Target Safety Gate | FR-TA-05, NFR-SEC-01 | Prevents an adversarial swarm from hitting prod/mainnet; trust-brand-critical. |
| Intent-labeled goals (misuse oracle) | FR-GS-03 | Makes the flagship misuse-map number falsifiable. |
| Goal Synthesis as a named subsystem | FR-GS-* | Goal realism is the crux; one YAML line under-serves it. |
| Statistical run-diffing | FR-OB-06 | Naive snapshot diffing flags noise as regression, killing CI trust. |
| Pre-run cost estimator (`plan`) | FR-CLI-05 | Users must predict spend, not just cap it. |
| Deterministic zero-LLM dry-run | FR-CLI-04, FR-OR-06 | Enables a real CI gate. |
| trace-format = OTel GenAI profile | FR-OB-01, NFR-INTEROP-01 | Portfolio-wide interop; avoids a bespoke schema. |
| Per-agent state isolation | FR-TA-06 | Without it, agents confound each other's results. |
| Record mode | FR-OB-09 | Grounding + incident replay + realistic goal derivation. |

---

## 6. Success metrics / north stars

| Metric | Type | Launch (30–60 d) | 12 months |
|---|---|---|---|
| **Distinct repos with a committed `stampede.yaml`** | North star (adoption depth) | 25 | ≥ 25 in public CI |
| GitHub stars | Vanity/reach | 500+ in 30 d | — |
| HN front page | Reach | Yes, launch day | — |
| External persona packs contributed | Ecosystem flywheel | 3 in 60 d | community registry active |
| Framework ships an official stampede adapter | Integration depth | — | ≥ 1 |
| "Agent Readiness Report" screenshotted in the wild | Category signal | — | recurring |
| ⊕ Median `stampede plan` cost-estimate accuracy | Trust | ±25% | ±15% |
| ⊕ Reports that include a chaos-recovery + exactly-once assertion | Thesis proof | — | majority of premium runs |

---

## 7. Dependencies

### 7.1 Shared primitives (build here first, extract later)
| Primitive | stampede's role | Consumed by |
|---|---|---|
| **trace-format** | **Home / first build** (Observer) | mcp-probe, costbomb, mockworld |
| **persona-pack** | **Home / first build** (Population Factory) | costbomb |
| **report-renderer** | **Home / first build** (Observer) | mcp-probe, costbomb |
| **concurrency-core** | **Home / first build** (Orchestrator) | mcp-probe (load engine) |

Packaging decision (per portfolio doc): **vendor-per-repo now, extract to `agent-reliability-core` at ~stampede v0.2** once shapes are proven. trace-format is the first extraction candidate (most stable, most consumers).

### 7.2 Sibling integrations
| Sibling | Integration | Milestone |
|---|---|---|
| **mockworld** | stampede targets a mockworld world (safe demo surface; delete-vs-archive misuse demo) | v0.1 demo / v0.3 deep |
| **costbomb** | embedded as `adversarial:economic` cohort, then extracted | v0.1 → v0.2 |
| **exactly-once** | asserted in chaos recovery (side-effect uniqueness) | v0.1 |
| **agent-postmortems** | incidents ingested as chaos scenarios | v0.2 |
| **mcp-probe** | `stampede --from-probe` upgrades a probe target | v0.2 |
| **Cairn** | case study #1; six-state model dogfooded in the orchestrator | v0.1 |

### 7.3 External
Python 3.11+; official MCP SDK; web3.py + Foundry/Anvil (EVM); FastAPI + a small Vue/React front end; SQLite/Postgres; provider SDKs (Anthropic, OpenAI-compatible, Ollama); OpenTelemetry SDK; optional Ray.

---

## 8. Assumptions & constraints

**Assumptions**
- A1 — Calibrated, mixed-model personas are *realistic enough* to surface real target failures (validated via FR-PF-06 grounding; see open question in RESEARCH §9).
- A2 — Targets under test tolerate `reset()` or support session isolation (else confounding is documented).
- A3 — Small/local models are cheap and good enough for the bulk of the swarm; only a minority need frontier models.
- A4 — OTel GenAI conventions remain the converging standard through the build window.

**Constraints**
- C1 — Must run one-command on a laptop (no mandatory cloud) for adoption.
- C2 — Apache-2.0 license (no AGPL — preserves the enterprise/consulting funnel).
- C3 — Provider-agnostic and local-friendly; degrade to no-LLM (`--dry-run`) where possible.
- C4 — Trust-brand posture: never overpromise guarantees; never ship a foot-gun that can hit production/mainnet silently.
- C5 — Naming voice: lowercase, one-word tools; concept names ("Agent Readiness Report", "persona pack", "misuse map", "denial-of-wallet") are category-defining assets.
