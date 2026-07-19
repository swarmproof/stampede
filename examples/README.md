# Examples — your first simulation

Three ways to point a swarm at a system. All run with `--dry-run` (zero LLM, zero
keys, deterministic) so you can see the shape of the output immediately, then drop
`--dry-run` and add real models for a live run.

## 1. The built-in mock world (no setup)

```bash
pip install -e .            # from the repo root (or: pip install stampede)
stampede init               # writes stampede.yaml (targets mock:crm)
stampede run --dry-run      # watch the misuse map appear
```

You'll get an **Agent Readiness Report** with a misuse map showing agents confusing
`archive_record` and `delete_record`, a per-persona success + cost table, and a
chaos/recovery section. The HTML report lands at `./stampede-report.html`.

Try the other world:

```bash
stampede run --dry-run --target mock:payments   # exercises exactly-once under chaos
```

## 2. A real MCP server (stdio)

`echo_server.py` is a minimal MCP server with the same two confusable tools.

```bash
pip install "mcp"                                  # the server needs the MCP SDK
pip install -e ".[mcp]"                            # stampede's MCP client extra
stampede run --config examples/mcp_stdio.yaml --dry-run
# or point directly:
stampede run --target "python examples/echo_server.py" --dry-run
```

## 3. An HTTP / OpenAPI endpoint

`--dry-run` stubs the LLM brain but still hits the target for real, so start your
own service on `localhost:8000` first (localhost is allowlisted by default).

```bash
pip install -e ".[dev]"                            # brings in httpx
# start your OpenAPI service on :8000, then:
stampede run --config examples/http_openapi.yaml --dry-run
```

## Going live (local, free) — Ollama

Drive a real swarm with a local Ollama model, no keys, no cost:

```bash
ollama pull llama3.1                       # a tool-capable model
pip install -e ".[providers]"              # the openai client (used for Ollama's /v1)
stampede run --config examples/ollama_live.yaml   # NOTE: no --dry-run → real model calls
```

Each `ollama:*` agent asks the model to pick a tool for its goal; the `BrainPool`
routes per agent, so you can **mix** live and heuristic agents in one swarm:

```yaml
population:
  models: [ollama:llama3.1, dry-run:heuristic]   # some real, some free/instant
```

## Going live — hosted providers

```yaml
population:
  models: [anthropic:claude-haiku, ollama:llama3.1]   # provider-agnostic
report:
  budget_usd: 2.00                                     # hard pre-spend cap
```

Then estimate before you spend:

```bash
stampede plan                # per-persona cost estimate, no target contact
stampede run --budget 2.00   # hard-stops near the cap, still writes a valid report
```

## CI gate

```bash
stampede run --dry-run --fail-under B    # exits non-zero if the grade drops below B
```
