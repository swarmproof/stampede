"""Goal Synthesis (⊕ FR-GS-*) — realistic, intent-labeled objectives.

Turns a target's tool surface into natural-language goals, each carrying a
**difficulty** and an **intent label** (the expected tool / effect). That intent
label is the ground-truth oracle for the misuse map (ADR-5): misuse = the tool an
agent actually called ≠ the goal's expected tool, on *labeled* goals only.
"""

from __future__ import annotations

from stampede.goals.schema import Goal, GoalMode, Intent
from stampede.goals.synth import GoalSynthesizer, synthesize

__all__ = ["Goal", "GoalMode", "GoalSynthesizer", "Intent", "synthesize"]
