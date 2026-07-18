"""The programmatic run API — wire the whole pipeline (ARCHITECTURE §3.1).

``stampede.yaml → Safety Gate → Target.discover() → Goal Synthesis →
Population Factory → Orchestrator drives Agents ⇄ (Chaos-wrapped) Target →
Observer records trace-format → report``.

``run_simulation`` is what the CLI calls; it returns the report plus the trace
store and outcome so callers can render, export, or serve them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from stampede.chaos.injector import ChaosPolicy
from stampede.config import StampedeConfig
from stampede.goals.synth import synthesize
from stampede.observer.report import RunReport, build_report
from stampede.orchestrator.engine import Orchestrator, RunOutcome
from stampede.personas.loader import load_pack
from stampede.population.brain import Brain, HeuristicBrain, LLMBrain
from stampede.population.factory import build_population
from stampede.population.providers import build_provider, cost_usd
from stampede.targets import build_target
from stampede.targets.base import TargetAdapter
from stampede.targets.safety import SafetyGate
from stampede.trace.store import TraceStore
from stampede.trace.tracer import Tracer


@dataclass
class RunResult:
    report: RunReport
    store: TraceStore
    outcome: RunOutcome


def _run_id(config: StampedeConfig) -> str:
    """Deterministic run id from seed + config — no wall clock (NFR-REPRO-01)."""
    blob = config.model_dump_json().encode()
    short = hashlib.blake2b(blob, digest_size=4).hexdigest()
    return f"run_seed{config.seed}_{short}"


def _select_brain(config: StampedeConfig, dry_run: bool) -> Brain:
    if dry_run:
        return HeuristicBrain()
    # Live mode (experimental v0.1): one provider for the swarm, from the first model.
    first = config.population.models[0] if config.population.models else "dry-run:heuristic"
    provider_name = first.split(":", 1)[0]
    if provider_name in {"dry-run", "heuristic"}:
        return HeuristicBrain()
    return LLMBrain(build_provider(provider_name))


async def run_simulation(
    config: StampedeConfig, *, dry_run: bool = True, target: TargetAdapter | None = None
) -> RunResult:
    run_id = _run_id(config)
    store = TraceStore(config.report.trace_db if not dry_run else ":memory:")
    tracer = Tracer(store, run_id=run_id, seed=config.seed)

    # 1. Safety Gate — before anything connects (ADR-6). ``target`` may be supplied
    # directly (embedding / tests); otherwise it's built from config.
    if target is None:
        target = build_target(config.target)
    gate = SafetyGate(config.safety)
    posture = gate.check(target.safety_descriptor())  # raises SafetyViolation if blocked

    # 2. Discover the target surface.
    toolset = await target.discover()

    # 3. Goal synthesis (intent-labeled).
    goals = synthesize(
        toolset,
        extra=config.goals.extra,
        mode=config.goals.mode,
        count=max(12, min(config.population.size, 64)),
        seed=config.seed,
    )

    # 4. Build the population.
    pack = load_pack(config.population.pack)
    agents = build_population(
        pack=pack,
        mix=config.population.mix,
        size=config.population.size,
        models=config.population.models,
        goals=goals,
        seed=config.seed,
    )

    # 5. Orchestrate under chaos.
    brain = _select_brain(config, dry_run)
    orch = Orchestrator(
        target=target,
        tracer=tracer,
        brain=brain,
        chaos=ChaosPolicy(config.chaos),
        budget_usd=config.report.budget_usd,
    )
    try:
        outcome = await orch.run(
            agents,
            toolset,
            curve=config.concurrency.curve,
            peak=config.concurrency.peak or config.population.size,
            hold=config.concurrency.hold,
            seed=config.seed,
            safety=posture,
        )
    finally:
        await target.aclose()

    # 6. Aggregate the Agent Readiness Report.
    report = build_report(config=config, agents=agents, outcome=outcome, store=store, run_id=run_id)
    store.commit()
    return RunResult(report=report, store=store, outcome=outcome)


def plan_cost(config: StampedeConfig) -> dict:
    """`stampede plan` — a pre-run cost estimate (FR-CLI-05), no target contact.

    Estimates modeled tokens per agent from token_budget and an expected turn count
    (1 + patience × chaos rate), priced per model binding."""
    from stampede.personas.loader import load_pack, sample_mix
    from stampede.population.agent import ModelBinding

    pack = load_pack(config.population.pack)
    personas = sample_mix(pack, config.population.mix, config.population.size, config.seed)
    models = config.population.models or ["dry-run:heuristic"]
    chaos_rate = config.chaos.rate if config.chaos.inject else 0.0

    total = 0.0
    per_persona: dict[str, float] = {}
    for i, persona in enumerate(personas):
        binding = ModelBinding.parse(models[i % len(models)])
        budget = max(persona.temperament.token_budget, 200)
        est_turns = 1.0 + persona.temperament.patience * chaos_rate
        in_tok = int((budget // 20) * est_turns)
        out_tok = int((budget // 100) * est_turns)
        c = cost_usd(binding.provider, binding.model, in_tok, out_tok)
        total += c
        per_persona[persona.name] = per_persona.get(persona.name, 0.0) + c

    return {
        "estimated_usd": round(total, 4),
        "budget_usd": config.report.budget_usd,
        "within_budget": total <= config.report.budget_usd,
        "per_persona_usd": {k: round(v, 4) for k, v in sorted(per_persona.items())},
        "size": config.population.size,
        "models": models,
    }


STARTER_YAML = """\
# stampede.yaml — point a herd of realistic agents at your system.
# Docs: https://github.com/swarmproof/stampede   ·   Run: stampede run --dry-run

target:
  type: mock          # mock | mcp | http (evm in v0.2)
  world: crm          # for type: mock — try 'crm' (misuse) or 'payments' (exactly-once)
  # For a real MCP server instead:
  # type: mcp
  # transport: stdio
  # command: "python my_server.py"

population:
  size: 50
  mix:                # temperaments, not just models — this is the realism knob
    naive: 0.5
    expert: 0.2
    impatient: 0.15
    frugal: 0.1
    adversarial: 0.05
  models:             # provider-agnostic; --dry-run ignores providers, keeps the mix
    - dry-run:heuristic
    # - anthropic:claude-haiku
    # - openai:gpt-4o-mini
    # - ollama:llama3

goals:
  autogenerate: true
  mode: template      # template = deterministic (dry-run); llm = model-derived
  extra:
    - "Archive the oldest inactive record but keep it recoverable"

concurrency:
  curve: ramp         # ramp | spike | steady
  peak: 50
  hold: 30s

chaos:
  kill_agents_at: [random]
  inject: [tool_timeout, rate_limit, malformed_output]
  rate: 0.15
  assert_recovery: true

safety:               # the swarm refuses to hit anything off this allowlist
  allow_targets: ["localhost:*", "127.0.0.1:*", "mock:*", "dry-run:*", "stdio:*"]
  acknowledge_non_production: false

report:
  out: ./stampede-report.html
  live: false
  budget_usd: 5.00

seed: 42
"""
