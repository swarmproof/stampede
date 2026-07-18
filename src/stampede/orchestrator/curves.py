"""Concurrency curves (FR-OR-01) — ``ramp`` / ``spike`` / ``steady``.

Produces a per-agent *arrival offset* on the virtual timeline. The executor caps
how many run at once (``peak``); the curve shapes when they arrive, which is what
gives the report its concurrency + latency-under-load story.
"""

from __future__ import annotations


def schedule_offsets(size: int, curve: str, peak: int, hold: int) -> list[int]:
    """Return a virtual-second arrival offset for each of ``size`` agents."""
    if size <= 0:
        return []
    span = max(hold, 1)  # arrival window in virtual seconds
    if curve == "steady":
        return [0] * size
    if curve == "spike":
        # A burst of ``peak`` at t=0, the remainder trailing at the window end.
        return [0 if i < peak else span for i in range(size)]
    if curve == "ramp":
        denom = max(size - 1, 1)
        return [int(span * i / denom) for i in range(size)]
    raise ValueError(f"unknown concurrency curve {curve!r} (ramp|spike|steady)")
