"""trace-format tests — run standalone so agent-reliability-core is self-verifying.

Imports only ``agent_reliability_core`` (no stampede), proving the primitive stands
on its own for the sibling repos that consume it."""

from __future__ import annotations

from agent_reliability_core.trace import (
    GenAI,
    Span,
    SpanKind,
    Swarmproof,
    Tracer,
    TraceStore,
    new_span_id,
    new_trace_id,
    traceparent,
)
from agent_reliability_core.trace.schema import REDACT_PLACEHOLDER


def test_ids_are_deterministic_and_w3c_sized():
    assert new_trace_id(42, 1) == new_trace_id(42, 1)
    assert new_trace_id(42, 1) != new_trace_id(42, 2)
    assert len(new_trace_id(42, 1)) == 32 and len(new_span_id(42, 1)) == 16


def test_traceparent_format():
    assert traceparent("a" * 32, "b" * 16) == f"00-{'a' * 32}-{'b' * 16}-01"


def test_redaction_targets_secrets_not_token_counts():
    s = Span(name="x", trace_id="t", span_id="s")
    s.set("api_key", "sk-secret")
    s.set(GenAI.USAGE_INPUT_TOKENS, 1200)
    assert s.attributes["api_key"] == REDACT_PLACEHOLDER
    assert s.attributes[GenAI.USAGE_INPUT_TOKENS] == 1200  # counts are not secrets


def test_store_roundtrip():
    store = TraceStore(":memory:")
    span = Span(name="chat", trace_id="t" * 32, span_id="s" * 16, kind=SpanKind.CLIENT)
    span.set(GenAI.REQUEST_MODEL, "claude-haiku")
    store.add(span)
    store.commit()
    got = store.all_spans()
    assert len(got) == 1 and got[0].attributes[GenAI.REQUEST_MODEL] == "claude-haiku"


def test_tracer_stamps_run_context_and_nests():
    store = TraceStore(":memory:")
    tracer = Tracer(store, run_id="run_1", seed=42)
    root = tracer.start("run", kind=SpanKind.INTERNAL)
    child = tracer.start("chat", parent=root, kind=SpanKind.CLIENT)
    tracer.end(child)
    tracer.end(root)
    assert child.trace_id == root.trace_id  # same trace
    assert child.parent_span_id == root.span_id  # nested
    assert child.attributes[Swarmproof.RUN_ID] == "run_1"
