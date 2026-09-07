"""The ``adversarial:economic`` cohort — costbomb-core embedded in stampede.

Two uses of costbomb-core:
1. **Playbook** — the cohort's goals come from costbomb's attack library (the named
   cost-explosion classes: retry-loop, tool-storm, context-bomb, recursion, …).
2. **Economic findings** — the report's ``adversarial.economic`` section is produced
   through costbomb's shared ``RunReport`` contract (``merge_economic_section``), with
   the headline **amplification factor** the crude ``cost > 2× mean`` flag lacks.

costbomb is an optional dependency; :func:`build_economic_section` is a no-op passthrough
when it isn't installed, so stampede's core never hard-depends on it.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stampede.population.agent import Agent


def economic_playbook(count: int = 5) -> list[str]:
    """Cost-explosion goal texts drawn from costbomb's attack library."""
    from costbomb.attacks import registry
    from costbomb.attacks.base import TargetCapabilities

    caps = TargetCapabilities(
        has_tools=True, can_spawn=True, accepts_documents=True,
        supports_reasoning=True, uses_cache=True, is_routed=True, has_retrieval=True,
    )
    texts: list[str] = []
    for attack in registry.all():
        for seed in attack.seeds(caps):
            texts.append(seed.text)
    return texts[:count]


def assign_economic_goals(agents: list[Agent], seed: int = 0) -> int:
    """Point the adversarial cohort at costbomb's cost-explosion playbook.

    Reassigns each adversarial agent's goal to a costbomb attack seed (round-robin),
    so the cohort actually *pursues* denial-of-wallet strategies rather than being
    detected after the fact. No-op (returns 0) when costbomb isn't installed or there
    is no adversarial cohort. Non-adversarial agents are untouched.
    """
    adv = [a for a in agents if a.is_adversarial]
    if not adv:
        return 0
    try:
        playbook = economic_playbook(count=max(len(adv), 10))
    except ImportError:
        return 0
    if not playbook:
        return 0

    from stampede.goals.schema import Goal, Intent

    for i, agent in enumerate(adv):
        agent.goal = Goal(
            id=f"g_econ_{agent.id}",
            text=playbook[i % len(playbook)],
            labeled=False,  # economic goals target cost, not the tool-misuse oracle
            intent=Intent(),
        )
    return len(adv)


def build_economic_section(agents: list[Agent], adversarial: dict[str, Any]) -> dict[str, Any]:
    """Enrich the ``adversarial`` report dict with costbomb's economic findings.

    Amplification = the worst adversarial agent's cost over a benign baseline (median
    of the non-adversarial cohort). Returns the merged dict; a passthrough if costbomb
    isn't installed or there is no adversarial cohort.
    """
    try:
        from costbomb._vendor.run_report import merge_economic_section
    except ImportError:
        return adversarial  # stampede[economic] not installed — leave base flags intact

    adv = [a for a in agents if a.is_adversarial]
    if not adv:
        return adversarial

    benign = [a.memory.cost_usd for a in agents if not a.is_adversarial]
    baseline = statistics.median(benign) if benign else min(a.memory.cost_usd for a in adv)
    baseline = max(baseline, 1e-9)

    ranked = sorted(adv, key=lambda a: a.memory.cost_usd, reverse=True)
    findings = [
        {
            "rank": i,
            "persona": a.persona.name,
            "cost_usd": round(a.memory.cost_usd, 6),
            "amplification_factor": round(a.memory.cost_usd / baseline, 2),
            "repro": {"goal": a.goal.text, "agent_id": a.id},
        }
        for i, a in enumerate(ranked, start=1)
    ]
    worst = ranked[0].memory.cost_usd
    economic = {
        "baseline_usd": round(baseline, 6),
        "worst_usd": round(worst, 6),
        "amplification_factor": round(worst / baseline, 2),
        "attack_classes": _attack_class_names(),
        "playbook": economic_playbook(),
        "findings": findings,
    }
    return merge_economic_section(adversarial, economic)


def _attack_class_names() -> list[str]:
    from costbomb.attacks import registry

    return registry.names()
