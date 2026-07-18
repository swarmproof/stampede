"""Population Factory + the Agent model (ARCHITECTURE §2.4).

Instantiates N heterogeneous, stateful agents from a persona pack, a goal set and a
model list. The agent's *imperfection is the product*: temperament drives how it
misreads and misuses the target. Each agent carries a private memory, a model
binding (provider-agnostic), a goal, and a six-state machine (dogfooding Cairn).
"""

from __future__ import annotations

from stampede.population.agent import (
    Agent,
    AgentMemory,
    AgentState,
    ModelBinding,
    StateMachine,
    TransitionError,
)
from stampede.population.factory import PopulationFactory, build_population

__all__ = [
    "Agent",
    "AgentMemory",
    "AgentState",
    "ModelBinding",
    "PopulationFactory",
    "StateMachine",
    "TransitionError",
    "build_population",
]
