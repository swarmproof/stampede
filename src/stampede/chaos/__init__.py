"""Chaos Injector + recovery assertion (FR-CH-*).

Wraps target invocations and agent lifecycles to inject failure — kills, timeouts,
tool failures, latency, malformed output, and rate-limiting (the top-impact fault
per ReliabilityBench) — then asserts recovery: did state survive, and did
side-effects fire *exactly once* after a kill + resume? All chaos draws come from a
dedicated per-agent RNG so the schedule is seeded and reproducible (FR-OR-06).
"""

from __future__ import annotations

from stampede.chaos.injector import ChaosAction, ChaosPolicy, FaultKind
from stampede.chaos.recovery import ExactlyOnceLedger, RecoveryAssertion, RecoveryFinding

__all__ = [
    "ChaosAction",
    "ChaosPolicy",
    "ExactlyOnceLedger",
    "FaultKind",
    "RecoveryAssertion",
    "RecoveryFinding",
]
