"""persona-pack ``swarmproof.dev/persona/v1`` schema (ARCHITECTURE §4.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RetryPolicy = Literal["none", "gentle", "aggressive"]


class Temperament(BaseModel):
    """Behavioural params — how the agent misreads and misuses (the product)."""

    patience: int = Field(5, ge=0)  # turns tolerated before giving up
    retry_policy: RetryPolicy = "gentle"
    token_budget: int = Field(8000, ge=0)
    risk_appetite: float = Field(0.2, ge=0, le=1)  # willingness to take destructive actions
    misread_rate: float = Field(0.4, ge=0, le=1)  # P(misinterpret a tool description)
    goal_adherence: float = Field(0.6, ge=0, le=1)  # how tightly it sticks to the goal


class Calibration(BaseModel):
    """⊕ grounding provenance (FR-PF-06). Null until a pack is calibrated."""

    grounded_against: str | None = None
    realism_score: float | None = Field(None, ge=0, le=1)


class Persona(BaseModel):
    """A resolved persona (``extends`` already applied by the loader)."""

    name: str
    description: str = ""
    temperament: Temperament = Field(default_factory=Temperament)
    attacks: list[str] = Field(default_factory=list)  # e.g. ["injection", "denial_of_wallet"]
    prompt_template: str = ""
    pack: str = "core@1.0"  # provenance → swarmproof.persona.pack

    @property
    def is_adversarial(self) -> bool:
        return bool(self.attacks) or self.temperament.risk_appetite >= 0.99


class PersonaPack(BaseModel):
    api_version: str = "swarmproof.dev/persona/v1"
    kind: str = "PersonaPack"
    name: str
    version: str = "1.0"
    description: str = ""
    license: str = "Apache-2.0"
    personas: dict[str, Persona] = Field(default_factory=dict)
    calibration: Calibration = Field(default_factory=Calibration)

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    def get(self, name: str) -> Persona:
        try:
            return self.personas[name]
        except KeyError as exc:
            known = ", ".join(sorted(self.personas)) or "(none)"
            raise KeyError(f"persona {name!r} not in pack {self.ref!r}; have: {known}") from exc
