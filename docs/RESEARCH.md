# stampede — RESEARCH

*The wind tunnel for the agent economy — problem, landscape, prior art, and where the white space actually is.*

Author: Systems/architecture design pass · Date: 2026-07-13 · Status: living doc

> Reading order: this doc sharpens the thesis and maps the 2026 field. `PRD.md` turns it into requirements, `ARCHITECTURE.md` into a buildable system, `DELIVERY-PLAN.md` into milestones, `TEST-PLAN.md` into acceptance gates.
>
> Notation: **⊕ Beyond original spec** marks a claim, gap, or feature this research adds on top of `SPEC.md`.

---

## 1. The sharpened problem & thesis

### 1.1 The one-sentence problem

Software is now **consumed by agents, not humans** — MCP servers, tool APIs, and onchain protocols are all built to be driven by LLM agents — yet builders have **no way, before shipping, to observe how a realistic diversity of agents will behave against the thing they built.**

### 1.2 The three failed substitutes (and why each fails)

Builders today reach for one of three tools, and all three answer the wrong question:

| What they reach for | What it actually measures | Why it misses the real risk |
|---|---|---|
| **Manual test with one agent, one happy path** | "Does it work when everything goes right?" | Agents are a *distribution*, not a point. The failures live in the tail — the misread description, the wrong tool, the retry storm. |
| **A load tester (k6, Locust, JMeter)** | Requests/sec, p99 latency of a stateless endpoint | Load tools "do not understand multi-turn conversations, do not score response quality, and do not connect into the eval pipeline" ([premai, 2026](https://blog.premai.io/load-testing-llms-tools-metrics-realistic-traffic-simulation-2026/)). They fire *uniform* traffic; agents generate *heterogeneous behavior*. |
| **An agent-eval / user-sim framework (LangWatch Scenario, IntellAgent, tau²-bench)** | "Is *my agent* good?" | These point the camera at the **agent**. The target-under-test (the MCP server, API, protocol) is held fixed and assumed correct. Nobody points the camera at the **target** and asks "what will a herd of imperfect agents do to *you*?" |

### 1.3 The thesis, in one line

> **Agents don't generate traffic — they generate *behavior*.** stampede is the first tool that manufactures a *population* of realistic and adversarial agents and turns it loose on **your** system, then reports where agents succeed, get confused, and break you.

The unit of the product is not the request and not the agent — it is the **population run against a target**, and the deliverable is not a latency chart, it is the **Agent Readiness Report** (misuse map + cost profile + chaos-recovery + adversarial findings).

### 1.4 Why now (2026 evidence)

| Signal | 2026 figure | Source |
|---|---|---|
| MCP monthly SDK downloads | **97M+** (Python + TS) | [Anthropic ecosystem update, Dec 2025](https://www.digitalapplied.com/blog/mcp-97-million-downloads-model-context-protocol-mainstream) |
| Active public MCP servers | **10,000+** (registries index 13k–20k) | [Anthropic; QCode 2026](https://www.qcode.cc/mcp-servers-ecosystem-2026) |
| Orgs with MCP in limited/broad production | **41%** | [Stacklok 2026 software report](https://workos.com/blog/everything-your-team-needs-to-know-about-mcp-in-2026) |
| MCP as the interop standard | Adopted across ChatGPT, Cursor, Gemini, Copilot, VS Code | [modelcontextprotocol.io roadmap 2026](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) |
| Frontier LLM success on multi-step MCP tasks | **< 60%** | [LiveMCP-101, arXiv 2508.15760](https://arxiv.org/abs/2508.15760) |

> ⊕ **Spec correction:** the SPEC quotes "177,000+ APIs; FastMCP 1M+ downloads/day." The defensible, current framing is **10k+ active public servers, 97M+ monthly SDK downloads, 41% of orgs in production** — a *set of measured public signals*, not one headline number. Use these.

The category being *built for agents* is exploding; the tooling to *pre-flight-test those systems against agents* is stuck at "write a client loop with the MCP SDK and fire it in a `for` loop" ([Fastio, 2026](https://fast.io/resources/mcp-server-load-testing/)). That gap is the opportunity.

---

## 2. The 2026 competitive & adjacent landscape

The field splits into six lanes. stampede sits in a lane of its own (Lane F), bordered by all five others. **Distinguish existing from white space** is the whole point of this section.

### 2.1 Lane A — Agent-eval & user-simulation frameworks (point at the *agent*)

| Tool | What it does | What it lacks for stampede's job |
|---|---|---|
| **LangWatch Scenario** ([scenario.langwatch.ai](https://scenario.langwatch.ai/), released **2026-01-15**, OSS on PyPI/npm) | Simulates *users* in multi-turn conversations to test *your* agent; LLM user-simulator + judge agent + result aggregation; adapters for LangGraph/CrewAI/Pydantic AI. Runs "thousands of synthetic conversations." | **Inverted target.** It simulates the human on the *other* side of *your* agent. stampede simulates the *agents on the other side of your server*. Scenario assumes the tools/target are correct; stampede exists to prove they aren't. Closest adjacent — and the clearest positioning contrast. |
| **IntellAgent** ([arXiv](https://arxiv.org/html/2503.16416v2)) | Takes DB schema + policy docs → builds a policy graph → generates events → simulates dialogue between tested agent and a user-agent → critique agent scores. | Again the tested unit is *the agent*, not the server it calls. No population heterogeneity model, no misuse map for the *toolset*, no chaos/cost profile of the *target*. |
| **agentevals** (LangChain, 2025) | Trajectory evaluation of an agent's steps. | A scoring library for *one* agent's trace. stampede *integrates* this (exports traces to it) rather than competing. |
| **tau-bench / τ²-bench** | Dual-control benchmark: an LLM plays the user, agent completes tasks under written policy; `pass^k` reliability metric over repeated trials; retail/airline/telecom domains. | A fixed *benchmark* of a few domains, not a tool you point at *your* system. Its `pass^k` idea is worth borrowing for our reliability metric (see §7). |

**Takeaway:** Lane A is crowded and well-funded, but every entrant points at the agent. **stampede's inversion — target-as-subject — is unoccupied.**

### 2.2 Lane B — MCP-specific agent benchmarks (test the *model's* tool-use)

| Tool | Scale | Finding relevant to us |
|---|---|---|
| **LiveMCP-101** ([arXiv 2508.15760](https://arxiv.org/abs/2508.15760)) | 101 tasks, 41 servers, 260 tools, avg 5.4 tool steps | Frontier models **< 60%** success; **7 failure modes** across planning/parameterization/output-handling — a ready-made *misuse taxonomy* for our report. |
| **LiveMCPBench** ([arXiv 2508.01780](https://arxiv.org/html/2508.01780)) | "Ocean of MCP tools" | Tool-selection under large tool spaces is where agents drown — validates the misuse-map thesis. |
| **MCP-Bench** ([arXiv 2508.20453](https://arxiv.org/pdf/2508.20453)) | 28 live servers, 250 tools, cross-domain | Complementary-tool orchestration is the hard part. |
| **MCPAgentBench** ([arXiv 2512.24565](https://arxiv.org/pdf/2512.24565)) | Real-world MCP tool-use tasks | Confirms benchmark momentum through late 2025. |

**Takeaway:** These are *leaderboards for models*, fixed corpora built by researchers. They are **not** tools a builder points at *their own* server. They give us (a) a validated failure taxonomy to align our misuse map with, and (b) academic legitimacy to cite. They are not competitors — they're a citation base and a source of chaos scenarios.

### 2.3 Lane C — Load / performance testing (fire *uniform* traffic)

| Tool | Why it fails for agents (2026 sources) |
|---|---|
| **k6** | "Treats each request as a unit… no native understanding of streaming"; measures request→final-byte, "tells you total generation time but nothing about the shape of the user experience." ([TianPan, 2026](https://tianpan.co/blog/2026-03-19-load-testing-llm-applications)) |
| **Locust** | Python **GIL** contention: token-level measurement (tokenization/byte-stream analysis) "competes with the request generation process." ([TianPan, 2026](https://tianpan.co/blog/2026-03-19-load-testing-llm-applications)) The Microsoft/Azure guide still recommends hand-rolling a Locust MCP harness ([MS Community Hub](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/load-testing-hosted-mcp-servers-with-locust-and-azure-load-testing/4522691)) — i.e., DIY is the state of the art. |
| **JMeter / Gatling** | Same class: "generic HTTP load tools drive concurrency well but do not understand multi-turn conversations, do not score response quality, do not connect into the eval pipeline" ([premai](https://blog.premai.io/load-testing-llms-tools-metrics-realistic-traffic-simulation-2026/)). |

**Takeaway:** These prove the *negative space*. stampede must speak MCP/JSON-RPC/SSE natively (like the DIY harnesses), but the differentiator is **behavior, not RPS** — never lead a demo with throughput.

### 2.4 Lane D — Chaos engineering for agents (nascent, validates the Chaos Injector)

| Tool / work | Relevance |
|---|---|
| **ReliabilityBench** ([arXiv 2601.06112](https://arxiv.org/pdf/2601.06112)) | "First systematic application of chaos engineering principles to LLM agent evaluation"; configurable fault profiles. **Key number: rate-limiting is the single largest reliability impact (2.5% degradation below baseline), compounding across multi-step tasks.** → Our Chaos Injector's fault library must include `rate_limit` as a first-class, not an afterthought. |
| **Gremlin, Agent SRE, Cordum, Fastio playbooks** ([Cordum 2026](https://cordum.io/blog/ai-agent-chaos-engineering-playbook)) | Establish that agent chaos ≠ infra chaos: must test *governance paths* (policy-decision-point unreachable, result-queue replay, output-scanner spikes) and failures that "look like success." → informs our fault taxonomy and the "assert recovery" contract. |
| **Microsoft "SRE for autonomous agents"** ([MS Community Hub](https://techcommunity.microsoft.com/blog/linuxandopensourceblog/applying-site-reliability-engineering-to-autonomous-ai-agents/4521357)) | SLO/error-budget framing for agents — vocabulary for our report. |

**Takeaway:** Chaos-for-agents is being *defined* in 2026 but as **benchmarks and playbooks, not as an injectable runtime you drive against your own target.** stampede's Chaos Injector is a differentiated, first-class module here; ReliabilityBench is the academic anchor to cite and align taxonomy with.

### 2.5 Lane E — Society simulation (the *viral product pattern* precedent)

| Precedent | What it proves |
|---|---|
| **Stanford Generative Agents / Smallville** | The cognitive-architecture pattern (memory stream + reflection) that makes agent populations *believable*. |
| **AgentSociety** ([arXiv 2502.08691](https://arxiv.org/abs/2502.08691)) | **10k+ agents, 5M interactions** — large-scale LLM-agent society is tractable and studied. |
| **Altera "Project Sid"** | 1000s of agents in Minecraft → emergent role specialization, norms — proves emergent-behavior-as-spectacle. |
| **Emergence World** ([arXiv 2606.08367](https://arxiv.org/pdf/2606.08367)) | 15-day continuous multi-agent runs — long-horizon is feasible. |
| **MiroFish** (SPEC's 67k-star precedent) | *Society-simulation-as-a-watchable-product* spreads virally when it's one-command and watchable. |

**Takeaway:** This lane proves the **"watchable world" demo mechanic** works and the **Python+Vue live-dashboard shape** is the right one. stampede points that spectacle at a developer's own system — more useful and more repeatable than predicting the news. This is the emotional hook, not the technical core.

### 2.6 Lane F — DeFi agent-based simulation (the premium play, proven but *closed*)

| Tool | Relevance |
|---|---|
| **Gauntlet** ([overview](https://medium.com/@gwrx2005/gauntlet-simulation-based-risk-modeling-and-quantitative-research-for-defi-fb736e4392d2)) | Loads real (or forked) smart contracts, **integrates the EVM**, runs agent populations (lenders, borrowers, liquidators, arbitrageurs, oracles) to stress-test protocol parameters under adverse markets. **This is exactly the EVMTarget vision — and it's a closed, consulting-gated platform.** |
| **Anvil / Foundry** ([getfoundry.sh/anvil](https://www.getfoundry.sh/anvil)) | Fast in-memory node, **forks any EVM chain** — the substrate for EVMTarget. `web3-ethereum-defi` provides Python Anvil bindings ([readthedocs](https://web3-ethereum-defi.readthedocs.io/api/provider/_autosummary_provider/eth_defi.provider.anvil.html)). |

**Takeaway:** Gauntlet **validates the premium EVMTarget market and proves it's lucrative — and it's closed-source and B2B-services-shaped.** stampede's v0.2 EVMTarget is **"open-source Gauntlet-for-anyone"**: point a swarm of wallet-holding agents at a mainnet fork of *your* protocol. This is the brand-defining, consulting-adjacent use. Do not overbuild it in v0.1 — but the positioning ("open Gauntlet") is a genuine wedge.

---

## 3. The observability standard we must adopt (not invent)

⊕ **This is the single most important cross-project research finding.**

The industry has **converged on OpenTelemetry GenAI Semantic Conventions** as the telemetry layer for agents. The GenAI SIG (formed April 2024) now covers LLM calls, agent invocations, tool executions, MCP tool calling, and quality evaluation ([OTel semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)). Datadog, Honeycomb, New Relic support it natively; LangChain, CrewAI, AutoGen emit it ([Datadog](https://www.datadoghq.com/blog/llm-otel-semantic-convention/), [Zylos](https://zylos.ai/research/2026-02-28-opentelemetry-ai-agent-observability)).

Canonical attributes we must speak:

```
gen_ai.operation.name        gen_ai.provider.name       gen_ai.request.model
gen_ai.usage.input_tokens    gen_ai.usage.output_tokens
gen_ai.agent.id / .name / .description / .version
gen_ai.tool.name / .call.id / .type        (child span per tool call)
```

**Decision (binding on the whole portfolio):** the shared **trace-format** primitive is **not a bespoke schema — it is an OTel GenAI *profile*** (a superset that adds a small `swarmproof.*` extension namespace for population/persona/chaos context). This means stampede traces drop straight into any OTel backend, and mcp-probe / costbomb / mockworld interoperate for free. See `ARCHITECTURE.md §4.1`. Also relevant: "Reasoning Provenance for Autonomous AI Agents" ([arXiv 2603.21692](https://arxiv.org/pdf/2603.21692)) argues for structured behavioral analytics *beyond* raw execution traces — which is exactly what the misuse map and per-agent "why did you call X?" inspector provide.

---

## 4. Prior art & academic references (citation base)

| Ref | Use in stampede |
|---|---|
| Stanford **Generative Agents** (Park et al.) | Cognitive architecture (memory + reflection) for believable personas. |
| **AgentSociety** (arXiv 2502.08691) | Precedent for large-scale LLM-agent populations; scale feasibility. |
| **LiveMCP-101** (arXiv 2508.15760) | 7-mode failure taxonomy → misuse-map categories. |
| **ReliabilityBench** (arXiv 2601.06112) | Chaos fault profiles; rate-limit primacy. |
| **"Lost in Simulation"** (arXiv 2601.17087) | The validity critique — see §6.1. Directly shapes the persona design and a new grounding subsystem. |
| **τ²-bench** | `pass^k` reliability metric → our per-persona reliability score. |
| **OTel GenAI semconv** | Authoritative trace schema. |
| **Survey on Evaluation of LLM-based Agents** (arXiv 2503.16416) | Field map; positions stampede vs eval frameworks. |
| **"Static Sandboxes Are Inadequate"** (arXiv 2510.13982) | Argues sims need open-ended co-evolution → supports emergent-swarm framing over scripted flows. |
| **AdaptOrch / Ray agent architecture** | Orchestration scaling guidance for concurrency-core (§ARCH). |

---

## 5. Users & jobs-to-be-done (expanded)

The SPEC names four. This expands the set and sharpens each JTBD into a *trigger → job → success* statement.

| # | Persona | Trigger | Job (hire stampede to…) | "Done" looks like |
|---|---|---|---|---|
| U1 | **MCP server / tool-API builder** *(primary, hottest)* | About to publish a server / merged a tool-description change | "Show me how 500 different agents use my tools and where my descriptions are ambiguous." | A misuse map with a confusion-rate per tool pair; a PR that fixes 3 descriptions and the confusion drops. |
| U2 | **Agent-platform / framework team** | Every release / CI run | "Regression-test our orchestration against a standard swarm; fail the build if reliability drops." | `stampede.yaml` in CI; a seeded run-diff gate. |
| U3 | **Protocol / DeFi engineer** *(premium)* | Pre-mainnet, param change, audit | "Simulate 1000 wallet-holding agents against a mainnet fork of my protocol." | An EVMTarget run showing liquidation cascades / griefing / MEV-ish behavior before real money does. |
| U4 | **AI researcher** | Writing a multi-agent behavior paper | "A reproducible, seeded harness for population experiments." | A citable, deterministic run + exported traces. |
| U5 ⊕ | **Third-party MCP adopter / procurement** | Evaluating a server before letting agents use it | "Before I trust this vendor's server, show me how my agents will misuse it." | A readiness report on someone *else's* server (the `--from-probe` handoff). |
| U6 ⊕ | **SRE / platform reliability owner** | Pre-incident hardening / game day | "Run a chaos game-day: kill agents mid-flight, fail tools, prove recovery + exactly-once." | A chaos-recovery section with pass/fail on state survival and side-effect uniqueness. |
| U7 ⊕ | **Security / red-team engineer** | Threat modeling an agent surface | "Turn the adversarial cohort loose: injection, denial-of-wallet, tool-poisoning replay." | An adversarial-findings section mapped to OWASP-MCP + agent-postmortems incidents. |
| U8 ⊕ | **DevRel / vendor demoing agent-readiness** | Marketing an agent-ready product | "A screenshotable Agent Readiness Report / badge to publish." | A shareable report + `Agent Ready` badge. |

---

## 6. Gap analysis

Two kinds of gaps: **(A) gaps in the field** (opportunities stampede fills) and **(B) gaps/risks in the current SPEC** (things the design must add or de-risk).

### 6.1 The one risk that could sink the thesis — and why stampede is *its own* mitigation

**"Lost in Simulation: LLM-Simulated Users are Unreliable Proxies for Human Users in Agentic Evaluations"** ([arXiv 2601.17087](https://arxiv.org/pdf/2601.17087)) documents four failure modes of simulated users:

1. **Behavioral homogeneity** — simulated users are uniform; real ones vary by personality/context.
2. **Impatience misalignment** — sims mismodel human patience/failure tolerance.
3. **Goal-specification brittleness** — sims over-interpret or fail to adapt to ambiguous goals.
4. **Interaction-artifact effects** — prompt phrasing biases sim behavior in ways it wouldn't bias humans.

**Why this is existential for stampede:** if simulated agents aren't realistic, the whole "wind tunnel" claim is hot air.

**Why it's actually stampede's differentiator (⊕ but must be made explicit):** the paper's own prescribed mitigations map 1:1 onto stampede's design *if we build them deliberately*:

| Paper's failure mode | Paper's mitigation | stampede mechanism |
|---|---|---|
| Behavioral homogeneity | "explicit behavioral diversity constraints" | **Persona packs** — the entire product is a diversity constraint made first-class. |
| Impatience misalignment | model patience explicitly | The **`impatient`** persona *is* a patience parameter (retry policy, timeout aggressiveness). |
| Goal brittleness | vary goal specification | The **`drunk` / `naive`** personas *are* malformed/under-specified goals. |
| Interaction artifacts | "sample multiple LLM variants" | **Model mixing** across the swarm (haiku + gpt-4o-mini + llama3) is built into `stampede.yaml`. |
| — | "validate against real-world deployment data" | ⊕ **NEW: the grounding/calibration subsystem the SPEC lacks (see 6.2-G1).** |

**Positioning move:** stampede should *cite this paper in its own README* and claim: "Yes, naïve agent-simulation is unreliable — that's precisely why stampede models *populations with calibrated temperaments and mixed models*, and lets you *ground personas against recorded real traffic*, instead of one generic simulated user."

### 6.2 Gaps / risks in the current SPEC (things to add or harden)

| ID | Gap in SPEC | Why it matters | Recommendation |
|---|---|---|---|
| **G1 ⊕** | **No persona *grounding/calibration* story.** The SPEC defines personas as authored temperaments; it never says how you know they're *realistic*. | The "Lost in Simulation" critique lands directly here. | Add a **grounding subsystem**: (a) **record mode** — capture real agent traffic (OTel traces) hitting a target; (b) **replay/fit** — calibrate persona parameters (patience, retry, error rate) to match recorded distributions; (c) report a *realism score* per persona. This is the answer to "how do you know your agents behave like real ones?" |
| **G2 ⊕** | **trace-format under-specified** — SPEC says "OpenTelemetry-compatible" but doesn't commit to gen_ai.* conventions. | Ambiguity here fragments the whole portfolio. | Bind trace-format to the **OTel GenAI profile** (§3). Authoritative schema in `ARCHITECTURE.md §4.1`. |
| **G3 ⊕** | **No safety / authorization gate.** An adversarial swarm + a misconfigured target = you just DoS'd production (or a real mainnet, not a fork). | Denial-of-wallet + kill-injection pointed at prod is a foot-gun and a reputational/legal risk for a *trust* brand. | Add a **Target Safety Gate**: explicit allowlist, `--i-understand-this-is-not-production` style guard, EVMTarget refuses non-fork RPC by default (checks `chainId`/fork marker), and a global `budget_usd` hard-stop enforced *before* spend. |
| **G4 ⊕** | **The misuse map needs a ground-truth oracle.** "34% called delete when they meant archive" requires knowing what they *meant*. | Without an intent oracle, the flagship number is unfalsifiable. | Each goal carries an **expected-tool / expected-effect label** (from auto-gen or authoring). Misuse = agent's realized tool-path diverges from the labeled intent. Report confusion only where intent is known; mark the rest "unlabeled." |
| **G5 ⊕** | **Run-diffing is hand-waved.** "Compare two runs like snapshot tests" ignores that runs are stochastic. | A naive diff flags noise as regression and destroys CI trust. | Specify a **statistical diff**: seeded runs fix model+temperature+seed; report metrics as distributions; a regression = a *significant* shift (effect size + CI) on a tracked metric, not any delta. Borrow τ²-bench's `pass^k`. |
| **G6 ⊕** | **Goal auto-generation quality is the crux of realism but is one line in the YAML.** | Bad goals → unrealistic swarm → worthless report. | Elevate **Goal Synthesis** to a named subsystem: derive goals from tool descriptions + resources + (optionally) recorded traffic; each goal gets difficulty + intent label; a `--dry-run` path validates goals without spend. |
| **G7 ⊕** | **Per-agent target state isolation unspecified.** If 200 agents share one target DB, their side-effects confound each other and the report. | You can't attribute a failure to an agent if agents corrupt each other's state. | Define isolation policy per target: session/tenant isolation where the target supports it; else document confounding and offer `reset()` between waves; integrate mockworld's per-session state isolation. |
| **G8 ⊕** | **Only MCP/HTTP/EVM targets — no A2A.** Agent-to-Agent protocol is emerging as the multi-agent interop standard alongside MCP. | If A2A gains traction, "wind tunnel for agents" that can't test A2A endpoints has a hole. | Note A2A as a **v0.3 target adapter** candidate; keep the Target Adapter interface protocol-agnostic so it slots in. |
| **G9 ⊕** | **No cost model for stampede's *own* spend beyond a cap.** | Users need to *predict* a run's cost before committing, not just cap it. | Add a **pre-run cost estimator** (`stampede plan`): population × model prices × est. turns → predicted $ range, shown before the run starts. |
| **G10 ⊕** | **Determinism vs. LLM nondeterminism contract not defined for the `--dry-run` path.** | CI needs a *fully deterministic, zero-LLM* smoke path or it can't gate. | Define **`--dry-run` = heuristic agents (no LLM), fixed seed, deterministic scheduler** → identical report every run; this is the CI smoke gate. |

### 6.3 Gaps in the field (stampede's opportunities)

1. **No target-as-subject tool exists** (the core white space) — everyone tests the agent, not the system the agent uses.
2. **No open-source Gauntlet** — agent-based protocol stress-testing is a closed, consulting product.
3. **No standard "misuse map" artifact** — the disambiguation-matrix concept exists in mcp-probe's spec and LiveMCP-101's taxonomy, but no tool *ships it against your server as a report*.
4. **No injectable chaos *runtime* for agents** — ReliabilityBench is a benchmark; Gremlin is infra; nobody gives you `chaos:` as a config block against your own target.
5. **No population-level cost profile** — costbomb (portfolio sibling) is the only thing hunting cost, and it's single-agent; the per-persona cost spread ("naive burns $3.40 vs expert $0.12") is unique.

---

## 7. Differentiation & positioning

### 7.1 The positioning sentence

> **stampede is to your MCP server / API / protocol what a wind tunnel is to an airframe:** it doesn't tell you if the *wind* is good (that's an eval tool's job) — it tells you if *your thing* survives contact with a realistic, turbulent population of the agents that will actually use it.

### 7.2 The competitive frame (what to say when asked "isn't this just X?")

| "Isn't this just…" | The answer |
|---|---|
| …load testing? | Load tests measure RPS of stateless endpoints; stampede measures *behavior* — misuse, confusion, cost spread, recovery. Lead demos with the **misuse map and cost profile**, never RPS. |
| …LangWatch Scenario / an eval tool? | Those simulate *users* to test *your agent* and assume the target is correct. stampede simulates *agents* to test *your target* and assumes the target is *suspect*. Opposite camera. We *export to* agentevals; we don't replace it. |
| …a benchmark like LiveMCP-101? | Benchmarks score *models* on *fixed* corpora. stampede scores *your server* against a *population you configure*. We cite their taxonomy; we're a tool, not a leaderboard. |
| …Gauntlet? | Gauntlet is closed, B2B-services, DeFi-only. stampede is open-source, protocol-general, and one-command; EVMTarget is "open Gauntlet for everyone." |
| …chaos engineering (Gremlin)? | Gremlin kills pods; stampede kills *agents mid-reasoning* and asserts *agent-specific* recovery (state survival, exactly-once side-effects). |

### 7.3 The moats

1. **The persona-pack ecosystem** — versioned, shareable, community-contributed temperaments = a flywheel nobody else has (and shared with costbomb).
2. **The Agent Readiness Report as a *named artifact*** — like a Lighthouse score, it becomes a thing people screenshot and demand.
3. **Portfolio interlock** — consumes mockworld, embeds costbomb, asserts exactly-once, ingests agent-postmortems, emits trace-format. Each sibling drives adoption of stampede and vice-versa.
4. **Native author credibility** — building MCP servers and agentic risk systems is the author's day job.

---

## 8. Comprehensive use-case catalog

Grouped by target type. Each is a concrete "point stampede at X to answer Y."

### 8.1 MCPTarget (v0.1)
- **UC-M1** Pre-publish description audit: which tool pairs do agents confuse?
- **UC-M2** Tool-selection under scale: does adding a 40th tool degrade selection accuracy?
- **UC-M3** Legibility regression: did this PR's description change raise the confusion rate? (CI gate)
- **UC-M4** Cost-per-persona: what does a naive vs expert agent cost to complete the same goal?
- **UC-M5** Concurrency ceiling: at what swarm size do SSE connections drop / p99 explode?
- **UC-M6** Chaos recovery: kill agents mid-task, fail a tool — does the server leak state / connections?
- **UC-M7** Adversarial: injection strings in args, denial-of-wallet loops, tool-poisoning replay from agent-postmortems.
- **UC-M8** Third-party vetting: run against a vendor's server before adopting it (U5).
- **UC-M9** `--from-probe`: upgrade an mcp-probe static run into a full behavioral simulation.
- **UC-M10** mockworld target: run the swarm against a fake Stripe/CRM to demo the delete-vs-archive misuse safely.

### 8.2 HTTPTarget (v0.1)
- **UC-H1** OpenAPI-as-toolset: agents get the spec, do they pick the right endpoint?
- **UC-H2** Auth/error handling: how do agents react to 401/429/500 under chaos?
- **UC-H3** Idempotency probe: replay + crash → does the API double-charge? (asserts exactly-once)

### 8.3 EVMTarget (v0.2)
- **UC-E1** Liquidation cascade: 1000 borrower/lender agents on a fork — does a price shock cascade?
- **UC-E2** Griefing / MEV-ish behavior: adversarial agents front-run / sandwich the protocol.
- **UC-E3** Parameter stress: sweep a collateral ratio, watch the swarm's aggregate behavior (open-Gauntlet).
- **UC-E4** Denial-of-wallet onchain: gas-burning loops via costbomb's economic cohort.
- **UC-E5** Recovery + exactly-once: agent crashes mid-tx on resume — does it double-submit?

### 8.4 Cross-cutting / research
- **UC-R1** Reproducible population experiment (seeded, citable).
- **UC-R2** Emergent-behavior study: do agents coordinate/collide at scale? (society-sim lineage)
- **UC-R3** Incident replay: ingest an agent-postmortems incident as a chaos scenario ("replay last month's real failure against your stack").

---

## 9. Open questions (for the delivery phase to resolve)

1. **Persona realism ceiling:** how close can calibrated personas get to recorded real traffic before diminishing returns? (Determines how much to invest in G1.)
2. **Goal auto-gen without an LLM:** is there a template/grammar approach good enough for the `--dry-run` deterministic path, or does realistic goal-gen always need a model?
3. **Intent oracle authoring cost:** is expected-tool labeling (G4) cheap enough to auto-derive, or does it need human seeding for the flagship demo?
4. **Concurrency backend threshold:** at what swarm size does asyncio-on-a-laptop stop sufficing and Ray earn its ~1–2ms/request overhead? (Research suggests laptops handle low-hundreds of stateful agents; validate.)
5. **Shared-primitive packaging:** vendor-per-repo now vs. `agent-reliability-core` package — SPEC recommends vendor-now, extract at v0.2. Confirm trace-format is stable enough to extract first.
6. **A2A priority:** does A2A adoption in 2026 justify pulling the A2A adapter forward from v0.3?
7. **Report determinism for screenshots:** the report is the marketing artifact — how much run-to-run variance is acceptable before it stops being screenshottable/trustworthy?

---

## 10. Sources

- premai — Load Testing LLMs (2026): https://blog.premai.io/load-testing-llms-tools-metrics-realistic-traffic-simulation-2026/
- TianPan — Load Testing LLM Applications: Why k6 and Locust Lie to You (2026): https://tianpan.co/blog/2026-03-19-load-testing-llm-applications
- TianPan — Chaos Engineering for AI Agents (2026): https://tianpan.co/blog/2026-04-12-chaos-engineering-ai-agents-injecting-failures-before-production
- LangWatch Scenario: https://scenario.langwatch.ai/ · https://github.com/langwatch/scenario
- LiveMCP-101 (arXiv 2508.15760): https://arxiv.org/abs/2508.15760
- LiveMCPBench (arXiv 2508.01780): https://arxiv.org/html/2508.01780
- MCP-Bench (arXiv 2508.20453): https://arxiv.org/pdf/2508.20453
- MCPAgentBench (arXiv 2512.24565): https://arxiv.org/pdf/2512.24565
- ReliabilityBench (arXiv 2601.06112): https://arxiv.org/pdf/2601.06112
- "Lost in Simulation" (arXiv 2601.17087): https://arxiv.org/pdf/2601.17087
- AgentSociety (arXiv 2502.08691): https://arxiv.org/abs/2502.08691
- Emergence World (arXiv 2606.08367): https://arxiv.org/pdf/2606.08367
- Static Sandboxes Are Inadequate (arXiv 2510.13982): https://arxiv.org/pdf/2510.13982
- Survey on Evaluation of LLM-based Agents (arXiv 2503.16416): https://arxiv.org/html/2503.16416v2
- Reasoning Provenance for Autonomous AI Agents (arXiv 2603.21692): https://arxiv.org/pdf/2603.21692
- OTel GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/ · registry: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- Datadog GenAI semconv support: https://www.datadoghq.com/blog/llm-otel-semantic-convention/
- Zylos — OTel for AI Agents (2026): https://zylos.ai/research/2026-02-28-opentelemetry-ai-agent-observability
- MCP ecosystem 2026: https://www.qcode.cc/mcp-servers-ecosystem-2026 · https://workos.com/blog/everything-your-team-needs-to-know-about-mcp-in-2026 · https://www.digitalapplied.com/blog/mcp-97-million-downloads-model-context-protocol-mainstream
- MCP roadmap 2026: https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/
- Gauntlet (DeFi agent sim): https://medium.com/@gwrx2005/gauntlet-simulation-based-risk-modeling-and-quantitative-research-for-defi-fb736e4392d2 · https://gauntlet.network/
- Foundry Anvil: https://www.getfoundry.sh/anvil · Python bindings: https://web3-ethereum-defi.readthedocs.io/api/provider/_autosummary_provider/eth_defi.provider.anvil.html
- MS Azure — Load testing hosted MCP servers with Locust: https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/load-testing-hosted-mcp-servers-with-locust-and-azure-load-testing/4522691
- MS — SRE for autonomous AI agents: https://techcommunity.microsoft.com/blog/linuxandopensourceblog/applying-site-reliability-engineering-to-autonomous-ai-agents/4521357
- Fastio — MCP server load testing / AI agent chaos: https://fast.io/resources/mcp-server-load-testing/ · https://fast.io/resources/ai-agent-chaos-engineering/
- Ray agent architecture (2026): https://markaicode.com/architecture/agent-architecture-with-ray/
