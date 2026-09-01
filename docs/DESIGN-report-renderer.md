# Design note — extracting the report-renderer primitive

Status: proposal · Date: 2026-09-05 · Companions: `ARCHITECTURE.md` (§2.7, §6, ADR-4), `PRD.md` (FR-OB-04)

The last of the four shared primitives (ADR-4). Unlike trace-format, concurrency-core, and persona-pack — which were dependency-light *leaves* that moved out mechanically — report-renderer needs a **real seam first**, because today's renderer is fused to stampede's domain model. This note defines that seam so the implementation is a follow-up, not a guess.

---

## 1. The problem

`observer/renderer.py` knows `RunReport` intimately — **17 direct references** to domain fields (`report.misuse_map`, `report.success`, `report.cost_profile`, `report.chaos`, `report.adversarial`, `report.realism`, …). The `report.html.j2` template hard-codes stampede's exact sections. So "report-renderer" cannot be lifted as-is: doing so would drag stampede's domain (`misuse map`, `persona success`, `denial-of-wallet`) into a package that mcp-probe and costbomb are supposed to share. Their reports have *different* sections.

**What is actually shared** is not the report — it's the **visual vocabulary**: a grade badge, a KPI row, tables (with bar and tag cells), a lead callout, and dim status notes, all in one oxblood-editorial theme, rendered to both HTML and terminal. Every tool in the portfolio composes *its own* sections from that vocabulary.

## 2. The seam

Split rendering into a domain-agnostic **presentation model** (in core) and a per-tool **adapter** (stays in each tool).

```
stampede RunReport ──adapter──▶ core.report.Report ──renderer──▶ HTML / terminal
(domain model)                  (presentation model)             (shared theme)
mcp-probe ProbeReport ─adapter─▶ core.report.Report ──────────────▶  "
costbomb  CostReport  ─adapter─▶ core.report.Report ──────────────▶  "
```

The domain models (`RunReport`, `build_report`, `to_dict`) **do not move and do not change** — the JSON contract and `--dry-run` determinism/golden snapshots are untouched. Only the *rendering path* changes.

## 3. The presentation model (`agent_reliability_core.report`)

A small, **closed** set of section shapes — enough for all three tools, simple enough to keep two renderers (HTML + terminal) trivial. `tone` is the one theming primitive; it maps to a hex in HTML and a Rich style in the terminal.

```python
class Tone(StrEnum):
    NEUTRAL = "neutral"; GOOD = "good"; WARN = "warn"; BAD = "bad"; ACCENT = "accent"

@dataclass
class Badge:                       # the grade chip
    value: str; tone: Tone = Tone.ACCENT

@dataclass
class Kpi:
    value: str; label: str; tone: Tone = Tone.NEUTRAL

@dataclass
class Cell:                        # a table cell: text, or a bar, or a tag
    text: str = ""
    bar: float | None = None       # 0..1 → a proportion bar (the misuse confusion column)
    tone: Tone = Tone.NEUTRAL

@dataclass
class Column:
    name: str; align: Literal["left", "right"] = "left"

# --- sections (a closed union) ---
@dataclass
class KpiRow:  items: list[Kpi]
@dataclass
class Table:   title: str; columns: list[Column]; rows: list[list[Cell]]
@dataclass
class Callout: text: str            # the lead sentence ("where agents called the wrong tool…")
@dataclass
class Note:    text: str; tone: Tone = Tone.NEUTRAL   # the dim one-liners (perf, chaos, realism)

Section = KpiRow | Table | Callout | Note

@dataclass
class Report:
    title: str
    subtitle: str = ""
    badge: Badge | None = None
    sections: list[Section] = field(default_factory=list)
```

Renderers + theme, also in core:

```python
@dataclass
class Theme:                        # oxblood-editorial by default; overridable
    ink: str; paper: str; accent: str; good: str; warn: str; bad: str; muted: str
    # + a terminal counterpart mapping Tone → Rich style

DEFAULT_THEME = Theme(accent="#6b1f2a", good="#2f7d4f", warn="#dfb317", bad="#b03030", ...)

def render_html(report: Report, theme: Theme = DEFAULT_THEME) -> str: ...
def render_terminal(report: Report, console=None) -> None: ...
```

