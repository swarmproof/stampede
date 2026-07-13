# stampede — TEST PLAN

*How we prove the wind tunnel works — and that its numbers are trustworthy.*

Status: v1.1 design pass · Date: 2026-07-13
Companions: `PRD.md` (REQ-IDs + acceptance), `ARCHITECTURE.md` (components), `DELIVERY-PLAN.md` (DoD).
Notation: **⊕** = beyond original `SPEC.md`.

Testing a tool whose *subject matter is non-determinism* is the central challenge: stampede runs stochastic LLM agents, so its own tests must separate **the harness's determinism** (which must be rock-solid) from **the agents' stochasticity** (which must be characterized, seeded, and diffed statistically). This plan is organized around that split.

---

## 1. Test strategy & pyramid

```
                 ▲  fewer, slower, higher-value
     ┌───────────────────────────┐
     │   E2E (real swarm runs)    │   swarm vs mockworld/Cairn → assert the report   (§4)
     ├───────────────────────────┤
     │   Integration              │   real MCP/HTTP/EVM target + real scheduler + chaos (§3)
     ├───────────────────────────┤
     │   Component / contract     │   each Protocol against a fake counterpart          (§3)
     ├───────────────────────────┤
     │   Unit (the bulk)          │   pure logic: key derivation, curves, cost math,    (§2)
     │                            │   misuse detection, schema validators — ZERO LLM
     └───────────────────────────┘
                 ▼  many, fast, deterministic
```

**Golden rule:** everything below the E2E tier is **zero-LLM and deterministic**. LLMs appear only in a small, seeded, opt-in E2E band and in nightly (not per-commit) jobs. The `--dry-run` heuristic-agent path (`FR-CLI-04`) is what makes most of the pyramid testable without spend.

---

## 2. Unit scope (zero-LLM, deterministic, the bulk of coverage)

| Area | What's tested | Key cases |
|---|---|---|
| trace-format | OTel-profile validator; span hierarchy; `swarmproof.*` attrs | valid/invalid spans; secret-redaction (`NFR-SEC-02`); round-trips through OTLP export |
| persona-pack | schema validation; `extends` inheritance resolution | override-merge correctness; version mismatch rejected; malformed pack errors clearly |
| Goal Synthesis (template mode) | deterministic grammar generator; intent labeling | same seed → identical goals; labeled vs unlabeled flagging (`FR-GS-03/04`) |
| Concurrency curves | ramp/spike/steady schedule math over SimClock | peak/hold honored; wave boundaries; virtual-clock compression |
| Six-state machine | legal transitions; kill from any state → RECOVERING | illegal transitions rejected; terminal states sticky |
| Chaos policy | fault selection given config + seed | probabilities honored over N draws; rate_limit fires; `pass` when no chaos |
| Recovery/exactly-once glue | claim/commit/skip logic against a fake Store | double-fire detected; in-flight-on-crash quarantined |
| Cost meter | tokens×price math; per-persona aggregation | price-table updates; budget hard-stop arithmetic (`NFR-COST-01`) |
| Misuse detection | realized-tool vs intent-label comparison (`ADR-5`) | detects delete-vs-archive; excludes unlabeled from denominator |
| Safety Gate | allowlist match; ack requirement; EVM fork check | off-allowlist blocked; fork marker missing → refuse (`FR-TA-05`) |
| `stampede plan` | cost estimate formula | estimate within model of population×prices×turns |

Target: **≥ 85% line coverage on core logic modules** (harness, not UI).

---

## 3. Integration scope (real components, fake or local targets)

| Integration | Setup | Assertions |
|---|---|---|
| MCPTarget ↔ real MCP server | Spawn a tiny local MCP server (stdio + HTTP/SSE) | `initialize` handshake; discover returns declared tools; invoke round-trips; SSE stays alive under N connections; `reset()` clears state |
| HTTPTarget ↔ local OpenAPI app | FastAPI sample with an OpenAPI spec | spec→ToolSet mapping; 4xx/5xx surfaced to agent as tool errors |
| Orchestrator ↔ AsyncioExecutor | dry-run heuristic agents | 200 agents complete without run-abort (`NFR-REL-01`); graceful stop on SIGINT flushes a valid report |
| Chaos ↔ Target invoke wrapper | inject each fault type | latency delays observed; malformed output reaches agent; rate_limit throttles; kill terminates the agent task cleanly |
| Recovery ↔ exactly-once (real lib) | mockworld payments target; kill mid-charge; resume | side-effect fires exactly once; `swarmproof.recovery.exactly_once=true` in trace |
| Observer ↔ SQLite store | full dry-run | spans persisted (WAL); dashboard reads a rolling window; report aggregates match raw spans |
| trace-format ↔ OTel backend | OTLP export to a local collector | spans import unmodified; `gen_ai.*` recognized (`NFR-INTEROP-01`) |
| EVMTarget ↔ Anvil fork (v0.2) | `anvil --fork-url <rpc>` | fork detected; non-fork RPC refused; a test-wallet tx lands; balance changes |

