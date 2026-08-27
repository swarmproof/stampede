"""The fault library + policy (FR-CH-01/02/03), config-driven via ``chaos:``.

A policy is normally built from the ``chaos:`` config (random faults at a rate). It
can also *replay a real incident* (FR-CH-05): :meth:`ChaosPolicy.apply_incident`
rewrites the policy to inject the incident's exact fault mix — each fault weighted by
its blast radius — so you can point last month's outage at your current stack.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from stampede.config import ChaosConfig

if TYPE_CHECKING:
    from stampede.chaos.incident import Incident


class FaultKind(StrEnum):
    PASS = "pass"
    FAIL = "fail"  # tool_failure
    TIMEOUT = "timeout"  # tool_timeout
    DELAY = "delay"  # latency degradation
    MANGLE = "mangle"  # malformed / contradictory output
    RATE_LIMIT = "rate_limit"  # ⊕ FR-CH-02
    KILL = "kill"  # agent kill


_INJECT_MAP = {
    "tool_timeout": FaultKind.TIMEOUT,
    "tool_failure": FaultKind.FAIL,
    "latency": FaultKind.DELAY,
    "malformed_output": FaultKind.MANGLE,
    "rate_limit": FaultKind.RATE_LIMIT,
}


@dataclass
class ChaosAction:
    kind: FaultKind
    latency_ticks: int = 0

    @property
    def is_fault(self) -> bool:
        return self.kind is not FaultKind.PASS


class ChaosPolicy:
    """Decides, deterministically from a seeded RNG, what chaos does to a call."""

    # Fraction of "random" kills — a quarter of agents get killed once mid-run.
    KILL_FRACTION = 0.25

    def __init__(self, config: ChaosConfig) -> None:
        self.enabled = [_INJECT_MAP[x] for x in config.inject if x in _INJECT_MAP]
        self.rate = config.rate
        self.kill_spec = config.kill_agents_at
        self.assert_recovery = config.assert_recovery
        # Incident-replay extras (defaults = config-driven behaviour).
        self.weights: list[float] | None = None  # per-fault blast radii when replaying
        self.kill_fraction = self.KILL_FRACTION
        self.kill_at_step: int | None = None
        self.incident: dict[str, str] | None = None  # id/title when replaying an incident

    def apply_incident(self, incident: Incident) -> ChaosPolicy:
        """Rewrite this policy to replay ``incident``'s fault mix (FR-CH-05)."""
        invoke = [(f.kind, f.blast_radius) for f in incident.faults if f.kind in _INJECT_MAP]
        self.enabled = [_INJECT_MAP[k] for k, _ in invoke]
        self.weights = [w for _, w in invoke] or None
        self.rate = min(1.0, sum(w for _, w in invoke))
        kill = next((f for f in incident.faults if f.kind in ("agent_kill", "kill")), None)
        self.kill_spec = ["random"] if kill else []
        self.kill_fraction = kill.blast_radius if kill else self.KILL_FRACTION
        self.kill_at_step = kill.at_step if kill else None
        self.incident = {"id": incident.id, "title": incident.title}
        return self

    def kill_step_for(self, rng: random.Random, max_steps: int) -> int | None:
        """Precompute at which step (if any) this agent is killed — once, seeded."""
        if not self.kill_spec:
            return None
        if any(s == "random" for s in self.kill_spec):
            if rng.random() < self.kill_fraction:
                # An incident may pin the kill to a specific step; else pick one.
                if self.kill_at_step is not None:
                    return min(self.kill_at_step, max(max_steps - 1, 0))
                return rng.randint(0, max(max_steps - 1, 0))
            return None
        ints = [int(s) for s in self.kill_spec if isinstance(s, int)]
        return ints[0] if ints else None

    def before_invoke(self, rng: random.Random) -> ChaosAction:
        """Pick a fault (or PASS) for one invocation."""
        if not self.enabled or rng.random() >= self.rate:
            return ChaosAction(FaultKind.PASS)
        kind = _weighted_choice(self.enabled, self.weights, rng)
        latency = rng.randint(200, 1500) if kind is FaultKind.DELAY else 0
        return ChaosAction(kind, latency)


def _weighted_choice(
    kinds: list[FaultKind], weights: list[float] | None, rng: random.Random
) -> FaultKind:
    if not weights:
        return kinds[rng.randrange(len(kinds))]
    total = sum(weights)
    draw = rng.random() * total
    cumulative = 0.0
    for kind, weight in zip(kinds, weights, strict=True):
        cumulative += weight
        if draw < cumulative:
            return kind
    return kinds[-1]
