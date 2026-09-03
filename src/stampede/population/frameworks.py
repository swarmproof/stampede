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


class ToolCapture:
    """Records tool calls a framework agent makes against capture-stub tools and
    yields the first as a decision. Framework-agnostic — LangGraph and CrewAI both
    accept LangChain tools, so they share this. Independently unit-testable."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def record(self, name: str, args: dict[str, Any]) -> None:
        self.calls.append((name, {k: v for k, v in args.items() if v is not None}))

    def stub_tools(self, tools: list[ToolInfo]) -> list[Any]:
        """Build LangChain StructuredTools that record calls instead of executing —
        stampede runs the real call on the target. Each carries an args schema from
        the target spec so the agent's LLM knows the parameters."""
        from langchain_core.tools import StructuredTool  # lazy — optional dep
        from pydantic import create_model

        def _stub(spec: ToolInfo) -> StructuredTool:
            def _call(**kwargs: Any) -> str:
                self.record(spec.name, kwargs)
                return "ok"

            props = (spec.input_schema or {}).get("properties", {})
            extra: dict[str, Any] = {}
            if props:
                fields: dict[str, Any] = {str(name): (Any, None) for name in props}
                extra["args_schema"] = create_model(f"{spec.name}_Args", **fields)
            return StructuredTool.from_function(
                _call, name=spec.name, description=spec.description, **extra
            )

        return [_stub(t) for t in tools]

    def decision(self, framework: str) -> FrameworkDecision:
        if not self.calls:
            return FrameworkDecision(tool=None, reasoning=f"{framework} agent made no tool call")
        name, args = self.calls[0]
        return FrameworkDecision(tool=name, arguments=args, reasoning=f"{framework} agent called {name!r}")


def _capture_agent_fn(
    run: Callable[[str, list[Any]], Any], framework: str
) -> AgentFn:
    """Build an AgentFn that runs a framework agent over capture stubs. ``run(goal,
    stub_tools)`` performs the framework-specific invocation (sync or async)."""

    async def agent_fn(goal: str, tools: list[ToolInfo]) -> FrameworkDecision:
        capture = ToolCapture()
        result = run(goal, capture.stub_tools(tools))
        if inspect.isawaitable(result):
            await result
        return capture.decision(framework)

    return agent_fn


def langgraph_agent_fn(graph_factory: Callable[[list[Any]], Any]) -> AgentFn:
    """Adapt a LangGraph react agent. ``graph_factory(tools)`` returns a compiled
    graph (e.g. ``langgraph.prebuilt.create_react_agent(llm, tools)``). Needs
    ``langchain-core`` + ``langgraph``."""

    def run(goal: str, stubs: list[Any]) -> Any:
        return graph_factory(stubs).ainvoke({"messages": [("user", goal)]})

    return _capture_agent_fn(run, "langgraph")


def crewai_agent_fn(crew_factory: Callable[[list[Any], str], Any]) -> AgentFn:
    """Adapt a CrewAI crew. ``crew_factory(tools, goal)`` returns a Crew whose agent
    is bound to ``tools`` and tasked with ``goal``; we ``kickoff()`` it and capture
    the first tool call. CrewAI accepts LangChain tools, so the stubs are shared.
    Needs ``crewai`` (+ ``langchain-core``)."""

    def run(goal: str, stubs: list[Any]) -> Any:
        return crew_factory(stubs, goal).kickoff()

    return _capture_agent_fn(run, "crewai")


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
    if framework == "crewai":
        # ref is a crew_factory(tools, goal) -> Crew.
        return FrameworkBrain(crewai_agent_fn(target))
    if framework == "callable":
        # ref is already an AgentFn.
        return FrameworkBrain(target)
    raise ValueError(f"unknown framework {framework!r} (use 'langgraph', 'crewai', or 'callable')")
