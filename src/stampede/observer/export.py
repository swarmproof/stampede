"""OTLP export of trace-format spans (FR-OB-05, NFR-INTEROP-01).

Because a stampede span *is* an OTel GenAI span, we can serialize the trace store
straight to the **OTLP/JSON** wire format and POST it to any collector's
``/v1/traces`` — preserving our deterministic trace/span ids and the parent/child
hierarchy exactly. (Virtual ticks map onto ``timeUnixNano`` from a zero epoch, so
absolute times are synthetic while durations are faithful — documented in
TEST-PLAN §10.)
"""

from __future__ import annotations

from typing import Any

from stampede.trace.schema import Span

_TICK_TO_NANOS = 1_000_000  # 1 virtual "tick" (a virtual ms) → 1e6 ns


def _attr_values(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, value in sorted(attributes.items()):
        out.append({"key": key, "value": _any_value(value)})
    return out


def _any_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, dict):
        return {"stringValue": _json(value)}
    return {"stringValue": str(value)}


def _json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, default=str)


_KIND = {"INTERNAL": 1, "SERVER": 2, "CLIENT": 3, "PRODUCER": 4, "CONSUMER": 5}


def to_otlp_json(spans: list[Span], service_name: str = "stampede") -> dict[str, Any]:
    """Build an OTLP/JSON ``TracesData`` document for ``spans``."""
    otlp_spans: list[dict[str, Any]] = []
    for s in spans:
        span_doc = {
            "traceId": s.trace_id,
            "spanId": s.span_id,
            "name": s.name,
            "kind": _KIND.get(s.kind.value, 1),
            "startTimeUnixNano": str(s.start_tick * _TICK_TO_NANOS),
            "endTimeUnixNano": str(s.end_tick * _TICK_TO_NANOS),
            "attributes": _attr_values(s.attributes),
            "status": {"code": 2 if s.status == "ERROR" else 1},
        }
        if s.parent_span_id:
            span_doc["parentSpanId"] = s.parent_span_id
        otlp_spans.append(span_doc)

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}}
                    ]
                },
                "scopeSpans": [
                    {"scope": {"name": "stampede", "version": "0.1.0"}, "spans": otlp_spans}
                ],
            }
        ]
    }


def export_otlp(spans: list[Span], endpoint: str, service_name: str = "stampede") -> int:
    """POST spans to an OTLP/HTTP collector (e.g. ``http://localhost:4318/v1/traces``).

    Returns the HTTP status code. Requires ``httpx`` (the ``[dev]`` extra)."""
    import httpx

    url = endpoint.rstrip("/")
    if not url.endswith("/v1/traces"):
        url = url + "/v1/traces"
    doc = to_otlp_json(spans, service_name)
    resp = httpx.post(url, json=doc, headers={"Content-Type": "application/json"}, timeout=30.0)
    return resp.status_code
