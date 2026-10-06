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


# A plan function: (goal, tools) → the framework agent's FULL tool sequence. Sync/async.
PlanFn = Callable[[str, list["ToolInfo"]], "list[FrameworkDecision] | Awaitable[list[FrameworkDecision]]"]


class FrameworkBrain:
    """Implements stampede's Brain by delegating to the user's framework agent.

    Two shapes, both experimental / off the CI blocking path:

    * ``agent_fn`` — returns ONE decision per call (the ``callable`` framework).
    * ``plan_fn`` — returns the framework's FULL captured tool sequence; stampede's
      multi-step loop then executes it one call per step against the real target
      (``max_steps`` > 1). At ``max_steps == 1`` only the first call runs — exactly
      the original single-capture behaviour.

    The plan is formed against capture stubs, so it is the agent's *intended*
    sequence: it doesn't observe real intermediate results (that would need the
    framework to drive the target directly). Honest ceiling, noted in the guide.
    """

    def __init__(self, agent_fn: AgentFn | None = None, *, plan_fn: PlanFn | None = None) -> None:
        self.agent_fn = agent_fn
        self.plan_fn = plan_fn
        self._plans: dict[str, list[FrameworkDecision]] = {}

    async def decide(self, agent: Agent, toolset: ToolSet, obs: Observation) -> Decision:
        tools = [ToolInfo(t.name, t.description, t.input_schema) for t in toolset.tools]
        try:
            if self.plan_fn is not None:
                return await self._decide_from_plan(agent, tools, obs)
            if obs.turn > 0:  # single-decision agent: one reach, then done (like the heuristic)
                return Decision(tool=None, done=True, reasoning="framework agent: single decision complete")
            assert self.agent_fn is not None
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

    async def _decide_from_plan(self, agent: Agent, tools: list[ToolInfo], obs: Observation) -> Decision:
        if obs.turn == 0 or agent.id not in self._plans:
            assert self.plan_fn is not None
            plan = self.plan_fn(agent.goal.text, tools)
            if inspect.isawaitable(plan):
                plan = await plan
            self._plans[agent.id] = list(plan)
        plan = self._plans[agent.id]
        if not plan:
            return Decision(tool=None, give_up=True, reasoning="framework agent made no tool call")
        if obs.turn < len(plan):
            d = plan[obs.turn]
            return Decision(
                tool=d.tool,
                arguments=d.arguments,
                reasoning=d.reasoning or f"framework step {obs.turn}: {d.tool!r}",
            )
        return Decision(tool=None, done=True, reasoning=f"framework plan complete ({len(plan)} calls)")


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

    def decisions(self, framework: str) -> list[FrameworkDecision]:
        """Every captured call, in order — the framework's full tool sequence (multi-step)."""
        return [
            FrameworkDecision(tool=name, arguments=args, reasoning=f"{framework} agent called {name!r}")
            for name, args in self.calls
        ]


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


def _capture_plan_fn(run: Callable[[str, list[Any]], Any], framework: str) -> PlanFn:
    """Like :func:`_capture_agent_fn`, but returns the framework's FULL tool sequence
    (every captured call) so stampede's multi-step loop can replay it against the target."""

    async def plan_fn(goal: str, tools: list[ToolInfo]) -> list[FrameworkDecision]:
        capture = ToolCapture()
        result = run(goal, capture.stub_tools(tools))
        if inspect.isawaitable(result):
            await result
        return capture.decisions(framework)

    return plan_fn


def langgraph_plan_fn(graph_factory: Callable[[list[Any]], Any]) -> PlanFn:
    """Multi-step LangGraph: capture the graph's whole tool sequence, not just the first call."""

    def run(goal: str, stubs: list[Any]) -> Any:
        return graph_factory(stubs).ainvoke({"messages": [("user", goal)]})

    return _capture_plan_fn(run, "langgraph")


def crewai_plan_fn(crew_factory: Callable[[list[Any], str], Any]) -> PlanFn:
    """Multi-step CrewAI: capture the crew's whole tool sequence, not just the first call."""

    def run(goal: str, stubs: list[Any]) -> Any:
        return crew_factory(stubs, goal).kickoff()

    return _capture_plan_fn(run, "crewai")


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
        # ref is a graph_factory(tools) -> compiled graph. Multi-step replays its sequence.
        return FrameworkBrain(plan_fn=langgraph_plan_fn(target))
    if framework == "crewai":
        # ref is a crew_factory(tools, goal) -> Crew. Multi-step replays its sequence.
        return FrameworkBrain(plan_fn=crewai_plan_fn(target))
    if framework == "callable":
        # ref is already an AgentFn.
        return FrameworkBrain(target)
    raise ValueError(f"unknown framework {framework!r} (use 'langgraph', 'crewai', or 'callable')")
