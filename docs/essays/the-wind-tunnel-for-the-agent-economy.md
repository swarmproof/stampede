# The wind tunnel for the agent economy

*Why agents break your API in ways a load test will never show you — and what to do about it before real ones arrive.*

Author: stampede team · Date: 2026-09-17

---

## Your API is about to have a very different kind of user

For twenty years we built software for humans and tested it for humans. We wrote unit tests for the paths we imagined, ran a load test to make sure the servers held, and shipped. The load test was our proxy for "the real world will be fine": ten thousand requests a second, p99 under 200ms, no memory leaks. Green board, ship it.

That proxy is quietly breaking. A fast-growing share of the traffic hitting MCP servers, tool APIs, and onchain protocols is no longer human — it's agents. And an agent is not a faster human or a heavier load. It's a *different kind of user*, one your existing tests are structurally blind to.

Here's the uncomfortable part: an agent can drive your API to a **100% success rate** while doing the wrong thing a quarter of the time. Your dashboard will be green. Your ledger will not.

## Load tests measure throughput. Agents generate behavior.

A load test fires **uniform, well-formed traffic**. Every request is the request you designed; the only variable is how many per second. That tells you something real — whether your infrastructure holds — but it holds one thing fixed that agents refuse to hold fixed: **the decision of what to call and why.**

Agents don't generate traffic. They generate *behavior*:

- They **read your tool descriptions** and pick a tool — sometimes the wrong one, because two tools sound alike.
- They **retry in loops** when something fails, sometimes amplifying a single fault into a storm.
- They **get confused under concurrency**, carrying stale context from one step into the next.
- They **have temperaments** — a careful "expert" and an "impatient" agent make different mistakes on the same API.
- And some, eventually, are **adversarial** — probing for the input that makes you spend $500 or fire a side-effect twice.

None of this shows up in a requests-per-second chart. A load test can tell you your `charge_customer` endpoint sustains 5,000 rps. It cannot tell you that a quarter of the agents that *meant* to call `list_charges` will call `charge_customer` instead, because the two descriptions don't disambiguate under pressure. That second fact is the one that ends up in an incident review.

## The wind tunnel

Aerospace figured this out a century ago. You don't certify a wing by putting a static weight on it and confirming it doesn't snap. You put it in a **wind tunnel** — you generate realistic, turbulent, adversarial airflow and watch where the design flutters, stalls, and tears. The static load test and the wind tunnel measure different things. One asks "is it strong?" The other asks "how does it behave in the conditions it will actually meet?"

Agents are your turbulent airflow. **stampede is the wind tunnel.**

The idea is simple: before real agents arrive, generate a *population* of realistic and adversarial ones — heterogeneous, stateful, realistically-flawed — and turn them loose on your target in a sandbox. Then, instead of a throughput chart, produce the thing you actually need: a map of where agents **succeed**, where they get **confused**, and where they **break you**.

## What the wind tunnel found in a payments API

We pointed 60 agents at a Stripe-shaped payments API — a realistic temperament mix plus a 15% adversarial cohort, all arriving at once, under a chaos storm that injected timeouts, failures, latency, and malformed responses. It's a deterministic, zero-LLM run, so anyone can reproduce it exactly. ([Full case study, one command to re-run.](../case-studies/01-payments-success-theater.md))

The headline number a load test would have given you: **100% task success.** Every agent finished.

The number the wind tunnel gave you: **24% misuse.** One in four agents finished *a different task than the one it was handed*. And the single most common confusion is the one you least want in a payments system:

- Of the agents told to **charge a customer**, 42% called **list charges** instead.
- Of the agents told merely to **read** the ledger, 37% **charged the card**.

"Read the ledger" quietly became "charge the card" for more than a third of the agents that tried it. That is not a capacity problem you can wait out with a bigger model — it's an **API-legibility** problem, fixable today with better tool names and descriptions. But you can only fix it if you can *see* it, and the only instrument that shows it is a misuse map.

The rest of the report is the part that lets you sleep: the confusion concentrated in the naive and impatient temperaments (experts got it right), the **exactly-once invariant held** under 11 injected faults — no double charges on retry — and the adversarial cohort was **contained**, reaching zero destructive tools while every one of its denial-of-wallet probes was surfaced and ranked.

Grade: **B.** Not because it fell over — because a quarter of its users, given a clear instruction, did the wrong thing with money.

## Honest instruments earn trust

One more thing, because it's the whole game. That run is on the deterministic dry-run path, which means **every dollar figure in it is $0** — no real tokens were spent. The cost-attack *mechanics* are exercised (the attacks are generated, ranked, flagged, contained), but the real dollar amplification only appears when you run the swarm against live models. We say this at the top of the report, not the bottom.

An instrument you can't trust is worse than no instrument. So the wind tunnel is **reproducible** (same seed, byte-identical report), it **states its own limits**, and it separates "the machine works" from "here's what it will cost you." The dry-run proves the machine; the live run prices the damage.

## Before the real herd arrives

If you build something agents will use, you have a short window where you can see how they'll behave against it *before* they show up in production. Use it. Point a population at your target, and read the misuse map instead of the success rate.

```bash
pip install stampede
stampede init
stampede run --dry-run      # zero-LLM, deterministic — the misuse map in seconds
```

The agents are coming. The only question is whether you meet them in a wind tunnel or in an incident channel.

---

*stampede is the flagship of [Swarm Proof](https://github.com/swarmproof) — trust infrastructure for the agent economy. Provider-agnostic, Apache-2.0.*
