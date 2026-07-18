"""Goal + Intent models (ARCHITECTURE §2.3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

GoalMode = Literal["llm", "template", "traffic"]
Difficulty = Literal["easy", "medium", "hard"]


class Intent(BaseModel):
    """The misuse oracle: what tool/effect a correct agent should produce."""

    expected_tool: str | None = None
    expected_effect: str = ""


class Goal(BaseModel):
    id: str
    text: str  # natural-language objective the agent pursues
    difficulty: Difficulty = "medium"
    intent: Intent = Field(default_factory=Intent)
    labeled: bool = False  # False → excluded from the misuse-rate denominator (ADR-5)
    # Deterministic per-goal arguments the dry-run brain uses (e.g. {"record_id": "rec_7"}).
    args: dict[str, str] = Field(default_factory=dict)
