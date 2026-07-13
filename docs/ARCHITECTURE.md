# stampede — ARCHITECTURE

*How the wind tunnel is built.*

Status: v1.1 design pass · Date: 2026-07-13
Companions: `PRD.md` (requirements + REQ-IDs), `RESEARCH.md` (rationale), `TEST-PLAN.md` (verification).
Notation: **⊕** = beyond original `SPEC.md`. Requirement refs (e.g. `FR-OB-01`) point at `PRD.md §3`.

---

## 1. System overview

stampede is a **pipeline that manufactures an agent population, drives it concurrently against a target under controlled chaos, and records everything as OTel-GenAI traces that render into a live dashboard and the Agent Readiness Report.**

Five core components sit behind one CLI/core, plus three ⊕-added cross-cutting subsystems (Goal Synthesis, Target Safety Gate, Grounding). Everything the components emit is the shared **trace-format**; everything they render goes through the shared **report-renderer**; the swarm is scheduled by the shared **concurrency-core**; the agents are shaped by the shared **persona-pack**. Those four are the primitives the rest of the portfolio reuses.

```
                                   ┌──────────────────────────────────────────┐
                                   │            stampede CLI / core             │
                                   │  init · run · plan · diff · --dry-run      │
                                   └───────────────────┬────────────────────────┘
                                                       │  loads stampede.yaml
                        ┌──────────────────────────────┼──────────────────────────────┐
                        │                     [ Target Safety Gate ⊕ ]                  │  ← guards before anything connects
                        └──────────────────────────────┼──────────────────────────────┘
                                                       │
   ┌───────────────┬───────────────┬──────────────────┼──────────────────┬───────────────────┐
   ▼               ▼               ▼                  ▼                  ▼                   ▼
┌──────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────────┐ ┌──────────────┐ ┌───────────────────┐
│  Target  │ │  Goal        │ │  Population   │ │ Orchestrator  │ │   Chaos      │ │     Observer       │
│  Adapter │ │  Synthesis ⊕ │ │   Factory     │ │ (concurrency- │ │   Injector   │ │ (trace + UI +      │
│          │ │              │ │               │ │  core)        │ │              │ │  report-renderer)  │
└────┬─────┘ └──────┬───────┘ └──────┬────────┘ └──────┬────────┘ └──────┬───────┘ └─────────┬─────────┘
     │              │                │                 │                 │                    │
 connects to    derives         builds N          runs agents      wraps invokes/       emits trace-format
 MCP/HTTP/EVM   intent-         Agents from        concurrently     lifecycles;          spans; serves live
 (safety-gated) labeled goals   persona pack +     over sim-time;   injects kills/       dashboard; renders
                from tools +    goals + model      per-agent state  fails/latency/       Agent Readiness
                (opt) traffic   mix                machines         rate-limit/malformed  Report; OTLP export
                                                                    → asserts recovery
                                                                       + exactly-once
     │                                                                                        │
     └──────────────────────── all reads/writes flow through ───────────────────────────────┘
                                     Trace Store (SQLite default / Postgres)
                                                       ▲
                                   [ Grounding / Calibration ⊕ ] ── fits personas to recorded traffic
```

**One-line data flow:** `stampede.yaml → Safety Gate → Target.discover() → Goal Synthesis → Population Factory → Orchestrator drives Agents ⇄ (Chaos-wrapped) Target → Observer records trace-format → dashboard + report.`

---

## 2. Components: responsibilities & interfaces

Interfaces are given as Python `Protocol`s (structural typing — the codebase style for pluggability without inheritance coupling).

### 2.1 Target Adapter — "what am I stress-testing?"

Responsibility: abstract the thing under test behind one protocol so the orchestrator is target-agnostic.

```python
class TargetAdapter(Protocol):
    async def discover(self) -> ToolSet: ...           # tools/resources/prompts the agents can use
    async def invoke(self, call: ToolCall, ctx: AgentContext) -> ToolResult: ...
    async def reset(self, seed: int | None = None) -> None: ...   # deterministic reset between waves
    async def health(self) -> HealthStatus: ...
    def isolation(self) -> IsolationMode: ...          # per-agent | per-wave | shared  (FR-TA-06)
    def safety_descriptor(self) -> SafetyDescriptor: ... # used by the Safety Gate (FR-TA-05)
```

