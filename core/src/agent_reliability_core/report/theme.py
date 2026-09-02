"""The shared oxblood-editorial theme — defined once, drives HTML + terminal.

A ``Theme`` maps the palette and each ``Tone`` to a hex (HTML) and a Rich style
(terminal), so the portfolio's visual identity lives in one place and a tool can
reskin without forking the renderers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_reliability_core.report.model import Tone


@dataclass
class Theme:
    ink: str = "#1b1712"
    paper: str = "#faf6f0"
    muted: str = "#7a6f63"
    line: str = "#e6ddd1"
    accent: str = "#6b1f2a"  # oxblood
    good: str = "#2f7d4f"
    warn: str = "#b8860b"
    bad: str = "#b03030"
    serif: str = '"Iowan Old Style", "Palatino Linotype", Georgia, serif'

    # Tone → terminal Rich style.
    terminal_styles: dict[str, str] = field(
        default_factory=lambda: {
            Tone.NEUTRAL: "default",
            Tone.GOOD: "green",
            Tone.WARN: "yellow",
            Tone.BAD: "red",
            Tone.ACCENT: "red",
        }
    )

    def hex_for(self, tone: Tone) -> str:
        return {
            Tone.NEUTRAL: self.ink,
            Tone.GOOD: self.good,
            Tone.WARN: self.warn,
            Tone.BAD: self.bad,
            Tone.ACCENT: self.accent,
        }[tone]

    def rich_for(self, tone: Tone) -> str:
        return self.terminal_styles[tone]


DEFAULT_THEME = Theme()
