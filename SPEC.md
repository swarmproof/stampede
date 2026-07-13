# stampede — Design Specification & PRD
### The wind tunnel for the agent economy
*Flagship project · v1.0 spec*

> **stampede** — you built it for agents. stampede shows you what agents will actually *do* to it. Generate realistic (and adversarial) agent populations, run them against your MCP server, API, or protocol in a sandbox, and get a report of where they succeed, where they get confused, and where they break you.

---

## 1. PRODUCT REQUIREMENTS DOCUMENT

### 1.1 Problem

Software is increasingly *consumed by agents*, not humans — MCP servers, tool APIs, and onchain protocols are all built to be driven by LLM-based agents. But the people building these systems have no way to know how agents will actually behave against them before shipping. Today they either (a) test manually with one agent and one happy path, or (b) write throwaway load scripts that fire uniform traffic — and, as the field itself admits, standard tools like k6 don't understand agent protocols, so teams hand-roll client loops. Both miss the real risk: **agents don't generate traffic, they generate *behavior*.** They misread tool descriptions, choose the wrong tool, retry in loops, chain calls unpredictably, and — when adversarial — exploit. No tool today generates a *population* of heterogeneous, stateful, realistically-flawed agents and turns them loose on your system to see what breaks.

### 1.2 Why now / why this wins

- MCP tool ecosystems already span 177,000+ APIs; FastMCP alone sees 1M+ downloads/day. The systems-built-for-agents category is exploding while its pre-production testing tooling is stuck in 2005.
- The existing agent-testing tools all point the *other* direction — they test the agent (agentevals, LangWatch, IntellAgent, LiveMCP-101). **Testing the system the agent uses, via a simulated agent population, is open white space.**
- The MiroFish precedent (67k stars) proves the *society-simulation-as-a-product* pattern spreads virally when it's watchable and one-command. stampede is that pattern pointed at a developer's own system — inherently more useful and more repeatable than predicting the news.
- Native author credibility: MCP servers and agentic risk systems are literally the author's day job.

### 1.3 Target users & jobs-to-be-done

1. **MCP server / tool-API builders** — "Before I publish, show me how 500 different agents use my tools, and where my descriptions are ambiguous." (Primary, largest, hottest.)
2. **Agent-platform / framework teams** — "Regression-test our orchestration against a standard agent swarm on every release."
3. **Protocol & DeFi engineers** — "Simulate a thousand agents with wallets using my protocol on a mainnet fork." (The premium, brand-defining, consulting-adjacent use.)
4. **AI researchers** — "A reproducible harness for multi-agent behavioral experiments." (Citations.)

### 1.4 Goals & non-goals

**Goals (v0.1):** generate configurable heterogeneous agent populations; run them concurrently and statefully against a target (MCP server first); inject chaos (kills, tool failures, latency); produce the **Agent Readiness Report**; provide a **watchable live view**; one-command local run; provider-agnostic; ship Cairn as case study #1.

**Non-goals (v0.1):** being an agent *evaluation* framework (that's agentevals' job — stampede integrates, doesn't replace); a hosted SaaS (that's the later commercial layer); a general MAS orchestration standard; replacing k6 for pure HTTP.

### 1.5 Success metrics

- **North star:** number of distinct repos with a `stampede.yaml` committed (adoption depth, not vanity stars).
- Launch: 500+ GitHub stars in 30 days; front page of HN; 3 external persona packs contributed within 60 days.
- 12 months: adopted in ≥25 public projects' CI; ≥1 framework ships an official stampede adapter; the "Agent Readiness Report" becomes a screenshot people post.

### 1.6 The signature artifacts (what makes it a category, not a load tester)

1. **Persona packs** — versioned, shareable YAML defining agent *temperaments*, not just models: `naive`, `expert`, `impatient` (aggressive timeouts + retries), `frugal` (token-minimizing), `adversarial` (injection + denial-of-wallet playbooks), `drunk` (malformed/contradictory goals). Community-contributable → the ecosystem flywheel.
2. **The Agent Readiness Report** — the screenshotable deliverable: task-success by persona; the **misuse map** ("34% of agents called `delete_record` when they meant `archive_record` — your descriptions are ambiguous"); swarm concurrency performance (p95/p99, dropped connections); the **cost profile** ("naive agent burns $3.40 for what an expert does at $0.12"); adversarial findings.
3. **The watchable world** — a live local dashboard where you *see* the swarm hit your system and can click any agent to ask "why did you call that tool?" This is the demo GIF. (MiroFish's true lesson: don't make them read logs, make them watch a society.)

---

## 2. ARCHITECTURE

### 2.1 High-level shape

```
                        ┌──────────────────────────────────────────┐
                        │              stampede CLI / core          │
                        └──────────────────────────────────────────┘
                                          │
      ┌───────────────┬──────────────────┼───────────────────┬───────────────────┐
      ▼               ▼                  ▼                   ▼                   ▼
┌───────────┐  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Target   │  │  Population  │   │  Orchestrator │   │   Chaos      │   │   Observer    │
│  Adapter  │  │   Factory    │   │  (scheduler)  │   │   Injector   │   │ (trace + UI)  │
└───────────┘  └─────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
      │               │                  │                   │                   │
      ▼               ▼                  ▼                   ▼                   ▼
  connects to     builds N          runs agents         kills / fails      emits shared
  MCP / HTTP /    Agent instances   concurrently over   / delays /          trace format;
  EVM fork        from persona      simulated time;     injects bad         serves live
  under test      packs + goals     manages state       responses           dashboard + report
```

### 2.2 Components