| Adapter | Transport | Notes |
|---|---|---|
| `MCPTarget` (v0.1) | stdio / HTTP-SSE | MCP `initialize`, JSON-RPC, SSE persistence handled here — the specifics generic load tools miss. |
| `HTTPTarget` (v0.1) | HTTP | OpenAPI/REST spec → ToolSet. |
| `EVMTarget` (v0.2) | JSON-RPC to Anvil fork | Agents hold funded test wallets; `invoke` → signed tx; `safety_descriptor` asserts fork. |
| `mockworldTarget` (v0.3) | MCP | Thin wrapper — a mockworld world *is* an MCPTarget. |
| `A2ATarget` (v0.3+) ⊕ | A2A | Protocol-agnostic slot. |

### 2.2 Target Safety Gate ⊕ (`FR-TA-05`, `NFR-SEC-01`)

Responsibility: refuse to point an adversarial/chaos swarm at anything unguarded. Runs **before** `discover()`.

- Requires the target to be on an **allowlist** or the run to carry an explicit non-production acknowledgement flag.
- `EVMTarget`: queries `chainId` / fork marker; **refuses a live-mainnet RPC** unless forced with a loud override.
- Enforces the `budget_usd` hard-stop wiring before any spend can occur.
- Emits a `safety.gate` span so the report shows what posture the run used.

### 2.3 Goal Synthesis ⊕ (`FR-GS-*`)

Responsibility: turn a target's surface into realistic, **intent-labeled** goals — the crux of realism and the oracle for the misuse map.

```python
class GoalSynthesizer(Protocol):
    def synthesize(self, toolset: ToolSet, extra: list[str], mode: GoalMode) -> list[Goal]: ...

@dataclass
class Goal:
    id: str
    text: str                       # natural-language objective
    difficulty: Literal["easy","medium","hard"]
    intent: Intent                  # expected tool(s)/effect — the misuse oracle (FR-GS-03)
    labeled: bool                   # False → excluded from misuse-rate denominator
```

- `mode=llm` (default): derive goals from tool descriptions + resources.
- `mode=template` ⊕: deterministic grammar generator, **no LLM**, for `--dry-run`.
- `mode=traffic` ⊕ (v0.2): derive from recorded real traffic (record mode).

### 2.4 Population Factory (`FR-PF-*`)

Responsibility: instantiate N heterogeneous `Agent`s from a persona pack (or mix) + goals + a model list.

```python
@dataclass
class Agent:
    id: str
    persona: Persona                # temperament (see schema §4.2)
    model: ModelBinding             # provider-agnostic
    goal: Goal
    memory: AgentMemory             # private, per-agent
    state: AgentState               # six-state machine (§2.5)

class ModelProvider(Protocol):      # provider-agnostic layer (FR-PF-04)
    async def complete(self, msgs, tools, params) -> Completion: ...   # Anthropic | OpenAI-compat | Ollama
```

The agent's *imperfection is the product*: temperament params (`patience`, `retry_policy`, `token_budget`, `risk_appetite`, `misread_rate`) control how it misreads and misuses. The `adversarial:economic` cohort delegates to the embedded **costbomb** attack library.

### 2.5 Orchestrator / concurrency-core (`FR-OR-*`)

Responsibility: run the swarm concurrently over **simulated time** with a configurable concurrency curve, managing each agent's **six-state machine** (dogfooding Cairn).

```python
class Scheduler(Protocol):                     # the shared concurrency-core primitive
    async def run(self, agents: list[Agent], curve: ConcurrencyCurve,
                  clock: SimClock, executor: Executor) -> RunResult: ...

class Executor(Protocol):                      # pluggable backend
    async def submit(self, coro) -> Any: ...    # AsyncioExecutor (default) | RayExecutor (v0.2)
```

- **Concurrency curve:** `ramp | spike | steady`, with `peak` + `hold` → produces the swarm-concurrency metrics.
- **SimClock:** virtual clock compresses hours into minutes; waves scheduled against it.
- **Agent state machine (Cairn six-state):** `CREATED → PLANNING → ACTING → WAITING → RECOVERING → DONE/FAILED` (dogfoods Cairn's model; the exact six states track Cairn's canonical taxonomy).
- **Determinism (`FR-OR-06`):** a fixed `seed` seeds goal assignment, persona sampling, chaos schedule, and (in `--dry-run`) the heuristic agent decisions → reproducible runs.
- **Graceful stop (`FR-OR-07`):** budget breach / SIGINT flushes partial state to a valid report.

