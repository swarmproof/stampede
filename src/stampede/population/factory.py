"""Population Factory (FR-PF-01/02) — build N agents, deterministically."""

from __future__ import annotations

from stampede.goals.schema import Goal
from stampede.personas.loader import sample_mix
from stampede.personas.schema import PersonaPack
from stampede.population.agent import Agent, ModelBinding


class PopulationFactory:
    def build(
        self,
        *,
        pack: PersonaPack,
        mix: dict[str, float],
        size: int,
        models: list[str],
        goals: list[Goal],
        seed: int,
    ) -> list[Agent]:
        if not goals:
            raise ValueError("cannot build a population with no goals")
        if not models:
            models = ["dry-run:heuristic"]
        personas = sample_mix(pack, mix, size, seed)
        bindings = [ModelBinding.parse(models[i % len(models)]) for i in range(size)]
        agents: list[Agent] = []
        for i in range(size):
            agents.append(
                Agent(
                    id=f"agent-{i:04d}",
                    index=i,
                    persona=personas[i],
                    binding=bindings[i],
                    goal=goals[i % len(goals)],
                    seed=seed,
                )
            )
        return agents


def build_population(
    *,
    pack: PersonaPack,
    mix: dict[str, float],
    size: int,
    models: list[str],
    goals: list[Goal],
    seed: int,
) -> list[Agent]:
    return PopulationFactory().build(
        pack=pack, mix=mix, size=size, models=models, goals=goals, seed=seed
    )
