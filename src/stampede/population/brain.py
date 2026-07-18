"""Agent 'brains' — how an agent chooses a tool for its goal.

Two implementations behind one interface:

* :class:`HeuristicBrain` — zero-LLM, deterministic (the ``--dry-run`` path and the
  bulk of the test pyramid). Temperament drives a *probabilistic-but-seeded* choice
  between the correct tool and its most **confusable** sibling, so a high-``misread``
  agent produces realistic misuse (archive→delete) rather than random noise.
* :class:`LLMBrain` — wraps a live :class:`~stampede.population.providers.ModelProvider`
  and lets the model pick the tool. Experimental in v0.1 (off the CI blocking path).

The brain only chooses the *action*; the orchestrator engine owns the retry/recover
loop and the state machine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from stampede.population.agent import Agent
from stampede.population.providers import ModelProvider
from stampede.targets.base import ToolSet, ToolSpec

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {"a", "an", "the", "to", "of", "for", "and", "or", "is", "it", "this", "from", "be"}


def _tokens(text: str) -> set[str]:
    return {t.rstrip("s") for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 2}


@dataclass
class Observation:
    turn: int
    last_error: str | None = None


@dataclass
class Decision:
    tool: str | None
    arguments: dict = field(default_factory=dict)
    reasoning: str = ""
    give_up: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class Brain(Protocol):
    async def decide(self, agent: Agent, toolset: ToolSet, obs: Observation) -> Decision: ...


def _confusable(expected: str, toolset: ToolSet) -> ToolSpec | None:
    """The tool most easily mistaken for ``expected`` — the misuse the agent makes."""
    exp = toolset.get(expected)
    if exp is None:
        return None
    exp_name, exp_desc = _tokens(exp.name), _tokens(exp.description)
    exp_args = set((exp.input_schema or {}).get("properties", {}))
    best: tuple[float, str] | None = None
    for other in toolset.tools:
        if other.name == expected:
            continue
        score = len(exp_name & _tokens(other.name)) * 2.0
        score += len(exp_desc & _tokens(other.description))
        score += 1.5 * len(exp_args & set((other.input_schema or {}).get("properties", {})))
        if exp.destructive and other.destructive:
            score += 1.0
        # Deterministic tiebreak by name so the pick is reproducible.
        cand = (score, other.name)
        if best is None or cand > best:
            best = cand
    if best is None:
        return None
    return toolset.get(best[1])


def _modeled_tokens(agent: Agent, toolset: ToolSet, turn: int) -> tuple[int, int]:
    """Deterministic per-turn token estimate. Ties spend to token_budget so the
    cost profile shows a real per-persona spread (naive burns more than expert)."""
    budget = max(agent.persona.temperament.token_budget, 200)
    inp = min(budget, budget // 20 + 40 * len(toolset.tools) + 20 * turn)
    out = budget // 100 + 8 * turn
    return inp, out


class HeuristicBrain:
    async def decide(self, agent: Agent, toolset: ToolSet, obs: Observation) -> Decision:
        temp = agent.persona.temperament
        inp, out = _modeled_tokens(agent, toolset, obs.turn)
        expected = agent.goal.intent.expected_tool

        # No labeled intent → best-effort match of goal text to a tool, no misuse signal.
        if not expected or toolset.get(expected) is None:
            picked = _match_by_text(agent.goal.text, toolset) or (
                toolset.tools[0].name if toolset.tools else None
            )
            return Decision(
                tool=picked,
                arguments=_args_for(picked, agent, toolset),
                reasoning=f"no labeled intent; matched goal text to {picked!r}",
                input_tokens=inp,
                output_tokens=out,
            )

        # p_correct blends how carefully the persona reads (misread) and how tightly
        # it sticks to the stated goal (adherence). Adversarial/drunk read loosely.
        base_correct = 1.0 - temp.misread_rate
        p_correct = base_correct * (0.5 + 0.5 * temp.goal_adherence)
        draw = agent.rng().random()

        if draw < p_correct:
            return Decision(
                tool=expected,
                arguments=_args_for(expected, agent, toolset),
                reasoning=f"goal intent is clear; {expected!r} is the right tool",
                input_tokens=inp,
                output_tokens=out,
            )

        wrong = _confusable(expected, toolset)
        if wrong is None:
            # Nothing to confuse it with → falls back to the right tool.
            return Decision(
                tool=expected,
                arguments=_args_for(expected, agent, toolset),
                reasoning=f"no confusable alternative; used {expected!r}",
                input_tokens=inp,
                output_tokens=out,
            )
        return Decision(
            tool=wrong.name,
            arguments=_args_for(wrong.name, agent, toolset),
            reasoning=(
                f"goal wanted {agent.goal.intent.expected_effect or expected!r}, but "
                f"{wrong.name!r} looked closest to me"
            ),
            input_tokens=inp,
            output_tokens=out,
        )


class LLMBrain:
    """Live brain (experimental v0.1). Not on the CI blocking path."""

    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider

    async def decide(self, agent: Agent, toolset: ToolSet, obs: Observation) -> Decision:
        tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in toolset.tools
        ]
        system = agent.persona.prompt_template or "Pursue your goal using the tools."
        user = agent.goal.text
        if obs.last_error:
            user += f"\n\n(Your previous attempt failed: {obs.last_error})"
        try:
            comp = await self.provider.complete(
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=tools,
                model=agent.binding.model,
                temperature=0.0,  # temp 0 for reproducibility within the noise band
            )
        except Exception as exc:
            # A provider hiccup (Ollama down, model missing, timeout) fails THIS
            # agent cleanly — the run and its report survive (NFR-REL-01).
            return Decision(
                tool=None,
                reasoning=f"provider error: {type(exc).__name__}: {exc}",
                give_up=True,
            )
        if not comp.tool_calls:
            return Decision(
                tool=None,
                reasoning=comp.text or "model returned no tool call",
                give_up=True,
                input_tokens=comp.input_tokens,
                output_tokens=comp.output_tokens,
            )
        call = comp.tool_calls[0]
        return Decision(
            tool=call.name,
            arguments=call.arguments,
            reasoning=comp.text or f"model chose {call.name!r}",
            input_tokens=comp.input_tokens,
            output_tokens=comp.output_tokens,
        )


class BrainPool:
    """Routes each agent to a brain by its model binding — enables model mixing.

    In ``--dry-run`` every agent uses the shared deterministic HeuristicBrain. In a
    live run, ``ollama:llama3`` agents get an ``LLMBrain`` over the Ollama provider
    while ``dry-run:heuristic`` agents in the same swarm stay heuristic. One live
    provider is built and cached per provider name.
    """

    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self._heuristic = HeuristicBrain()
        self._llm_by_provider: dict[str, LLMBrain] = {}

    def for_agent(self, agent: Agent) -> Brain:
        provider = agent.binding.provider
        if self.dry_run or provider in {"dry-run", "heuristic"}:
            return self._heuristic
        if provider not in self._llm_by_provider:
            from stampede.population.providers import build_provider

            self._llm_by_provider[provider] = LLMBrain(build_provider(provider))
        return self._llm_by_provider[provider]


def _match_by_text(text: str, toolset: ToolSet) -> str | None:
    goal_tokens = _tokens(text)
    best: tuple[int, str] | None = None
    for t in toolset.tools:
        overlap = len(goal_tokens & (_tokens(t.name) | _tokens(t.description)))
        cand = (overlap, t.name)
        if best is None or cand > best:
            best = cand
    return best[1] if best else None


def _args_for(tool: str | None, agent: Agent, toolset: ToolSet) -> dict:
    if tool is None:
        return {}
    spec = toolset.get(tool)
    if spec is None:
        return {}
    props = set((spec.input_schema or {}).get("properties", {}))
    # Prefer the goal's pre-computed args, filtered to what this tool accepts.
    args = {k: v for k, v in agent.goal.args.items() if k in props}
    # Fill any required arg the goal didn't provide, deterministically.
    for req in (spec.input_schema or {}).get("required", []):
        if req not in args:
            args[req] = f"{req}_{agent.index}"
    return args
