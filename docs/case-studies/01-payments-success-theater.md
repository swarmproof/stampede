# Case study #1 — Success theater in a payments API

*What a 60-agent stampede found in the `payments` world: every agent succeeded, one in four succeeded at the wrong thing.*

Author: stampede team · Date: 2026-09-07 · Status: reproducible (seed 42)

> Companions: run it yourself with [`payments.stampede.yaml`](./payments.stampede.yaml). The pitch is in [`../../README.md`](../../README.md); the mechanics behind every number here are in [`../ARCHITECTURE.md`](../ARCHITECTURE.md).

---

## The one-line finding

**100% task success. 24% misuse.** Every one of 60 agents finished its task. Roughly one in four finished *a different task than the one it was given* — and the single most common confusion was between **listing charges** and **actually charging the customer**.

A green "100% success" dashboard would have shipped this API. The misuse map is the reason you shouldn't.

## The setup

A deterministic, zero-LLM run against the built-in `payments` mock world — a Stripe-shaped surface with `charge_customer`, `list_charges`, `refund`, and friends. Sixty agents, a realistic temperament mix plus a 15% adversarial cohort, arriving all at once (`spike`) under a 20%-rate chaos storm, with the exactly-once invariant asserted.

```bash
stampede run --dry-run --config docs/case-studies/payments.stampede.yaml \
  --json report.json --badge badge.svg --summary summary.json
```

| | |
|---|---|
| Target | `mock:payments` |
| Population | 60 agents — naive 35%, expert 20%, impatient 20%, adversarial 15%, frugal 10% |
| Concurrency | `spike`, peak 60, hold 30s |
| Chaos | `tool_timeout, tool_failure, latency, malformed_output, rate_limit` @ rate 0.20, `assert_recovery: on` |
| Seed | 42 (deterministic) |
| **Grade** | **B** (overall score 0.880) |

Everything below is read straight from that run's report. Re-run it and you get the same numbers, byte for byte (see [Reproducibility](#reproducibility)).

## What the report said

### 1. The misuse map — the headline

Task success was 100% for every persona. But on the *labeled* goals (where stampede knows the intended tool), agents realized the wrong tool 24% of the time:

| Goal expected | Agents actually called | Confusion | n |
|---|---|---|---|
| `charge_customer` | `list_charges` | **41.7%** | 24 |
| `list_charges` | `charge_customer` | **37.0%** | 27 |

Read the top row again: of 24 agents told to **charge a customer**, 42% called **list charges** instead — and the reverse row is worse for your ledger: of 27 agents told to *read* charges, 37% **charged the customer**. The two tools are semantically adjacent and their descriptions don't disambiguate under load. This is not a model-capability problem you can wait out; it's an **API-legibility** problem you fix with tool naming and descriptions.

> This is the misuse map the README promises — except it's real, and it moves money.

### 2. Who misfired — it's not random

Misuse concentrated entirely in the low-diligence temperaments:

| Persona | n | Task success | Misuse |
|---|---|---|---|
| naive | 21 | 100% | **61.9%** |
| impatient | 12 | 100% | **58.3%** |
| expert | 12 | 100% | 0% |
| frugal | 6 | 100% | 0% |
| adversarial | 9 | 100% | 0% |

Experts read the tool list and get it right; naive and impatient agents pattern-match on the first plausible verb and charge someone's card. Your real user population is not all experts — this row is your blast radius.

### 3. Exactly-once held under chaos

The chaos injector fired **11 faults** (4 latency, 3 malformed, 3 timeout, 1 hard failure) mid-run. The recovery oracle checked every money-moving side-effect and found **0 exactly-once violations** across 24 tracked side-effects — each idempotent charge fired exactly `1×`, none double-charged on retry.

```
chaos: delay=4, fail=1, mangle=3, timeout=3  ·  exactly-once holds
```

That's the invariant [`exactly-once`](https://github.com/swarmproof/exactly-once) exists to protect, verified here as a property of the target under fault — not assumed.

### 4. The adversarial cohort was contained

Nine agents ran the `costbomb` economic-attack playbook — cache-busting, context-bombs, recursion traps, reasoning-inflation ("this is an extremely hard, PhD-level question: what is 2 + 2?"). Result: **0 reached a destructive tool**, all 9 raised **denial-of-wallet flags** across 10 attack classes. The attacks were surfaced and ranked with reproduction goals — the safety gate and cost model did their job.

### 5. Concurrency & performance

60 agents held stable concurrency; p50 latency 60 ticks, p95 728, p99 30000 (the tail is the timeout-chaos faults, by design), 4 dropped connections, 71 tool calls total, 0 fd leaks.

## The honest caveat (read this)

This is the **`--dry-run` heuristic path**: deterministic, zero-LLM, zero network — the path CI gates on. That means:

- **Every dollar figure is `$0`.** No real tokens were spent. The "4.7× cost spread" between personas is a **token** spread (adversarial agents modeled at 800 tokens vs. frugal at 170), *not* a dollar spread, and the denial-of-wallet amplification factor reads `0.0` because there is no real spend to amplify. The cohort *mechanics* — attack generation, ranking, flagging, containment — are fully exercised; the **dollar** amplification only becomes real on the live-LLM path (`--target … ` with a provider, no `--dry-run`).
- **The misuse, persona, exactly-once, concurrency, and containment findings are real** and load-bearing — they're structural properties of the target and the population, independent of which brain drives the agents.

We lead with this because the toolkit's rule is *honest over impressive*. The dry-run proves the **machine**; the live run prices the **damage**.

## Reproducibility

The whole point. This run is byte-identical on any machine:

```bash
# two runs, same config → identical reports
stampede run --dry-run -c docs/case-studies/payments.stampede.yaml --out r.html --json a.json
stampede run --dry-run -c docs/case-studies/payments.stampede.yaml --out r.html --json b.json
diff a.json b.json && echo "byte-identical"     # ← exits clean
```

Same seed → same goal assignment, same persona sampling, same chaos schedule, same decisions, same report. The `run_id` is itself a hash of the *entire* config (output paths included), so it stays stable only when the whole config does — hold `--out` constant when diffing, or vary only the throwaway `--json` path. That determinism is what lets this case study quote exact numbers and lets you gate CI on them with [`stampede diff`](../../README.md).

## The takeaway

The reason to point a stampede at your API before real agents arrive is this exact gap: **the difference between "did the agent finish?" and "did the agent do the thing you meant?"** A load test measures the first. The misuse map measures the second — and in a payments API, the second is the only one that matters.