The HTML page skeleton (head, CSS from theme tokens, layout) and the Rich rendering both live in core and iterate `report.sections` generically. The current `report.html.j2` becomes a **generic** section-iterating template owned by core.

**Dependencies:** rendering needs jinja2 (HTML) + rich (terminal). These become a core **extra** — `agent-reliability-core[render]` — so trace/concurrency/persona consumers stay lean. (trace + concurrency remain stdlib-only; persona adds pydantic+pyyaml; render adds jinja2+rich, opt-in.)

## 4. stampede's adapter (stays in stampede)

A single function maps the domain report to the presentation model; `renderer.py` shrinks to adapt-then-delegate.

```python
# observer/report_view.py
def to_report(r: RunReport) -> core.report.Report:
    sections: list[Section] = [
        KpiRow([Kpi(f"{succ:.0%}", "task success"), Kpi(f"{mis:.0%}", "misuse"),
                Kpi(f"{r.cost_spread:.1f}×", "cost spread"), Kpi(f"${r.total_usd:.4f}", "modeled spend")]),
    ]
    if r.misuse_map:
        sections += [Callout("Where agents called the wrong tool for their goal…"),
                     Table("Misuse map", [Column("expected"), Column("called"),
                                          Column("confusion", "right"), Column("n", "right")],
                           [[Cell(m.expected_tool), Cell(m.realized_tool),
                             Cell(f"{m.confusion_rate:.0%}", bar=m.confusion_rate), Cell(str(m.n_labeled))]
                            for m in r.misuse_map])]
    # …success / cost tables, perf / chaos / realism Notes, adversarial KpiRow…
    return Report(title="Agent Readiness Report", subtitle=f"{r.target} · {r.size} agents · seed {r.seed}",
                  badge=Badge(r.grade), sections=sections)

# observer/renderer.py  (now trivial + unchanged public API)
def render_html(r: RunReport) -> str:      return core.render_html(to_report(r))
def render_terminal(r: RunReport) -> None: core.render_terminal(to_report(r))
```

`render_html` / `render_terminal` keep their **exact current signatures**, so `cli.py` and every test are unaffected.

## 5. Decisions & alternatives

- **Closed section union vs an open `Renderable` protocol.** → *Closed.* Five shapes cover all three tools; a closed set keeps both renderers small and the theme consistent. New shapes are added deliberately, not ad hoc. (An open protocol would push rendering back into each tool — re-fragmenting the look.)
- **Presentation model vs moving `RunReport` to core.** → *Presentation model.* `RunReport` is stampede-domain; core must not know about misuse maps or personas. The adapter is the only stampede-aware code.
- **Theme tokens vs a hard-coded stylesheet.** → *Tokens.* One `Theme` dataclass drives both HTML hex and terminal styles, so the oxblood identity is defined once and a tool could reskin without forking the renderer.
- **Rendering deps in core.** → *Opt-in extra* (`[render]`), so the telemetry/scheduler consumers don't pull jinja2+rich.

## 6. Implementation plan (the follow-up PR)

1. `agent_reliability_core/report/`: `model.py` (the dataclasses above), `theme.py`, `render.py` (HTML+terminal), `templates/report.html.j2` (generic, section-iterating). Add the `[render]` extra.
2. Standalone core tests: build a `Report` by hand, assert HTML contains the sections/badge and terminal renders without error — **importing only `agent_reliability_core.report`** (proves it's domain-free).
3. stampede: add `observer/report_view.to_report`; reduce `observer/renderer.py` to the two delegating functions; delete `observer/templates/report.html.j2`.
4. **Equivalence check:** a test asserts the rendered HTML still carries every section title + the grade badge (visual parity), and the existing CLI/report tests pass unchanged.

## 7. Definition of done

- `RunReport` / `build_report` / `to_dict` byte-identical output (determinism intact).
- `render_html` / `render_terminal` signatures unchanged; all existing tests green.
- Core `report` primitive imports without stampede and renders a hand-built `Report`.
- HTML output visually equivalent (same sections, same oxblood theme).
