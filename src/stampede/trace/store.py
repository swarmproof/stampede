"""SQLite trace store (FR-OB-02). Default, zero-config, WAL-mode.

Spans are the OTel-profile spans from :mod:`stampede.trace.schema`; the store is
an implementation detail behind the Tracer. WAL mode keeps high-cardinality span
writes from blocking dashboard reads. A Postgres adapter is a v0.2 concern; the
query surface here is deliberately small so it can be reimplemented.

Times are **virtual ticks** (SimClock), not wall clock — reports stay deterministic.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from stampede.trace.schema import Span, SpanKind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    span_id        TEXT PRIMARY KEY,
    trace_id       TEXT NOT NULL,
    parent_span_id TEXT,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL,
    service_name   TEXT NOT NULL,
    start_tick     INTEGER NOT NULL,
    end_tick       INTEGER NOT NULL,
    status         TEXT NOT NULL,
    status_message TEXT NOT NULL,
    attributes     TEXT NOT NULL,
    seq            INTEGER
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_seq ON spans(seq);
"""


class TraceStore:
    """Append + query spans. Use ``:memory:`` for tests, a path for real runs."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            # WAL keeps writers from blocking the dashboard's readers.
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._seq = 0

    def add(self, span: Span) -> None:
        self._seq += 1
        self._conn.execute(
            "INSERT OR REPLACE INTO spans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                span.span_id,
                span.trace_id,
                span.parent_span_id,
                span.name,
                span.kind.value,
                span.service_name,
                span.start_tick,
                span.end_tick,
                span.status,
                span.status_message,
                json.dumps(span.attributes, sort_keys=True, default=str),
                self._seq,
            ),
        )

    def add_many(self, spans: Iterable[Span]) -> None:
        for span in spans:
            self.add(span)
        self._conn.commit()

    def commit(self) -> None:
        self._conn.commit()

    def all_spans(self) -> list[Span]:
        rows = self._conn.execute("SELECT * FROM spans ORDER BY seq").fetchall()
        return [_row_to_span(r) for r in rows]

    def iter_spans(self) -> Iterator[Span]:
        for r in self._conn.execute("SELECT * FROM spans ORDER BY seq"):
            yield _row_to_span(r)

    def recent(self, limit: int = 200) -> list[Span]:
        """Rolling window for the dashboard — newest spans, oldest-first."""
        rows = self._conn.execute(
            "SELECT * FROM spans ORDER BY seq DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_span(r) for r in reversed(rows)]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0])

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> TraceStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _row_to_span(r: sqlite3.Row) -> Span:
    attrs: dict[str, Any] = json.loads(r["attributes"])
    return Span(
        name=r["name"],
        trace_id=r["trace_id"],
        span_id=r["span_id"],
        parent_span_id=r["parent_span_id"],
        kind=SpanKind(r["kind"]),
        service_name=r["service_name"],
        start_tick=r["start_tick"],
        end_tick=r["end_tick"],
        attributes=attrs,
        status=r["status"],
        status_message=r["status_message"],
    )