**A. Target Adapter (pluggable "what am I attacking?")**
- `MCPTarget` (v0.1 priority): connects over stdio or HTTP/SSE, performs MCP `initialize`, discovers tools/resources/prompts, exposes them to agents. Handles the JSON-RPC + SSE specifics that generic load tools miss.
- `HTTPTarget`: any OpenAPI/REST endpoint (agents get the spec as their toolset).
- `EVMTarget` (v0.2, the premium hook): points at a mainnet fork (Anvil/Foundry); agents hold funded test wallets; tool calls become transactions. This is what turns stampede into an open Gauntlet-style simulator.
- Interface: `discover() -> ToolSet`, `invoke(tool, args, agent_ctx) -> Result`, `reset()`.

**B. Population Factory**
- Input: a persona pack (or mix, e.g. `60% naive, 30% expert, 10% adversarial`) + a goal set (natural-language objectives, optionally generated from the target's own tool descriptions).
- Output: N `Agent` instances, each with: a model binding (provider-agnostic), a temperament (system-prompt + behavioral params: retry policy, patience, token budget, risk appetite), a private memory, and a goal.
- Agents are deliberately *imperfect* — temperament controls how they misread and misuse, because realistic failure is the product.

**C. Orchestrator (scheduler)**
- Runs agents concurrently with a configurable concurrency curve (ramp to N, hold, spike) — this is how swarm-concurrency metrics get produced.
- **Simulated time:** a virtual clock lets hours of agent activity compress into minutes; agents can be scheduled in waves.
- Manages per-agent state machines (aligns with Cairn's six-state model — dogfooding the protocol).
- Async Python core (asyncio) so hundreds of stateful agents run on a laptop; heavy runs distribute via optional Ray/worker backend (v0.2).

**D. Chaos Injector**
- Wraps target invocations and agent lifecycles to inject: agent kills at random/specified steps; tool-call failures/timeouts; latency degradation; malformed or contradictory tool responses.
- Config-driven (`chaos:` block in stampede.yaml). This is where the original cairnbox chaos concept lives as a first-class module.
- After chaos, asserts recovery expectations (did state survive? were side-effects exactly-once? — hooks into `exactly-once`).

**E. Observer (trace + UI + report)**
- Every agent decision, tool call, result, and failure emits an event in the **shared OpenTelemetry-compatible trace format** (the primitive reused across the portfolio).
- **Live dashboard** (local web UI): swarm view (agents as dots hitting tools), per-agent inspector ("why did you call X?" answered from the agent's own reasoning trace), live metrics.
- **Report generator:** renders the Agent Readiness Report (HTML + terminal) via the shared oxblood-styled renderer.
- Optional export to agentevals / OTel backends (integrate, don't compete).

### 2.3 The `stampede.yaml` (the interface people commit to their repo)

```yaml
target:
  type: mcp
  transport: stdio
  command: "python my_server.py"

population:
  size: 200
  mix:
    naive: 0.5
    expert: 0.2
    impatient: 0.15
    frugal: 0.1
    adversarial: 0.05
  models:                      # provider-agnostic; distribute across the swarm
    - anthropic:claude-haiku
    - openai:gpt-4o-mini
    - ollama:llama3            # local, free, for cheap bulk agents

goals:
  autogenerate: true           # derive realistic goals from the target's tool descriptions
  extra:
    - "Refund the last order for customer 4471"
    - "Find and cancel any duplicate subscriptions"

concurrency:
  curve: ramp                  # ramp | spike | steady
  peak: 200
  hold: 5m

chaos:
  kill_agents_at: [random]
  inject: [tool_timeout, malformed_output]
  assert_recovery: true

report:
  out: ./stampede-report.html
  live: true                   # serve the watchable dashboard
  budget_usd: 5.00             # hard cap on total simulation spend
```

### 2.4 Tech stack

Python 3.11+ core (matches the agentic ecosystem); asyncio orchestration, optional Ray backend for scale; MCP via the official SDK; EVM via web3.py + Foundry/Anvil; live UI as a lightweight embedded web app (FastAPI + a small Vue/React front end, mirroring MiroFish's Python+Vue shape); trace store SQLite by default (Postgres adapter for big runs); provider-agnostic LLM layer (OpenAI-compatible + Anthropic SDK + Ollama).

### 2.5 Key risks & mitigations

- **Cost of running LLM swarms** → default to small/local models for bulk agents; hard `budget_usd` cap; a `--dry-run` heuristic mode with no LLM calls for CI smoke tests; aggressive caching of identical agent contexts.
- **Non-determinism makes runs hard to compare** → seedable runs, fixed model/temperature options, and report diffing (compare two runs like snapshot tests).
- **"Isn't this just load testing?"** → the report's misuse-map and cost-profile are things no load tester produces; lead every demo with those, not with RPS.
- **Scope creep toward being an agent framework** → hard non-goal; stampede *drives* agents, it doesn't help you *build* them.

---

## 3. ROADMAP

- **v0.1 (launch):** MCPTarget + HTTPTarget; 6 built-in personas; orchestrator with concurrency curves; chaos injector; Agent Readiness Report; live dashboard; Cairn case study; one-command run. Launch on HN + the "wind tunnel" essay.
- **v0.2:** EVMTarget (the DeFi simulator hook); persona-pack registry & sharing; costbomb extracted as standalone; distributed backend; run-diffing in CI.
- **v0.3:** mockworld integration; official framework adapters (LangGraph/CrewAI); hosted report sharing (the seed of the commercial tier).

## 4. LAUNCH

Build in public as a thread series ("building a wind tunnel for agents"). Launch day: HN "Show HN: stampede – simulate a herd of AI agents against your system before real ones arrive", the flagship essay on the site, X thread with the swarm-dashboard GIF, r/LocalLLaMA + r/mcp, submissions to Latent Space / TLDR AI, and a Trust Layer issue built around the Cairn simulation results. Talk demo: a live swarm crashing and recovering against Cairn on stage.
