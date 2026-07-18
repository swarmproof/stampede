"""Recovery assertion + the exactly-once hook (FR-CH-04).

After a chaos kill + resume, two things must hold: the agent's state survived (it
reached a terminal state, not a hang), and any keyed side-effect fired **exactly
once**. The :class:`ExactlyOnceLedger` stands in for the ``exactly-once`` sibling
library's ``claim``/``commit`` surface; the assertion reads how many times each key
actually committed. A target that double-fires (exactly-once disabled) produces a
``recovery.violation`` — which is the negative test in TEST-PLAN §4.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ExactlyOnceLedger:
    """Minimal claim/commit ledger keyed by side-effect id (the exactly-once hook)."""

    def __init__(self) -> None:
        self._fires: dict[str, int] = {}

    def claim(self, key: str) -> bool:
        """True if this key has not yet committed (the side-effect may proceed)."""
        return self._fires.get(key, 0) == 0

    def commit(self, key: str) -> None:
        self._fires[key] = self._fires.get(key, 0) + 1

    def fires(self, key: str) -> int:
        return self._fires.get(key, 0)


@dataclass
class RecoveryFinding:
    agent_id: str
    kind: str  # "exactly_once" | "state_survived"
    ok: bool
    detail: str = ""


@dataclass
class RecoveryReport:
    findings: list[RecoveryFinding] = field(default_factory=list)

    @property
    def exactly_once_violations(self) -> list[RecoveryFinding]:
        return [f for f in self.findings if f.kind == "exactly_once" and not f.ok]

    @property
    def all_ok(self) -> bool:
        return all(f.ok for f in self.findings)


class RecoveryAssertion:
    """Turns per-agent side-effect fire counts into findings."""

    def check_exactly_once(
        self, agent_id: str, key: str, fires: int, was_killed: bool
    ) -> RecoveryFinding:
        ok = fires <= 1
        detail = (
            f"side-effect {key!r} fired {fires}× "
            f"{'after a kill' if was_killed else '(no kill)'}"
        )
        return RecoveryFinding(agent_id=agent_id, kind="exactly_once", ok=ok, detail=detail)

    def check_state_survived(self, agent_id: str, reached_terminal: bool) -> RecoveryFinding:
        return RecoveryFinding(
            agent_id=agent_id,
            kind="state_survived",
            ok=reached_terminal,
            detail="reached a terminal state" if reached_terminal else "did not terminate",
        )
