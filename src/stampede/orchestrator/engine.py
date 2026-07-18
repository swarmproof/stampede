"""The Orchestrator engine (FR-OR-*) — drive the swarm, record everything.

Runs every agent concurrently through the Cairn six-state machine, wrapping each
tool invocation in chaos and emitting the trace-format span hierarchy
(``run → invoke_agent → chat / execute_tool → recovery.assertion``). Owns misuse
detection (ADR-5), the per-turn cost meter + ``budget_usd`` hard-stop (FR-OR-07),
and the exactly-once recovery check after a kill.

A single agent that raises never aborts the run (NFR-REL-01): its coroutine is
isolated by the executor and its partial state still lands in the report.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from stampede.chaos.injector import ChaosAction, ChaosPolicy, FaultKind
from stampede.chaos.recovery import RecoveryAssertion, RecoveryReport
from stampede.orchestrator.clock import AgentClock
from stampede.orchestrator.curves import schedule_offsets
from stampede.orchestrator.scheduler import AsyncioExecutor, Executor
from stampede.population.agent import Agent, AgentState
from stampede.population.brain import Brain, Observation
from stampede.population.providers import cost_usd
from stampede.targets.base import AgentContext, IsolationMode, TargetAdapter, ToolCall, ToolSet
from stampede.targets.safety import SafetyPosture
from stampede.trace.schema import GenAI, SpanKind, SpanSide, Swarmproof
from stampede.trace.tracer import Tracer

_THINK_LATENCY = 20  # virtual ticks for a planning/chat turn
_TIMEOUT_LATENCY = 30_000  # a timeout looks like a very slow call


@dataclass
class RunOutcome:
    agents: list[Agent]
    recovery: RecoveryReport
    safety: SafetyPosture | None
    total_usd: float = 0.0
    stopped_early: bool = False
    reason: str = ""
    faults_injected: dict[str, int] = field(default_factory=dict)


class _BudgetGuard:
    def __init__(self, cap_usd: float) -> None:
        self.cap = cap_usd
        self.spent = 0.0
        self._lock = asyncio.Lock()

    async def over(self) -> bool:
        async with self._lock:
            return self.spent >= self.cap

    async def add(self, amount: float) -> None:
        async with self._lock:
            self.spent += amount


class Orchestrator:
    def __init__(
        self,
        *,
        target: TargetAdapter,
        tracer: Tracer,
        brain: Brain,
        chaos: ChaosPolicy,
        budget_usd: float = 5.0,
        executor: Executor | None = None,
    ) -> None:
        self.target = target
        self.tracer = tracer
        self.brain = brain
        self.chaos = chaos
        self.executor = executor or AsyncioExecutor()
        self.budget = _BudgetGuard(budget_usd)
        self.recovery_assert = RecoveryAssertion()
        self._recovery = RecoveryReport()
        self._faults: dict[str, int] = {}
        self._isolation: IsolationMode = target.isolation()

    async def run(
        self,
        agents: list[Agent],
        toolset: ToolSet,
        *,
        curve: str,
        peak: int,
        hold: int,
        seed: int,
        safety: SafetyPosture | None = None,
    ) -> RunOutcome:
        offsets = schedule_offsets(len(agents), curve, peak, hold)

        root = self.tracer.start("run", kind=SpanKind.INTERNAL, start_tick=0)
        root.set("service.name", "stampede")
        self.tracer.end(root, end_tick=0)

        if safety is not None:
            gate = self.tracer.start("safety.gate", parent=root, start_tick=0)
            gate.set("swarmproof.safety.posture", safety.posture)
            gate.set("swarmproof.safety.endpoint", safety.endpoint)
            self.tracer.end(gate, end_tick=0)

        def _factory(agent: Agent, off: int) -> Callable[[], Awaitable[None]]:
            async def _run() -> None:
                await self._run_agent(agent, toolset, off, root.trace_id)

            return _run

        factories = [_factory(a, off) for a, off in zip(agents, offsets, strict=True)]
        await self.executor.run(factories, concurrency=peak)

        stopped = self.budget.spent >= self.budget.cap
        return RunOutcome(
            agents=agents,
            recovery=self._recovery,
            safety=safety,
            total_usd=round(self.budget.spent, 6),
            stopped_early=stopped,
            reason="budget_exhausted" if stopped else "",
            faults_injected=dict(self._faults),
        )

    # ---- per-agent lifecycle ----

    async def _run_agent(self, agent: Agent, toolset: ToolSet, offset: int, trace_id: str) -> None:
        clock = AgentClock(offset)
        chaos_rng = random.Random(agent.seed ^ (agent.index * 0x9E3779B1) ^ 0xC0FFEE)
        temp = agent.persona.temperament
        isolation_key = agent.id if self._isolation is IsolationMode.PER_AGENT else "shared"

        session = self.tracer.start(
            "invoke_agent",
            kind=SpanKind.CLIENT,
            trace_id=trace_id if trace_id else None,
            side=SpanSide.AGENT,
            start_tick=clock.now(),
        )
        session.set(GenAI.OPERATION_NAME, "invoke_agent")
        session.set(GenAI.AGENT_ID, agent.id)
        session.set(GenAI.AGENT_NAME, agent.persona.name)
        session.set(GenAI.PROVIDER_NAME, agent.binding.provider)
        session.set(GenAI.REQUEST_MODEL, agent.binding.model)
        session.set(Swarmproof.PERSONA_NAME, agent.persona.name)
        session.set(Swarmproof.PERSONA_PACK, agent.persona.pack)
        session.set(Swarmproof.AGENT_TEMPERAMENT, temp.model_dump())
        session.set(Swarmproof.GOAL_ID, agent.goal.id)
        session.set(Swarmproof.GOAL_INTENT_EXPECTED_TOOL, agent.goal.intent.expected_tool)
        session.set(Swarmproof.GOAL_INTENT_LABELED, agent.goal.labeled)

        # Graceful stop: if the budget is already gone, don't spend — fail cleanly.
        if await self.budget.over():
            agent.sm.transition(AgentState.FAILED)
            self._finish_session(session, agent, clock, reason="budget")
            return

        try:
            await self._drive(agent, toolset, session, clock, chaos_rng, isolation_key)
        except Exception as exc:  # isolate: one agent crashing never aborts the run
            if not agent.sm.terminal:
                with contextlib.suppress(Exception):
                    agent.sm.transition(AgentState.FAILED)
            self._finish_session(session, agent, clock, reason=f"crash:{type(exc).__name__}")
            return

        self._finish_session(session, agent, clock)

    async def _drive(self, agent, toolset, session, clock, chaos_rng, isolation_key) -> None:
        temp = agent.persona.temperament
        agent.sm.transition(AgentState.PLANNING)

        # One decision (the tool choice) — the chat turn.
        obs = Observation(turn=0)
        chat = self.tracer.start(
            "chat", kind=SpanKind.CLIENT, parent=session, side=SpanSide.AGENT, start_tick=clock.now()
        )
        chat.set(GenAI.OPERATION_NAME, "chat")
        chat.set(GenAI.PROVIDER_NAME, agent.binding.provider)
        chat.set(GenAI.REQUEST_MODEL, agent.binding.model)
        decision = await self.brain.decide(agent, toolset, obs)
        clock.advance(_THINK_LATENCY)
        chat.set(GenAI.USAGE_INPUT_TOKENS, decision.input_tokens)
        chat.set(GenAI.USAGE_OUTPUT_TOKENS, decision.output_tokens)
        chat.set(Swarmproof.DECISION_REASONING, decision.reasoning)
        turn_cost = cost_usd(
            agent.binding.provider, agent.binding.model, decision.input_tokens, decision.output_tokens
        )
        chat.set(Swarmproof.COST_USD, round(turn_cost, 6))
        self.tracer.end(chat, end_tick=clock.now())
        await self._account(agent, decision.input_tokens, decision.output_tokens, turn_cost)

        agent.realized_tool = decision.tool
        # Misuse (ADR-5): labeled goal + realized tool ≠ expected tool.
        if agent.goal.labeled and decision.tool != agent.goal.intent.expected_tool:
            agent.misuse = True

        if decision.tool is None or decision.give_up:
            agent.sm.transition(AgentState.FAILED)
            return

        spec = toolset.get(decision.tool)
        call = ToolCall(tool=decision.tool, arguments=decision.arguments)

        # Precompute the (seeded) kill step for this agent.
        max_steps = temp.patience + 1
        kill_step = self.chaos.kill_step_for(chaos_rng, max_steps)

        fires = 0
        side_effect_key: str | None = None
        was_killed = False
        succeeded = False

        def track_fire(res) -> None:
            nonlocal fires, side_effect_key
            if spec is not None and spec.idempotency_arg and res.ok:
                side_effect_key = str(
                    decision.arguments.get(spec.idempotency_arg) or f"{agent.id}:{decision.tool}"
                )
                if not res.side_effect_deduped:
                    fires += 1

        agent.sm.transition(AgentState.ACTING)
        attempt = 0
        while attempt <= temp.patience and not agent.sm.terminal:
            # Budget guard between turns (≤ one in-flight turn overrun, NFR-COST-01).
            if attempt > 0 and await self.budget.over():
                break

            action = self.chaos.before_invoke(chaos_rng)
            if action.is_fault:
                self._bump(action.kind.value)

            result, latency = await self._invoke_with_chaos(
                call, agent, spec, isolation_key, action, clock, session
            )
            clock.advance(latency)
            track_fire(result)
            agent.sm.transition(AgentState.WAITING)

            # Chaos kill AFTER this invoke — models a crash *after* a side-effect
            # commits but before the agent finalizes (the exactly-once hazard).
            if kill_step is not None and attempt == kill_step and not was_killed:
                was_killed = True
                agent.killed = True
                self._bump("agent_kill")
                self._emit_kill_span(session, clock, agent)
                agent.sm.kill()  # → RECOVERING
                if not self.chaos.assert_recovery:
                    agent.sm.transition(AgentState.FAILED)
                    break
                # Recovery: re-attempt the same call once. A good target dedupes
                # (fires stays 1); a broken one double-fires → recovery.violation.
                agent.recovered = True
                agent.sm.transition(AgentState.ACTING)
                rresult, rlat = await self._invoke_with_chaos(
                    call, agent, spec, isolation_key, ChaosAction(FaultKind.PASS), clock, session
                )
                clock.advance(rlat)
                track_fire(rresult)
                agent.sm.transition(AgentState.WAITING)
                succeeded = rresult.ok
                agent.sm.transition(AgentState.DONE if succeeded else AgentState.FAILED)
                break

            if result.ok and not action.is_fault:
                succeeded = True
                agent.sm.transition(AgentState.DONE)
                break

            # Failure → retry per policy/patience, else fail.
            attempt += 1
            if temp.retry_policy == "none" or attempt > temp.patience:
                agent.sm.transition(AgentState.FAILED)
                break
            agent.sm.transition(AgentState.PLANNING)
            agent.sm.transition(AgentState.ACTING)
            obs.last_error = result.error

        if not agent.sm.terminal:
            agent.sm.transition(AgentState.DONE if succeeded else AgentState.FAILED)

        # Recovery findings.
        if was_killed:
            self._recovery.findings.append(
                self.recovery_assert.check_state_survived(agent.id, agent.sm.terminal)
            )
        if side_effect_key is not None and (was_killed or self.chaos.assert_recovery):
            self._recovery.findings.append(
                self.recovery_assert.check_exactly_once(agent.id, side_effect_key, fires, was_killed)
            )

    async def _invoke_with_chaos(self, call, agent, spec, isolation_key, action, clock, session):
        """Invoke the target, applying the chaos ``action``. Returns (result, latency)."""
        ctx = AgentContext(
            agent_id=agent.id,
            persona=agent.persona.name,
            isolation_key=isolation_key,
        )
        tool_span = self.tracer.start(
            "execute_tool",
            kind=SpanKind.CLIENT,
            parent=session,
            side=SpanSide.AGENT,
            start_tick=clock.now(),
        )
        tool_span.set(GenAI.OPERATION_NAME, "execute_tool")
        tool_span.set(GenAI.TOOL_NAME, call.tool)
        tool_span.set(GenAI.TOOL_TYPE, spec.tool_type if spec else "function")
        tool_span.set(GenAI.TOOL_CALL_ID, tool_span.span_id)
        ctx.traceparent = self.tracer.traceparent_for(tool_span)
        if action.is_fault:
            tool_span.set(Swarmproof.CHAOS_ACTION, action.kind.value)

        base_latency = 40 + (agent.index % 5) * 10

        # Faults that short-circuit the target entirely.
        if action.kind in (FaultKind.TIMEOUT, FaultKind.FAIL, FaultKind.RATE_LIMIT):
            from stampede.targets.base import ToolResult

            errmap = {
                FaultKind.TIMEOUT: ("tool call timed out", _TIMEOUT_LATENCY),
                FaultKind.FAIL: ("tool call failed", base_latency),
                FaultKind.RATE_LIMIT: ("rate limited (429)", base_latency),
            }
            msg, latency = errmap[action.kind]
            result = ToolResult(ok=False, is_error=True, error=msg, latency_ticks=latency)
            tool_span.set(Swarmproof.MISUSE_DETECTED, agent.misuse)
            self.tracer.end(tool_span, status="ERROR", message=msg, end_tick=clock.now() + latency)
            return result, latency

        result = await self.target.invoke(call, ctx)
        latency = base_latency + action.latency_ticks
        if action.kind is FaultKind.MANGLE and result.ok:
            result.content = "�garbled�" + result.content[::-1]
            result.structured = None

        tool_span.set(Swarmproof.MISUSE_DETECTED, agent.misuse)
        if spec is not None and spec.idempotency_arg:
            tool_span.set(Swarmproof.RECOVERY_EXACTLY_ONCE, not result.side_effect_deduped or result.ok)
        status = "OK" if result.ok else "ERROR"
        self.tracer.end(tool_span, status=status, message=result.error, end_tick=clock.now() + latency)
        return result, latency

    def _emit_kill_span(self, session, clock, agent) -> None:
        span = self.tracer.start(
            "chaos.kill", kind=SpanKind.INTERNAL, parent=session, start_tick=clock.now()
        )
        span.set(Swarmproof.CHAOS_ACTION, "kill")
        span.set(Swarmproof.AGENT_STATE, agent.sm.state.value)
        self.tracer.end(span, status="ERROR", message="agent killed by chaos", end_tick=clock.now())

    def _finish_session(self, session, agent, clock, reason: str = "") -> None:
        session.set(Swarmproof.AGENT_STATE, agent.sm.state.value)
        session.set("swarmproof.agent.misuse", agent.misuse)
        session.set("swarmproof.agent.killed", agent.killed)
        session.set("swarmproof.agent.recovered", agent.recovered)
        session.set(Swarmproof.COST_USD, round(agent.memory.cost_usd, 6))
        status = "OK" if agent.sm.state is AgentState.DONE else "ERROR"
        self.tracer.end(session, status=status, message=reason, end_tick=clock.now())

    async def _account(self, agent: Agent, in_tokens: int, out_tokens: int, cost: float) -> None:
        agent.memory.input_tokens += in_tokens
        agent.memory.output_tokens += out_tokens
        agent.memory.cost_usd += cost
        await self.budget.add(cost)

    def _bump(self, name: str) -> None:
        self._faults[name] = self._faults.get(name, 0) + 1
