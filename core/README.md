# agent-reliability-core

Shared primitives for the [Swarm Proof](https://github.com/swarmproof) agent-reliability toolkit — extracted from `stampede` at v0.2 (ADR-4).

## trace-format

A **profile of the OpenTelemetry GenAI semantic conventions**: standard `gen_ai.*` attributes plus a namespaced `swarmproof.*` extension for population / persona / chaos / cost context. This is the telemetry contract `stampede`, `mcp-probe`, `costbomb`, and `mockworld` all emit into.

```python
from agent_reliability_core.trace import Tracer, TraceStore, GenAI, Swarmproof, SpanKind

store = TraceStore(":memory:")
tracer = Tracer(store, run_id="run_1", seed=42)
span = tracer.start("chat", kind=SpanKind.CLIENT)
span.set(GenAI.REQUEST_MODEL, "claude-haiku")
tracer.end(span)
```

Dependency-free (stdlib only). Span IDs are deterministic in `(seed, counter)` so seeded runs are byte-reproducible.

## concurrency-core

Virtual-time clocks, concurrency curves, and a pluggable `Executor` — the swarm scheduler `stampede`'s orchestrator and `mcp-probe`'s load engine both run on.

```python
from agent_reliability_core.concurrency import SimClock, schedule_offsets, AsyncioExecutor

offsets = schedule_offsets(size=200, curve="ramp", peak=200, hold=30)   # arrival schedule
results = await AsyncioExecutor().run(factories, concurrency=200)        # capped, failure-isolated
```

## persona-pack

Versioned agent *temperaments* as data — the `swarmproof.dev/persona/v1` schema, `extends` inheritance, seeded mix sampling, and (de)serialization.

```python
from agent_reliability_core.persona import load_pack, sample_mix

pack = load_pack("core")                                  # the six built-in temperaments
pack = load_pack("mypack", search_paths=[my_registry])    # + a consumer's own dir
agents = sample_mix(pack, {"naive": 0.6, "expert": 0.4}, size=50, seed=42)
```

## report-renderer

A domain-agnostic report model (badge + `KpiRow`/`Table`/`Callout`/`Note`), the oxblood `Theme`, and HTML + terminal renderers. Each tool adapts its own report into a `Report` and gets the portfolio's look. Needs the `[render]` extra (jinja2 + rich).

```python
from agent_reliability_core.report import Report, Badge, KpiRow, Kpi, render_html

report = Report(title="My Report", badge=Badge("A"),
                sections=[KpiRow([Kpi("97%", "success")])])
html = render_html(report)   # or render_terminal(report)
```

All four shared primitives are extracted (ADR-4 complete).

[Apache-2.0](../LICENSE)
