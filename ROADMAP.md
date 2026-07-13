# stampede — Roadmap

## v0.1 (launch)
- MCPTarget + HTTPTarget adapters
- 6 built-in personas (naive, expert, impatient, frugal, adversarial, drunk)
- Orchestrator with concurrency curves (ramp / spike / steady) + simulated time
- Chaos injector (kills, tool failures, latency, malformed responses)
- Agent Readiness Report (HTML + terminal) with misuse map + cost profile
- Watchable live dashboard; one-command local run; provider-agnostic
- Cairn case study #1
- Launch on HN + the "wind tunnel" essay

## v0.2
- EVMTarget (mainnet-fork DeFi simulator; funded test wallets)
- Persona-pack registry & sharing
- costbomb extracted as standalone
- Distributed backend (Ray/workers); run-diffing in CI

## v0.3
- mockworld integration (`stampede` targets a `mockworld` world)
- Official framework adapters (LangGraph / CrewAI)
- Hosted report sharing (seed of the commercial tier)
