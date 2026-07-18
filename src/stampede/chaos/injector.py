"""The fault library + policy (FR-CH-01/02/03), config-driven via ``chaos:``."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

from stampede.config import ChaosConfig


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

    def kill_step_for(self, rng: random.Random, max_steps: int) -> int | None:
        """Precompute at which step (if any) this agent is killed — once, seeded."""
        if not self.kill_spec:
            return None
        if any(s == "random" for s in self.kill_spec):
            if rng.random() < self.KILL_FRACTION:
                return rng.randint(0, max(max_steps - 1, 0))
            return None
        ints = [int(s) for s in self.kill_spec if isinstance(s, int)]
        return ints[0] if ints else None

    def before_invoke(self, rng: random.Random) -> ChaosAction:
        """Pick a fault (or PASS) for one invocation."""
        if not self.enabled or rng.random() >= self.rate:
            return ChaosAction(FaultKind.PASS)
        kind = self.enabled[rng.randrange(len(self.enabled))]
        latency = rng.randint(200, 1500) if kind is FaultKind.DELAY else 0
        return ChaosAction(kind, latency)
