"""Agent model + the Cairn six-state machine (FR-OR-03)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum

from stampede.goals.schema import Goal
from stampede.personas.schema import Persona


class AgentState(StrEnum):
    """Cairn's canonical six-state taxonomy (ARCHITECTURE §2.5)."""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    ACTING = "ACTING"
    WAITING = "WAITING"
    RECOVERING = "RECOVERING"
    DONE = "DONE"  # terminal (success)
    FAILED = "FAILED"  # terminal (failure)


_TERMINAL = {AgentState.DONE, AgentState.FAILED}

# Legal forward transitions. A kill from any non-terminal state → RECOVERING is
# handled separately in :meth:`StateMachine.kill`.
_LEGAL: dict[AgentState, set[AgentState]] = {
    AgentState.CREATED: {AgentState.PLANNING, AgentState.FAILED},
    AgentState.PLANNING: {AgentState.ACTING, AgentState.DONE, AgentState.FAILED},
    AgentState.ACTING: {AgentState.WAITING, AgentState.PLANNING, AgentState.DONE, AgentState.FAILED},
    AgentState.WAITING: {AgentState.PLANNING, AgentState.ACTING, AgentState.DONE, AgentState.FAILED},
    AgentState.RECOVERING: {
        AgentState.PLANNING,
        AgentState.ACTING,
        AgentState.DONE,
        AgentState.FAILED,
    },
    AgentState.DONE: set(),
    AgentState.FAILED: set(),
}


class TransitionError(Exception):
    """Raised on an illegal state transition."""


@dataclass
class StateMachine:
    state: AgentState = AgentState.CREATED
    history: list[AgentState] = field(default_factory=lambda: [AgentState.CREATED])

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL

    def transition(self, to: AgentState) -> None:
        if self.state in _TERMINAL:
            raise TransitionError(f"{self.state.value} is terminal; cannot move to {to.value}")
        if to not in _LEGAL[self.state]:
            raise TransitionError(f"illegal transition {self.state.value} → {to.value}")
        self.state = to
        self.history.append(to)

    def kill(self) -> bool:
        """Chaos kill: force RECOVERING from any non-terminal state. Idempotent-safe.

        Returns False if the agent had already terminated (nothing to kill)."""
        if self.state in _TERMINAL:
            return False
        self.state = AgentState.RECOVERING
        self.history.append(AgentState.RECOVERING)
        return True


@dataclass
class ModelBinding:
    """Provider-agnostic model reference parsed from ``"provider:model"``."""

    provider: str  # "anthropic" | "openai" | "ollama" | "dry-run" | "openai-compat"
    model: str
    raw: str

    @classmethod
    def parse(cls, spec: str) -> ModelBinding:
        if ":" in spec:
            provider, model = spec.split(":", 1)
        else:
            provider, model = "dry-run", spec
        return cls(provider=provider.strip(), model=model.strip(), raw=spec)


@dataclass
class AgentMemory:
    """Private, per-agent working memory + token accounting."""

    turns: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def record(self, entry: dict) -> None:
        self.turns.append(entry)


@dataclass
class Agent:
    id: str
    index: int
    persona: Persona
    binding: ModelBinding
    goal: Goal
    seed: int
    memory: AgentMemory = field(default_factory=AgentMemory)
    sm: StateMachine = field(default_factory=StateMachine)
    # Outcome fields, filled by the orchestrator.
    realized_tool: str | None = None  # the tool it actually called for its goal
    misuse: bool = False  # realized != intent on a labeled goal
    killed: bool = False
    recovered: bool = False
    _rng: random.Random | None = field(default=None, repr=False, compare=False)

    def rng(self) -> random.Random:
        """A *persistent* private RNG seeded from (run seed, agent index).

        Cached so successive draws advance one stream — reproducible per agent, and
        independent across agents so concurrency order never affects results."""
        if self._rng is None:
            self._rng = random.Random(self.seed ^ (self.index * 0x9E3779B1))
        return self._rng

    @property
    def is_adversarial(self) -> bool:
        return self.persona.is_adversarial
