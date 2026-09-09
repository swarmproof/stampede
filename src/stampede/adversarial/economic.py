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


def _cb_span_dict(span: Any) -> dict[str, Any]:
    """A stampede trace-format span → the dict costbomb's Span.from_dict expects.

    Both sides are the same OTel GenAI profile, so this is a field copy, not a
    translation.
    """
    kind = getattr(span.kind, "value", span.kind)
    return {
        "name": span.name,
        "trace_id": span.trace_id,
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "kind": kind,
        "service_name": getattr(span, "service_name", "stampede"),
        "start_tick": getattr(span, "start_tick", 0),
        "end_tick": getattr(span, "end_tick", 0),
        "attributes": dict(span.attributes),
        "status": getattr(span, "status", "OK"),
        "status_message": getattr(span, "status_message", ""),
    }


def metered_cohort(agents: list[Agent], store: Any) -> dict[str, dict[str, float]]:
    """Re-meter each adversarial agent's *real* trace with costbomb's meter.

    costbomb's sum-over-sources oracle (model tokens + tool fees + spawn roll-up, and
    the blast-radius extension) runs directly on stampede's spans — same OTel GenAI
    profile, no conversion beyond a field copy. Agents whose model costbomb can't price
    (e.g. the dry-run heuristic) are skipped, so this is purely additive. Returns
    ``{agent_id: {model_usd, tool_usd, total_usd, blast_radius_usd}}``.
    """
    try:
        from costbomb._vendor.trace import GenAI, Span, Trace
        from costbomb.meter import CostMeter
        from costbomb.pricing import PriceTable, UnpricedModelError
    except ImportError:
        return {}

    all_spans = list(store.all_spans())
    sessions = {
        s.attributes.get(GenAI.AGENT_ID): s
        for s in all_spans
        if s.attributes.get(GenAI.OPERATION_NAME) == "invoke_agent"
        and s.attributes.get(GenAI.AGENT_ID)
    }
    meter = CostMeter(PriceTable.default())
    out: dict[str, dict[str, float]] = {}
    for agent in agents:
        session = sessions.get(agent.id)
        if session is None:
            continue
        spans = [Span.from_dict(_cb_span_dict(s)) for s in all_spans if s.trace_id == session.trace_id]
        try:
            bd = meter.cost(Trace(root_span_id=session.span_id, spans=spans), annotate=False)
        except UnpricedModelError:
            continue  # dry-run/heuristic models aren't in the price table — skip, additive
        out[agent.id] = {
            "model_usd": bd.model_usd,
            "tool_usd": bd.tool_usd,
            "total_usd": bd.total_usd,
            "blast_radius_usd": bd.blast_radius_usd,
        }
    return out


def build_economic_section(
    agents: list[Agent], adversarial: dict[str, Any], store: Any = None
) -> dict[str, Any]:
    """Enrich the ``adversarial`` report dict with costbomb's economic findings.

    Amplification = the worst adversarial agent's cost over a benign baseline (median
    of the non-adversarial cohort). When ``store`` is given, each finding also carries
    costbomb's own metered breakdown of that agent's real trace (``metered``). A
    passthrough if costbomb isn't installed or there is no adversarial cohort.
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

    metered = metered_cohort(adv, store) if store is not None else {}
    ranked = sorted(adv, key=lambda a: a.memory.cost_usd, reverse=True)
    findings = []
    for i, a in enumerate(ranked, start=1):
        finding = {
            "rank": i,
            "persona": a.persona.name,
            "cost_usd": round(a.memory.cost_usd, 6),
            "amplification_factor": round(a.memory.cost_usd / baseline, 2),
            "repro": {"goal": a.goal.text, "agent_id": a.id},
        }
        if a.id in metered:  # costbomb's own sum-over-sources reading of the real trace
            finding["metered"] = {k: round(v, 6) for k, v in metered[a.id].items()}
        findings.append(finding)
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