### 2.6 Chaos Injector (`FR-CH-*`)

Responsibility: wrap target invocations and agent lifecycles to inject failure, then assert recovery.

```python
class ChaosPolicy(Protocol):
    def before_invoke(self, call: ToolCall, ctx) -> ChaosAction: ...   # pass | fail | delay | mangle | rate_limit
    def agent_lifecycle(self, agent: Agent, step: int) -> ChaosAction: ...  # kill | pass

class RecoveryAssertion(Protocol):
    def check(self, run: RunResult) -> list[RecoveryFinding]: ...      # state survived? side-effects exactly-once?
```

Fault library (config-driven via `chaos:`): `agent_kill`, `tool_timeout`, `tool_failure`, `latency`, `malformed_output`, **`rate_limit`** ⊕ (ReliabilityBench's top-impact fault), and (v0.2) `governance_path` faults + `incident_replay` from agent-postmortems. Recovery assertion hooks into **exactly-once** to verify side-effect uniqueness after a kill/replay.

### 2.7 Observer — trace + UI + report (`FR-OB-*`)

Three sub-parts over one trace store:

1. **Tracer** — every decision/tool-call/result/failure → a **trace-format** span (§4.1) in the Trace Store (SQLite default). OTLP export to agentevals/OTel backends.
2. **Live dashboard** — FastAPI backend streams spans over WebSocket to a small Vue/React front end: swarm view (agents as dots hitting tools), live metrics, and the **per-agent inspector** ("why did you call X?" reads the agent's reasoning span).
3. **Report generator** — aggregates the run into a `RunReport` model, rendered by the shared **report-renderer** (HTML + terminal, oxblood-editorial). Sections: task-success by persona, **misuse map**, concurrency perf (p50/p95/p99, dropped connections), **cost profile** (per-persona $), chaos-recovery, adversarial findings, and (v0.2) realism score + run-diff.

### 2.8 Grounding / Calibration ⊕ (`FR-PF-06`, `FR-OB-09`)

Responsibility: answer "how do you know these agents are realistic?" — the "Lost in Simulation" mitigation.

- **Record mode:** capture real agent traffic (as trace-format) hitting a target.
- **Fit:** estimate persona params (patience, retry, error/misread rates) so the population's aggregate distribution matches the recorded one.
- **Realism score:** report distance between simulated and recorded distributions per persona.

---

## 3. Key runtime flows (sequence diagrams)

### 3.1 A standard MCPTarget run

```
CLI        SafetyGate    MCPTarget    GoalSynth   PopFactory   Orchestrator   ChaosInj    Agent      Observer
 │  run       │             │            │            │            │            │          │           │
 ├──load yaml─┤             │            │            │            │            │          │           │
 ├──gate?────►│ allowlist/ack check                                                                    │
 │◄──ok───────┤             │            │            │            │            │          │           │
 ├────────────┼──connect───►│            │            │            │            │          │           │
 ├────────────┼──discover──►│            │            │            │            │          │           │
 │◄───────────┼──ToolSet────┤            │            │            │            │          │           │
 ├────────────┼─────────────┼─synthesize►│            │            │            │          │           │
 │◄───────────┼─────────────┼─Goals(labeled)          │            │            │          │           │
 ├────────────┼─────────────┼────────────┼─build(N)──►│            │            │          │           │
 │◄───────────┼─────────────┼────────────┼─Agents─────┤            │            │          │           │
 ├────────────┼─────────────┼────────────┼────────────┼─run(curve)►│            │          │           │
 │            │             │            │            │            ├─spawn wave─┼─────────►│(PLANNING) │
 │            │             │            │            │            │            │  decide  ├──span────►│
 │            │             │            │            │            │◄─invoke────┼──────────┤(ACTING)   │
 │            │             │            │            │            ├─before_invoke►│ pass|fail|delay|  │
 │            │             │            │            │            │            │  rate_limit          │
 │            │◄────────────┼─invoke(if pass)─────────┼────────────┤            │          │           │
 │            │             ├─ToolResult─┼────────────┼───────────►│──result───►│          ├──span────►│
 │            │             │            │            │            │(loop until DONE/FAILED/killed)     │
 │            │             │            │            │            ├─assert_recovery (exactly-once)────►│
 │◄─RunResult─┼─────────────┼────────────┼────────────┼────────────┤            │          │           │
 ├──render report + serve dashboard───────────────────────────────────────────────────────────────►│
```

### 3.2 Chaos: kill mid-flight + recovery assertion

```
Orchestrator     ChaosInjector      Agent(pays)        Target(mockworld)     exactly-once     Observer
    │  step k          │                │                     │                   │              │
    ├─lifecycle(k)────►│ kill?                                                                    │
    │◄──KILL───────────┤                │                     │                   │              │
    ├─terminate───────────────────────►│ (RECOVERING)                                            │
    │  resume policy   │                ├─re-attempt charge──►│                                    │
    │                  │                │                     ├─claim(key)───────►│ committed?     │
    │                  │                │                     │◄─committed────────┤ (skip effect)  │
    │                  │                │                     │  return stored result             │
    ├─assert: side-effect fired exactly once ─────────────────────────────────────────────►│ PASS│
```

If the target/agent double-fires (no exactly-once), the assertion emits a `recovery.violation` finding → the report's chaos section fails.

---

## 4. Data models & schemas (authoritative)

### 4.1 trace-format — the OTel GenAI profile ⊕ (shared primitive; `FR-OB-01`, `NFR-INTEROP-01`)

**Decision:** trace-format is **a profile of the OpenTelemetry GenAI semantic conventions**, not a bespoke schema. A stampede span IS an OTel span; we add a namespaced `swarmproof.*` extension for population/persona/chaos context that generic OTel backends ignore harmlessly. This is binding on mcp-probe, costbomb, and mockworld.

Standard OTel GenAI attributes we populate (unchanged names):
```
gen_ai.operation.name        # "chat" | "execute_tool" | "invoke_agent"
gen_ai.provider.name         # "anthropic" | "openai" | "ollama"
gen_ai.request.model
gen_ai.usage.input_tokens
gen_ai.usage.output_tokens
gen_ai.agent.id / .name / .description / .version
gen_ai.tool.name / .call.id / .type          # child span per tool call
```

`swarmproof.*` extension namespace (our additions):
```yaml
# span attributes (JSON here for readability; emitted as OTel span attrs)
swarmproof.run.id:            "run_2026-07-13T10-02Z_a1b2"
swarmproof.run.seed:          42
swarmproof.persona.name:      "impatient"
swarmproof.persona.pack:      "core@1.0"
swarmproof.agent.temperament: {patience: 2, retry_policy: "aggressive", token_budget: 4000, risk_appetite: 0.7}
swarmproof.goal.id:           "g_refund_4471"
swarmproof.goal.intent.expected_tool: "archive_record"      # the misuse oracle
swarmproof.goal.intent.labeled:        true
swarmproof.decision.reasoning: "user said cancel, delete_record looked closest"  # powers "why did you call X?"
swarmproof.misuse.detected:    true         # realized tool != expected intent
swarmproof.chaos.action:       "rate_limit" # what chaos did to this span, if anything
swarmproof.cost.usd:           0.0034
swarmproof.recovery.exactly_once: true      # populated by exactly-once assertion
```

Span hierarchy (OTel parent/child):
```
run (root)                                                        [service.name=stampede]
└── agent.session                 gen_ai.invoke_agent   AGENT-SIDE
    ├── agent.turn                 gen_ai.chat           AGENT-SIDE  (+ swarmproof.decision.reasoning)
    │   └── tool.call              gen_ai.execute_tool   AGENT-SIDE  span.kind=CLIENT  (+ swarmproof.misuse.*, .chaos.*, .cost.usd)
    │       └── target.handler     gen_ai.execute_tool   TARGET-SIDE span.kind=SERVER [service.name=mockworld.<mock>]
    │           └── (target-internal spans: state mutation, fault decision, latency…)
    └── recovery.assertion         (+ swarmproof.recovery.exactly_once)
```

**Agent-side vs target-side spans ⊕ (the producer contract — binding on mockworld, mcp-probe, costbomb).**
The trace is *shared* across the wire. stampede emits **agent-side** spans (the client's view of a tool call); a target that is trace-aware (mockworld) emits **target-side** spans (the server's view) that nest under the agent's `tool.call` span in the **same `trace_id`**.

| Dimension | Agent-side (stampede emits) | Target-side (mockworld/server emits) |
|---|---|---|
| `span.kind` | `CLIENT` on `execute_tool` | `SERVER` on the handler |
| `service.name` (resource) | `stampede` | `mockworld.<mock>` (e.g. `mockworld.stripe`) |
| `swarmproof.span.side` | `"agent"` | `"target"` |
| Owns attrs | `gen_ai.usage.*`, `swarmproof.misuse/chaos/cost/decision.*` | `swarmproof.fault.*` (the semantic fault it applied), target-internal latency/state |
| `gen_ai.tool.call.id` | sets it | echoes the *same* value (the join key) |

**Trace-context propagation (how the nesting actually happens):** stampede injects **W3C `traceparent`** into every tool invocation so the server can parent its spans correctly:
- **HTTP/SSE transport** → standard `traceparent` / `tracestate` HTTP headers.
- **stdio (MCP)** → injected into the MCP request's **`_meta`** object as `_meta.traceparent` (MCP's forward-compatible metadata channel), since stdio has no headers.

A target that ignores `traceparent` still works — you simply get agent-side spans only (no target-side nesting), which is the correct graceful degradation for non-trace-aware targets (a plain third-party MCP server). Resource attributes carry `service.name` + `service.version`; `swarmproof.run.id` is a **span** attribute (one collector may observe many runs), never a resource attribute.

### 4.2 persona-pack YAML — authoritative schema ⊕ (shared primitive; `FR-PF-05`)

```yaml
apiVersion: swarmproof.dev/persona/v1        # versioned (FR-PF-05)
kind: PersonaPack
metadata:
  name: core
  version: "1.0"
  description: "The six canonical stampede temperaments."
  license: Apache-2.0
personas:
  - name: naive
    extends: null                            # inheritance (FR-PF-05)
    description: "First-time user; trusts tool names literally; under-reads descriptions."
    temperament:
      patience: 5              # turns tolerated before giving up (models the paper's 'impatience' axis)
      retry_policy: gentle     # none | gentle | aggressive
      token_budget: 8000
      risk_appetite: 0.2       # 0..1 — willingness to take destructive actions
      misread_rate: 0.4        # 0..1 — probability of misinterpreting a tool description
      goal_adherence: 0.6      # how tightly it sticks to the stated goal
    prompt_template: |
      You are a non-expert user. You skim tool descriptions and pick what *sounds* right...
  - name: impatient
    extends: naive
    temperament: {patience: 2, retry_policy: aggressive}   # only overrides differ
  - name: expert            # low misread, high adherence, frugal tokens
  - name: frugal            # token-minimizing; short contexts
  - name: adversarial       # risk_appetite: 1.0; loads attack playbooks
    attacks: [injection, denial_of_wallet]                 # → embedded costbomb library
  - name: drunk             # malformed/contradictory goals (paper's 'goal brittleness' axis)
    temperament: {goal_adherence: 0.1, misread_rate: 0.7}
calibration:                                               # ⊕ grounding (FR-PF-06)
  grounded_against: null      # path/id of a recorded-traffic dataset when calibrated
  realism_score: null         # 0..1, filled by the fit step
```

### 4.3 RunReport model (feeds report-renderer)

```
RunReport
├── meta            {run_id, seed, target, population_mix, models, duration, total_usd, safety_posture}
├── success         per-persona task-success rate + pass^k reliability (τ²-bench style)
├── misuse_map      [{expected_tool, realized_tool, confusion_rate, n_labeled}]   # only labeled goals
├── performance     {p50, p95, p99, max_stable_concurrency, dropped_connections, fd_leaks}
├── cost_profile    per-persona {usd_mean, usd_p95, tokens} + the headline spread
├── chaos           {faults_injected, recovery_findings[], exactly_once_violations[]}
├── adversarial     {injection_hits[], denial_of_wallet[], incident_replays[]}
├── realism         {per_persona realism_score}          # v0.2, when grounded
└── diff            {baseline_run_id, regressions[], significant: bool}   # v0.2
```

### 4.4 `stampede.yaml` — see `SPEC.md §2.3`; PRD adds `safety:` and `plan:` blocks ⊕

```yaml
safety:                       # ⊕ FR-TA-05
  allow_targets: ["localhost:*", "127.0.0.1:*"]
  acknowledge_non_production: false     # must be true to hit anything off-allowlist
  evm_require_fork: true                # EVMTarget refuses non-fork RPC unless false + ack
report:
  plan_only: false            # ⊕ `stampede plan` sets this → estimate cost, don't run
```

---

## 5. Tech stack & rationale

| Layer | Choice | Rationale |
|---|---|---|
| Core language | **Python 3.11+** | Matches the agentic ecosystem (MCP SDK, providers, Ray, web3.py all Python-first). 3.11 for `TaskGroup`/`asyncio` ergonomics + `tomllib`. |
| Orchestration | **asyncio** default, **Ray** optional backend | Research: laptops handle low-hundreds of stateful agents on asyncio; Ray's ~1–2ms/request overhead only earns its keep past that (`RESEARCH §2.6`, Ray guidance). Pluggable `Executor` keeps both. |
| Target — MCP | **official MCP SDK** | Correct JSON-RPC + SSE handshake; the specifics k6/Locust miss. |
| Target — EVM | **web3.py + Foundry/Anvil** | Anvil forks any EVM chain in-memory; `web3-ethereum-defi` gives Python Anvil bindings. |
| Live UI | **FastAPI + small Vue/React + WebSocket** | Mirrors MiroFish's proven Python+Vue watchable-sim shape; WebSocket for the live swarm stream. |
| Trace store | **SQLite** default, **Postgres** adapter | Zero-config local default; Postgres for big/shared runs. Spans are OTel; store is an implementation detail behind the Tracer. |
| Telemetry | **OpenTelemetry SDK** (GenAI profile) | Interop with every OTel backend; avoids inventing a schema (`ADR-1`). |
| Model layer | **provider-agnostic** (Anthropic SDK + OpenAI-compatible + Ollama) | Local-friendly bulk agents; frontier only where needed. |
| Report | shared **report-renderer** (HTML + Jinja + terminal via Rich) | Oxblood-editorial styling; one renderer across the portfolio. |
| Packaging | `pip install stampede`; primitives **vendored** now, extract to `agent-reliability-core` at v0.2 | Avoid premature coupling while APIs churn (`ADR-4`). |

---

## 6. Integration points (portfolio interlock)

| Sibling | Interface stampede exposes/consumes | Direction |
|---|---|---|
| **trace-format** | stampede *defines* the OTel GenAI profile; publishes the `swarmproof.*` attr registry | stampede → all |
| **persona-pack** | stampede *defines* the `swarmproof.dev/persona/v1` schema; costbomb consumes `adversarial:economic` | stampede → costbomb |
| **report-renderer** | stampede *defines* the `RunReport`→HTML/terminal renderer + theme tokens | stampede → mcp-probe, costbomb |
| **concurrency-core** | stampede *defines* the `Scheduler`/`Executor` protocol; mcp-probe's load engine imports it | stampede → mcp-probe |
| **mockworld** | consumes a mockworld world as `mockworldTarget` (an MCPTarget) | mockworld → stampede |
| **costbomb** | embeds costbomb's attack library as a cohort; later imports the extracted CLI | bidirectional |
| **exactly-once** | calls `Store.claim/commit` in the recovery assertion | exactly-once → stampede |
| **agent-postmortems** | reads incident YAML (its schema) → chaos scenarios | postmortems → stampede |
| **mcp-probe** | `stampede --from-probe` reads mcp-probe's JSON target descriptor | mcp-probe → stampede |
| **Cairn** | dogfoods Cairn's six-state model in the orchestrator; case study #1 | bidirectional |

---

## 7. Scalability, security, failure modes

### 7.1 Scalability
- **asyncio ceiling:** target ≥200 stateful agents/laptop (NFR-PERF-01); the bottleneck is LLM I/O, not CPU — so async concurrency + connection pooling to the target dominate.
- **Ray backend (v0.2):** stateful agents as Ray Actors, tool calls as tasks; crosses the 2,000+ agent line. Same `Scheduler` protocol.
- **Trace volume:** high-cardinality spans → batch writes to SQLite (WAL mode); Postgres + partitioning for big runs; dashboard reads a rolling window, not the full store.
- **Cost as a scaling limit:** the real ceiling is $, not CPU — hence bulk agents on local Ollama and the `budget_usd` hard-stop.

### 7.2 Security & safety
- **Target Safety Gate** (§2.2) is the primary control: adversarial + chaos cannot hit unguarded prod/mainnet.
- **Secret redaction** (NFR-SEC-02): API keys/RPC URLs stripped from spans before store/export.
- **Adversarial payloads are test-scoped** (NFR-SEC-03): documented as sandbox payloads; no framing or capability aimed at exploiting third-party production systems. This is a defensive/authorized-testing tool.
- **EVM funds are test-only:** funded test wallets on a fork; the fork guard prevents real-value transactions.

### 7.3 Failure modes & mitigations
| Failure | Mitigation |
|---|---|
| An agent crashes/hangs | Isolated per-agent tasks; timeout + cancel; never aborts the run (NFR-REL-01); partial report always valid. |
| Target dies mid-run | `health()` checks; run marks target-down, reports what completed. |
| Budget exceeded | Hard pre-spend stop (FR-OR-07); one in-flight turn max overrun. |
| Non-determinism confuses CI | Seeded runs + statistical diff (FR-OB-06); `--dry-run` fully deterministic. |
| Agents corrupt each other's target state | Isolation policy (FR-TA-06); `reset()` between waves; else documented confounding. |
| Simulated agents aren't realistic | Grounding/calibration + realism score (§2.8); model mixing; honest reporting of realism. |
| trace-format drift across siblings | Single OTel-profile spec + a shared validator in CI (see TEST-PLAN). |

---

## 8. ADRs (key decisions, alternatives considered)

**ADR-1 — trace-format is an OTel GenAI profile, not a bespoke schema.**
*Alternatives:* (a) bespoke JSON schema; (b) LangSmith/proprietary format; (c) OTel GenAI profile. *Decision:* (c). *Why:* 2026 convergence on OTel GenAI (Datadog/Honeycomb/New Relic/LangChain); free interop; avoids fragmenting the portfolio. *Cost:* we inherit OTel verbosity and must track SIG changes. *Consequence:* binding on all siblings.

**ADR-2 — asyncio-default with a pluggable Ray backend, not Ray-first.**
*Alternatives:* Ray-first; asyncio-only; multiprocessing. *Decision:* asyncio default + `Executor` protocol for Ray. *Why:* one-command-on-a-laptop is the adoption wedge; Ray overhead unjustified at demo scale; keeps the door open for scale. *Cost:* two executor code paths to test.

**ADR-3 — Personas as data (versioned YAML), not code subclasses.**
*Alternatives:* Python subclasses per persona; prompt-only personas. *Decision:* versioned YAML with `extends` + typed temperament params. *Why:* enables the community registry/flywheel, sharing with costbomb, grounding/calibration, and diffing; separates temperament from model. *Cost:* a schema to version and validate.

**ADR-4 — Vendor shared primitives now; extract `agent-reliability-core` at v0.2.**
*Alternatives:* shared package from day one; permanent vendoring. *Decision:* vendor now, extract when shapes stabilize (trace-format first). *Why:* avoids premature coupling while APIs churn across seven repos. *Cost:* temporary duplication; a disciplined extraction milestone.

**ADR-5 — Intent-labeled goals as the misuse oracle. ⊕**
*Alternatives:* infer misuse post-hoc via an LLM judge; no oracle (report raw tool distributions). *Decision:* attach an expected-tool/effect label at goal-synthesis time; misuse = realized ≠ expected on labeled goals only. *Why:* makes the flagship number falsifiable and cheap to compute; LLM-judge post-hoc is costly and circular. *Cost:* unlabeled goals are excluded from the misuse rate (reported transparently).

**ADR-6 — Safety Gate is mandatory and on by default. ⊕**
*Alternatives:* trust the user; warn-only. *Decision:* hard gate (allowlist + explicit ack + EVM fork check). *Why:* an adversarial swarm is a foot-gun; a *trust* brand cannot ship one that silently hits prod/mainnet. *Cost:* one extra config step for off-localhost targets (acceptable friction).
