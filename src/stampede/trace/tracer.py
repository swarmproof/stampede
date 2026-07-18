"""The Tracer — the one place spans are minted (ARCHITECTURE.md §4.1, §2.7).

Every agent decision, tool call, result and failure flows through here. The Tracer
owns the deterministic id counter (so seeded runs are reproducible), stamps
``swarmproof.run.*`` context onto each span, reads virtual time from the SimClock,
and writes into the TraceStore. It also builds the W3C ``traceparent`` a target
adapter injects downstream so a trace-aware target's SERVER spans nest under our
CLIENT span in the same ``trace_id``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from stampede.trace.schema import (
    Span,
    SpanKind,
    SpanSide,
    Swarmproof,
    new_span_id,
    new_trace_id,
    traceparent,
)
from stampede.trace.store import TraceStore

if TYPE_CHECKING:
    pass


class Clock(Protocol):
    """Minimal virtual-clock surface the Tracer needs (see orchestrator.SimClock)."""

    def now(self) -> int: ...


class _ZeroClock:
    """Fallback clock for tests / trace use outside an orchestrated run."""

    def now(self) -> int:
        return 0


class Tracer:
    def __init__(
        self,
        store: TraceStore,
        run_id: str,
        seed: int,
        clock: Clock | None = None,
    ) -> None:
        self.store = store
        self.run_id = run_id
        self.seed = seed
        self.clock = clock or _ZeroClock()
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def new_trace(self) -> str:
        return new_trace_id(self.seed, self._next())

    def start(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        trace_id: str | None = None,
        parent: Span | None = None,
        side: SpanSide = SpanSide.AGENT,
        service_name: str = "stampede",
        start_tick: int | None = None,
    ) -> Span:
        """Open a span. Caller fills attributes, then calls :meth:`end`.

        ``start_tick`` lets the engine drive per-agent virtual time (deterministic
        under concurrency); it falls back to the shared clock when omitted."""
        tid = trace_id or (parent.trace_id if parent else self.new_trace())
        span = Span(
            name=name,
            trace_id=tid,
            span_id=new_span_id(self.seed, self._next()),
            parent_span_id=parent.span_id if parent else None,
            kind=kind,
            service_name=service_name,
            start_tick=start_tick if start_tick is not None else self.clock.now(),
        )
        # Stamp run context + the span side on every span (§4.1).
        span.set(Swarmproof.RUN_ID, self.run_id)
        span.set(Swarmproof.RUN_SEED, self.seed)
        span.set(Swarmproof.SPAN_SIDE, side.value)
        return span

    def end(
        self, span: Span, *, status: str = "OK", message: str = "", end_tick: int | None = None
    ) -> Span:
        span.end_tick = end_tick if end_tick is not None else self.clock.now()
        span.status = status
        span.status_message = message
        self.store.add(span)
        return span

    def traceparent_for(self, span: Span) -> str:
        """The ``traceparent`` to inject into a tool invocation for target nesting."""
        return traceparent(span.trace_id, span.span_id)