---

## 4. Concrete E2E scenarios (Given/When/Then)

These are the acceptance-defining flows. Each runs a **real (small, seeded) swarm** against a **local target** and asserts the **report**.

### 4.1 Flagship: swarm vs mockworld → misuse map (the launch demo)
```
GIVEN  a mockworld `crm` world exposing `delete_record` and `archive_record` with slightly ambiguous descriptions
  AND  stampede.yaml: size=50, mix {naive:0.6, expert:0.3, adversarial:0.1}, models=[ollama:llama3], seed=42
  AND  goals auto-generated with intent labels (some goals mean "archive")
WHEN   `stampede run --target mock:crm --live` completes
THEN   a report is produced with:
  AND  a misuse map showing a non-zero confusion_rate for archive→delete on labeled goals
  AND  a per-persona cost_profile (naive spread > expert)
  AND  task-success rates per persona (expert > naive)
  AND  the live dashboard showed agents as dots and the inspector explained one "wrong" call
```

### 4.2 Chaos + recovery + exactly-once
```
GIVEN  a mockworld `payments` target and stampede.yaml with chaos: {kill_agents_at:[random], inject:[tool_timeout, rate_limit], assert_recovery:true}
WHEN   the run kills agents mid-charge and rate-limits some tool calls
THEN   the chaos section reports faults injected and recovery findings
  AND  every completed charge fired exactly once (0 exactly_once_violations)
  AND  a deliberately-broken variant (exactly-once disabled) FAILS the assertion (negative test)
```

### 4.3 Deterministic CI smoke (`--dry-run`)
```
GIVEN  any target descriptor and `--dry-run` (zero LLM), seed=7
WHEN   `stampede run --dry-run` runs twice
THEN   both runs finish < 30s (50 agents)
  AND  the two RunReport JSON outputs are byte-identical (NFR-REPRO-01)
  AND  exit code gates on `--fail-under`
```

### 4.4 Safety gate blocks production
```
GIVEN  stampede.yaml target = https://api.acme-prod.com and adversarial cohort, acknowledge_non_production=false
WHEN   `stampede run` starts
THEN   it refuses before connecting, printing which flag is required
  AND  no requests reach the target (verified by a spy)
```

### 4.5 Cost cap (denial-of-wallet on ourselves)
```
GIVEN  budget_usd=0.50 and a population that would cost ~$5 on a paid model
WHEN   the run proceeds
THEN   it hard-stops at/near $0.50 (≤ one in-flight turn overrun) and produces a partial-but-valid report
```

### 4.6 Run-diffing separates signal from noise (v0.2)
```
GIVEN  a baseline run and a candidate run of the SAME config+seed
WHEN   the candidate's target has a genuinely worsened tool description
THEN   `stampede diff` flags a SIGNIFICANT misuse regression (effect size + CI)
GIVEN  two runs differing only by RNG reseed on a stable target
THEN   `stampede diff` reports NO significant regression (noise band) — no false alarm
```

### 4.7 EVM wallet-swarm on a fork (v0.2)
```
GIVEN  an Anvil fork of a lending protocol and a mix of borrower/liquidator/adversarial wallet-agents
WHEN   a price-shock scenario runs
THEN   the report shows aggregate swarm behavior (e.g., liquidation activity) and any griefing findings
  AND  EVMTarget refused to run had the RPC been non-fork mainnet
```

### 4.8 Grounding realism score (v0.2)
```
GIVEN  a recorded-traffic dataset for a target and an ungrounded persona
WHEN   grounding calibrates the persona and the swarm runs
THEN   the report shows a realism_score, higher for the calibrated persona than the default
```

---

## 5. Test data & fixtures

- **Local MCP server** (`tests/fixtures/echo_mcp/`): minimal server with 2 intentionally-confusable tools — the misuse-map fixture.
- **mockworld worlds**: `crm` (delete/archive), `payments` (exactly-once), `exchange` (EVM-ish) — reused as demo + test targets.
- **Recorded-cassette LLM responses** ⊕: VCR-style cassettes so "LLM" E2E tests replay canned completions deterministically in CI; live-model runs are nightly/opt-in only.
- **Golden RunReport JSONs**: committed baselines for `--dry-run` scenarios (the snapshot targets).
- **Seed corpus**: fixed seeds (42, 7) documented so runs are reproducible across machines.
- **Chaos config fixtures**: one per fault type + a "kitchen-sink" config.
- **Anvil fork snapshot** (v0.2): a pinned block for reproducible EVM tests.

