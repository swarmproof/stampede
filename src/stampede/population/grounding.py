"""Persona grounding / calibration (⊕ FR-PF-06, FR-OB-07, FR-OB-09).

Answers the thesis's biggest risk — "how do you know these agents are realistic?"
(the "Lost in Simulation" critique):

1. **Record** a distribution of *real* agent behaviour against a target
   (:class:`RecordedTraffic`, built from trace-format spans or a saved report).
2. **Fit** a persona's temperament so the simulated population matches that
   distribution (:func:`fit_persona`).
3. **Score** how close the simulation is to the recording (:func:`realism_score`),
   and report it — honestly, as a distance, not a guarantee.

v0.2 fits ``misread_rate`` (the dominant driver of misuse) in closed form by
inverting the heuristic brain's own decision model; more params calibrate later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stampede.personas.schema import Persona
    from stampede.trace.schema import Span

# Weights for the realism distance — misuse dominates (it's the flagship signal).
_W_MISUSE, _W_GIVEUP, _W_TOKENS = 0.6, 0.2, 0.2


@dataclass
class RecordedTraffic:
    """An observed behaviour distribution to calibrate against."""

    misuse_rate: float
    give_up_rate: float = 0.0
    avg_tokens: float = 0.0
    sample_size: int = 0
    source: str = ""

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.__dict__, indent=2, sort_keys=True))

    @classmethod
    def from_json(cls, path: str | Path) -> RecordedTraffic:
        return cls(**json.loads(Path(path).read_text()))

    @classmethod
    def from_report(cls, report: dict[str, Any], source: str = "report") -> RecordedTraffic:
        """Distill a saved RunReport dict into an aggregate distribution."""
        rows = report.get("success", [])
        n = sum(r.get("n", 0) for r in rows) or 1
        misuse = sum(r.get("misuse_rate", 0.0) * r.get("n", 0) for r in rows) / n
        success = sum(r.get("success_rate", 0.0) * r.get("n", 0) for r in rows) / n
        tokens_rows = report.get("cost_profile", [])
        tok_n = len(tokens_rows) or 1
        avg_tokens = sum(r.get("tokens_mean", 0.0) for r in tokens_rows) / tok_n
        return cls(
            misuse_rate=round(misuse, 6),
            give_up_rate=round(1.0 - success, 6),
            avg_tokens=round(avg_tokens, 2),
            sample_size=n,
            source=source,
        )

    @classmethod
    def from_spans(cls, spans: list[Span], source: str = "recorded") -> RecordedTraffic:
        """Record mode (FR-OB-09): distill real agent traffic (trace-format spans)."""
        from stampede.trace.schema import GenAI, Swarmproof

        agents = 0
        misused = 0
        gave_up = 0
        total_tokens = 0
        for span in spans:
            a = span.attributes
            if span.name == "invoke_agent":
                agents += 1
                if a.get("swarmproof.agent.misuse"):
                    misused += 1
                if a.get(Swarmproof.AGENT_STATE) == "FAILED":
                    gave_up += 1
            if span.name == "chat":
                total_tokens += int(a.get(GenAI.USAGE_INPUT_TOKENS, 0)) + int(
                    a.get(GenAI.USAGE_OUTPUT_TOKENS, 0)
                )
        n = agents or 1
        return cls(
            misuse_rate=round(misused / n, 6),
            give_up_rate=round(gave_up / n, 6),
            avg_tokens=round(total_tokens / n, 2),
            sample_size=agents,
            source=source,
        )


def fit_misread_rate(target_misuse: float, goal_adherence: float) -> float:
    """Invert the heuristic decision model to hit a target misuse rate.

    The brain uses ``p_correct = (1 - misread) · (0.5 + 0.5·adherence)`` and
    ``misuse ≈ 1 - p_correct``. Solve for ``misread`` given the observed misuse."""
    denom = 0.5 + 0.5 * goal_adherence
    misread = 1.0 - (1.0 - target_misuse) / denom
    return max(0.0, min(1.0, misread))


def fit_persona(persona: Persona, recorded: RecordedTraffic) -> Persona:
    """Return a calibrated copy of ``persona`` fitted to ``recorded``."""
    from stampede.personas.schema import Calibration

    fitted_misread = fit_misread_rate(recorded.misuse_rate, persona.temperament.goal_adherence)
    temperament = persona.temperament.model_copy(update={"misread_rate": fitted_misread})
    return persona.model_copy(
        update={
            "temperament": temperament,
            "calibration": Calibration(grounded_against=recorded.source or "recorded"),
        }
    )


def realism_score(simulated: RecordedTraffic, recorded: RecordedTraffic) -> float:
    """1.0 = the simulation matches the recording exactly; lower = further apart."""
    d_misuse = abs(simulated.misuse_rate - recorded.misuse_rate)
    d_giveup = abs(simulated.give_up_rate - recorded.give_up_rate)
    denom = max(recorded.avg_tokens, 1.0)
    d_tokens = min(1.0, abs(simulated.avg_tokens - recorded.avg_tokens) / denom)
    distance = _W_MISUSE * d_misuse + _W_GIVEUP * d_giveup + _W_TOKENS * d_tokens
    return round(max(0.0, 1.0 - distance), 4)
