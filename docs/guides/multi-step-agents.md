# Multi-step agents

*How to let an agent sequence tool calls (`create → use`) against a stateful target.*

Status: guide · applies from the `max_steps` feature

## The default: one decision per agent

By default, every stampede agent makes **one** tool decision for its goal, then that
call is retried (same tool) under chaos. This is deliberate — it's what produces the
**misuse map**, the flagship measurement: *"which tool does an agent reach for,
given this goal?"* For that question, one decision is exactly right, and it keeps
`--dry-run` fast, deterministic, and cheap.

It has a ceiling, though. Some goals are inherently multi-step: you can't `capture` a
charge that was never created, or `charge` a customer that doesn't exist. Against a
**stateful** target (a mockworld world, a real API), a single decision on such a tool
just errors — the agent never gets to do the prerequisite first.

## The knob: `population.max_steps`

```yaml
population:
  max_steps: 6        # default 1. >1 → multi-step agents.
```

With `max_steps > 1`, each agent runs a loop: **decide → act → observe → decide
again**, feeding every result back into the next decision, until its brain reports
the goal is done, it gives up, or it hits the step limit. A capable brain uses this
to recover:

```
goal: "charge customer cus_2 500 cents"
  step 0  create_charge(cus_2, 500)   → ERROR: no such customer
  step 1  create_customer(cus_2)      → ok            ← the agent reacts to the error
  step 2  create_charge(cus_2, 500)   → ok
  step 3  (no tool call)              → done
```

## What it needs to actually work

Multi-step composes with two other things:

1. **A reasoning brain.** The dry-run heuristic makes its single reach and stops — it
   has no model to infer prerequisites. Multi-step pays off with a **live LLM** or a
   **framework agent** (LangGraph/CrewAI) that can read an error and decide the next
   step. (Dry-run with `max_steps > 1` stays deterministic and simply ends after the
   one reach.)
2. **An actionable step 0.** Schema-aware goal synthesis bakes concrete values into
   goals for discovered tools, so the model has something to call on the first step
   instead of asking for details. This is automatic in `template` mode.

See [`examples/multi_step.yaml`](../../examples/multi_step.yaml) for a runnable live
setup against a mockworld fake Stripe.

## How the report changes

- **Misuse (ADR-5)** is now *"the intended tool was never called across the whole
  sequence."* A legitimate prerequisite call (e.g. `create_customer` on the way to a
  charge) is **not** counted as misuse. The misuse-map key stays the agent's *first*
  reach — what it tried before observing anything.
- **Success** means the intended tool (for labeled goals) was invoked successfully at
  some step — not merely that one call returned ok.
- Each step emits its own `chat` + `execute_tool` spans, so the trace shows the full
  sequence per agent (`stampede run ... --otlp ...`, or read the persisted trace db).

## Honest boundaries

- **Determinism:** `max_steps = 1` is byte-identical to the pre-feature engine (it
  runs the unchanged single-decision path). Multi-step dry-run is deterministic but
  its reports differ from single-step by design.
- **Completion is model-dependent.** A small local model may reason about the missing
  customer yet not finish the sequence within the step budget; a stronger model (or a
  higher `max_steps`) completes more. stampede provides the *loop*; the brain provides
  the *competence*.
- **Chaos scope:** the single-step kill/recovery exactly-once *dance* (crash mid-call,
  re-attempt, assert one side-effect) is specific to the single-decision path. Multi-step
  still applies per-invoke faults and checks exactly-once on idempotent calls, but if
  your focus is the exactly-once proof under a mid-call crash, use `max_steps: 1`.
