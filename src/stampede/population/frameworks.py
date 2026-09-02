"""Framework adapters (FR — v0.3) — drive the swarm with the *user's own* agent.

Respecting NG-3 (stampede drives agents, it doesn't help you build them), a
framework adapter lets you plug an agent you already have — a LangGraph graph, a
CrewAI crew, or any callable — in as the swarm's brain. stampede still owns the
population (personas, goals), the target, chaos, and the report; your agent just
makes the tool decision.

The contract is framework-agnostic: an ``AgentFn`` is given the goal text and the
target's tools and returns which tool to call. :func:`langgraph_agent_fn` adapts a
LangGraph react agent to it; the same ``FrameworkBrain`` wraps any ``AgentFn``.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Union

from stampede.population.agent import Agent
from stampede.population.brain import Decision, Observation
from stampede.targets.base import ToolSet


@dataclass
class ToolInfo:
    """What the user's agent sees about one target tool."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class FrameworkDecision:
    """What the user's agent returns: the tool to call (or None to give up)."""

    tool: str | None
    arguments: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


# An agent function: (goal, tools) → a decision. Sync or async.
AgentFn = Callable[[str, list[ToolInfo]], Union["FrameworkDecision", Awaitable["FrameworkDecision"]]]


class FrameworkBrain:
    """Implements stampede's Brain by delegating the decision to an ``AgentFn``.

    Experimental / off the CI blocking path — a real framework run needs the
    framework + a model, like the LLM brain."""

    def __init__(self, agent_fn: AgentFn) -> None:
        self.agent_fn = agent_fn

    async def decide(self, agent: Agent, toolset: ToolSet, obs: Observation) -> Decision:
        tools = [ToolInfo(t.name, t.description, t.input_schema) for t in toolset.tools]
        try:
            result = self.agent_fn(agent.goal.text, tools)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # a framework hiccup fails THIS agent, not the run
            return Decision(tool=None, give_up=True, reasoning=f"framework error: {type(exc).__name__}: {exc}")
        return Decision(
            tool=result.tool,
            arguments=result.arguments,
            reasoning=result.reasoning or (f"agent chose {result.tool!r}" if result.tool else "no tool call"),
            give_up=result.tool is None,
        )


def langgraph_agent_fn(graph_factory: Callable[[list[Any]], Any]) -> AgentFn:
    """Adapt a LangGraph react agent to an ``AgentFn``.

    ``graph_factory(tools)`` must return a compiled graph bound to ``tools`` (e.g.
    ``langgraph.prebuilt.create_react_agent(llm, tools)``). The tools we pass are
    **capture stubs**: the graph "calls" them, we record the first call, and stampede
    executes the real tool on the target — so the agent's behaviour is measured while
    stampede keeps ownership of side effects. Needs ``langchain-core`` + ``langgraph``.
    """

    async def agent_fn(goal: str, tools: list[ToolInfo]) -> FrameworkDecision:
        from langchain_core.tools import StructuredTool  # lazy — optional dep
        from pydantic import create_model

        captured: list[tuple[str, dict[str, Any]]] = []

        def _stub(spec: ToolInfo) -> StructuredTool:
            def _call(**kwargs: Any) -> str:
                captured.append((spec.name, {k: v for k, v in kwargs.items() if v is not None}))
                return "ok"  # placeholder; stampede runs the real call on the target

            # Give the tool an args schema from the target's tool spec, so the agent's
            # LLM knows the parameters (and so the args survive validation on capture).
            props = (spec.input_schema or {}).get("properties", {})
            kwargs: dict[str, Any] = {}
            if props:
                fields: dict[str, Any] = {str(name): (Any, None) for name in props}
                kwargs["args_schema"] = create_model(f"{spec.name}_Args", **fields)
            return StructuredTool.from_function(
                _call, name=spec.name, description=spec.description, **kwargs
            )

        graph = graph_factory([_stub(t) for t in tools])
        await graph.ainvoke({"messages": [("user", goal)]})
        if not captured:
            return FrameworkDecision(tool=None, reasoning="langgraph agent made no tool call")
        name, args = captured[0]
        return FrameworkDecision(tool=name, arguments=args, reasoning=f"langgraph agent called {name!r}")

    return agent_fn


def _import_ref(ref: str) -> Any:
    """Import ``"package.module:attr"`` and return the attribute."""
    if ":" not in ref:
        raise ValueError(f"framework_ref must be 'module:attr', got {ref!r}")
    module_name, attr = ref.split(":", 1)
    return getattr(importlib.import_module(module_name), attr)


def build_framework_brain(framework: str, ref: str) -> FrameworkBrain:
    """Load the user's agent from ``ref`` and wrap it per ``framework``."""
    target = _import_ref(ref)
    if framework == "langgraph":
        # ref is a graph_factory(tools) -> compiled graph.
        return FrameworkBrain(langgraph_agent_fn(target))
    if framework == "callable":
        # ref is already an AgentFn.
        return FrameworkBrain(target)
    raise ValueError(f"unknown framework {framework!r} (use 'langgraph' or 'callable')")