---

## 6. CI gates

| Gate | Trigger | Contents | Blocking? |
|---|---|---|---|
| **lint + type** | every PR | ruff/mypy | Yes |
| **unit** | every PR | §2, zero-LLM | Yes |
| **integration** | every PR | §3, local targets, no paid LLM | Yes |
| **dry-run smoke** ⊕ | every PR | scenario 4.3 (deterministic, <30s) + report-schema validation | Yes |
| **trace-format profile check** ⊕ | every PR | validate emitted spans against the OTel-profile validator | Yes |
| **cassette E2E** | every PR | scenarios 4.1/4.2/4.4/4.5 with recorded LLM cassettes | Yes |
| **live-model E2E** | nightly / manual | scenarios 4.1/4.2 with a real small model (Ollama in CI, or a tiny paid budget) | No (report-only) |
| **coverage** | every PR | ≥85% on core modules | Yes |
| **portfolio interop** ⊕ | on primitive change | siblings' consumers still parse trace-format/persona-pack | Yes (once extracted) |

The paid-LLM path is never on the blocking per-commit gate — cost and flakiness make it unfit for a required check. This is why the deterministic dry-run + cassette layers carry the CI weight.

---

## 7. Performance / load testing approach

stampede is itself a load generator, so we test *its own* scaling separately from the target's:
- **Harness scaling** (`NFR-PERF-01`): dry-run 200 agents on a 16GB laptop profile; assert completion + memory ceiling; Ray backend variant hits ≥2,000 (v0.2).
- **Dashboard latency** (`NFR-PERF-02`): measure agent-action→visible < 500ms p95 under a 200-agent stream.
- **Trace-write throughput**: sustained span-write rate to SQLite WAL without becoming the bottleneck.
- **Target-perf metrics correctness**: point stampede at a target with *known injected* latency/dropped-connection behavior and assert the report's p50/p95/p99 and dropped-connection counts recover the injected ground truth (meta-validation — testing that our measurement is accurate).

---

## 8. Handling non-determinism (the core methodology)

| Technique | Where | Guarantee |
|---|---|---|
| **Seeded harness RNG** | goal assignment, persona sampling, chaos schedule | same seed → same *harness* decisions |
| **`--dry-run` heuristic agents** | CI bulk | fully deterministic, byte-identical reports (`NFR-REPRO-01`) |
| **LLM cassettes (VCR)** | cassette E2E | canned completions → deterministic "LLM" runs in CI |
| **Fixed model+temp+seed** | live-model runs | aggregate metrics within a documented **noise band** (`NFR-REPRO-02`) |
| **Statistical run-diffing** | `stampede diff` | regression flagged only on significant shift (effect size + CI), never on RNG noise (`FR-OB-06`) |
| **`pass^k` reliability metric** | report | per-persona reliability over k repeats (τ²-bench-style), not a single pass/fail |
| **Noise-band characterization** | nightly | track metric variance over repeated seeded live runs; publish the band so users know what "changed" means |

The user-facing promise: *the harness is deterministic; the agents are stochastic but characterized; a "regression" is a statistically significant shift, not any delta.*

---

## 9. Acceptance criteria per feature tier

**MUST (v0.1) — a feature is accepted when:**
- Its REQ-ID's unit + integration tests pass, AND
- It appears correctly in at least one E2E scenario's asserted report, AND
- The relevant CI gate (dry-run / cassette / trace-profile) is green.
- Specifically: misuse map (4.1), chaos+exactly-once (4.2), deterministic dry-run (4.3), safety gate (4.4), cost cap (4.5) all pass.

**SHOULD (v0.2) — accepted when:**
- EVM fork scenario (4.7) passes incl. fork-guard; run-diffing (4.6) distinguishes signal from noise on seeded fixtures; grounding (4.8) shows a differentiated realism score; costbomb standalone reproduces the embedded-cohort findings; badge/JSON validate; extracted primitives pass the portfolio-interop gate.

**COULD (v0.3) — accepted when:**
- mockworld world runs via one flag; a framework adapter drives real agents through a full E2E; hosted report link renders the same RunReport.

---

## 10. Out of scope for testing (documented non-guarantees)
- Absolute realism of personas vs *all* real-world agents (we test *relative* realism via grounding scores, not ground truth).
- Third-party target correctness (we test *our measurement* of it, not the target's own bugs beyond what agents surface).
- Distributed-consensus correctness of exactly-once beyond its documented single-writer boundary (that's exactly-once's own test suite).
- Real-mainnet behavior (EVM tests run against forks only, by design and by safety gate).
