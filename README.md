# stampede

### The wind tunnel for the agent economy

> You built it for agents. **stampede** shows you what agents will actually *do* to it. Generate realistic (and adversarial) agent populations, turn them loose on your MCP server, API, or protocol in a sandbox, and get a report of where they succeed, where they get confused, and where they break you.

<!-- TODO: demo GIF above the fold — the swarm hitting your system live, <90s -->
<p align="center"><em>▶ demo GIF coming — the watchable swarm crashing & recovering against a live target</em></p>

> **Status:** 🚧 v0.1 in progress. Building in public — follow the "wind tunnel" thread series.

---

## Why

Software is increasingly *consumed by agents, not humans*. But if you build an MCP server, tool API, or onchain protocol, you have no way to know how agents behave against it before shipping. You test one agent on one happy path, or fire uniform load that doesn't speak agent protocols. Both miss the real risk: **agents don't generate traffic, they generate *behavior*** — they misread tool descriptions, pick the wrong tool, retry in loops, and (when adversarial) exploit.

stampede generates a *population* of heterogeneous, stateful, realistically-flawed agents and turns them loose on your system to see what breaks.

## Quickstart

```bash
# from source (v0.1 — not yet on PyPI):
git clone https://github.com/swarmproof/stampede && cd stampede
python -m venv .venv && .venv/bin/pip install -e .

stampede init                       # writes a starter stampede.yaml (targets a mock world)
stampede run --dry-run              # zero-LLM, deterministic — watch the misuse map appear
# report at ./stampede-report.html

# against your own MCP server, and live (needs the extras + a model):
stampede run --target "python my_server.py" --size 200 --live
```

`--dry-run` needs no API keys and no network: it runs the deterministic heuristic
swarm so you see the report shape in seconds. Drop it (and set real `models:`) for a
live run. See [`examples/`](./examples) for MCP / HTTP / mock walkthroughs.

## The signature artifacts

- **Persona packs** — versioned YAML defining agent *temperaments*, not just models: `naive`, `expert`, `impatient`, `frugal`, `adversarial`, `drunk`. Community-contributable.
- **The Agent Readiness Report** — the screenshotable deliverable: task-success by persona, the **misuse map** ("34% of agents called `delete_record` when they meant `archive_record`"), swarm concurrency (p95/p99), the **cost profile**, and adversarial findings.
- **The watchable world** — a live local dashboard where you *see* the swarm hit your system and click any agent to ask "why did you call that tool?"

See [`SPEC.md`](./SPEC.md) for the full design and [`ROADMAP.md`](./ROADMAP.md) for what ships when.

## Part of the Swarm Proof toolkit

*Trust infrastructure for the agent economy — seven projects, one thesis.*

| Project | What it does |
|---------|--------------|
| **stampede** ← *you are here* | Point a herd of realistic agents at your system before real ones arrive |
| [mockworld](https://github.com/swarmproof/mockworld) | A synthetic internet for agents — fake Stripe, Gmail, exchange, instantly |
| [mcp-probe](https://github.com/swarmproof/mcp-probe) | The CI quality suite for MCP servers — lint, contract-test, benchmark, load |
| [costbomb](https://github.com/swarmproof/costbomb) | Denial-of-wallet fuzzing — find the inputs that make your agent spend $500 |
| [exactly-once](https://github.com/swarmproof/exactly-once) | Idempotency middleware so agent side-effects fire once |
| [agent-postmortems](https://github.com/swarmproof/agent-postmortems) | A structured incident database + post-mortem standard for agent failures |
| [awesome-agent-reliability](https://github.com/swarmproof/awesome-agent-reliability) | The curated map of the field |

## License

[Apache-2.0](./LICENSE). Provider-agnostic (OpenAI-compatible + Anthropic SDK + Ollama). Citable via [`CITATION.cff`](./CITATION.cff).
