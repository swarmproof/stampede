"""The presentation model — a domain-agnostic report the renderers consume.

A tool maps its own domain report into this closed set of section shapes; core
renders it to HTML/terminal in the shared theme (ADR-4, FR-OB-04). ``Tone`` is the
single theming primitive — it resolves to a hex (HTML) and a Rich style (terminal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar, Literal


class Tone(StrEnum):
    NEUTRAL = "neutral"
    GOOD = "good"
    WARN = "warn"
    BAD = "bad"
    ACCENT = "accent"


@dataclass
class Badge:
    """A headline chip — e.g. a grade or pass/fail indicator."""

    value: str
    tone: Tone = Tone.ACCENT


@dataclass
class Kpi:
    value: str
    label: str
    tone: Tone = Tone.NEUTRAL


@dataclass
class Column:
    name: str
    align: Literal["left", "right"] = "left"


@dataclass
class Cell:
    """A table cell: text, optionally a 0..1 proportion ``bar``, tinted by ``tone``."""

    text: str = ""
    bar: float | None = None
    tone: Tone = Tone.NEUTRAL


# ---- sections (a closed union) ----


@dataclass
class KpiRow:
    kind: ClassVar[str] = "kpis"
    items: list[Kpi] = field(default_factory=list)


@dataclass
class Table:
    kind: ClassVar[str] = "table"
    title: str = ""
    columns: list[Column] = field(default_factory=list)
    rows: list[list[Cell]] = field(default_factory=list)


@dataclass
class Callout:
    """A lead sentence introducing what follows."""

    kind: ClassVar[str] = "callout"
    text: str = ""


@dataclass
class Note:
    """A compact status line (perf / chaos / realism)."""

    kind: ClassVar[str] = "note"
    text: str = ""
    tone: Tone = Tone.NEUTRAL


Section = KpiRow | Table | Callout | Note


@dataclass
class Report:
    title: str
    subtitle: str = ""
    badge: Badge | None = None
    sections: list[Section] = field(default_factory=list)
