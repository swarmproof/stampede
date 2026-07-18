"""trace-format — the shared OpenTelemetry GenAI profile (FR-OB-01, ADR-1).

A stampede span *is* an OTel span: we populate the standard ``gen_ai.*`` GenAI
semantic-convention attributes and add a namespaced ``swarmproof.*`` extension
for population / persona / chaos / cost context that generic OTel backends ignore
harmlessly. This package owns the attribute registry (``schema``), the span model,
the SQLite trace store (``store``), and the tracer that the rest of the codebase
emits through (``tracer``). OTLP export to real OTel backends is an optional
adapter under the ``[otel]`` extra (``export``).
"""

from __future__ import annotations

from stampede.trace.schema import (
    GenAI,
    Span,
    SpanKind,
    SpanSide,
    Swarmproof,
    new_span_id,
    new_trace_id,
)
from stampede.trace.store import TraceStore
from stampede.trace.tracer import Tracer

__all__ = [
    "GenAI",
    "Span",
    "SpanKind",
    "SpanSide",
    "Swarmproof",
    "Tracer",
    "TraceStore",
    "new_span_id",
    "new_trace_id",
]
