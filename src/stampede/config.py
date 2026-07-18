"""``stampede.yaml`` — the config people commit to their repo (FR-CLI-03).

Schema per SPEC §2.3 + the ⊕ ``safety:`` / ``report.plan_only`` blocks from
ARCHITECTURE §4.4. Pydantic gives validation + clear errors for free. Durations
like ``5m`` / ``30s`` parse to integer *virtual seconds* (SimClock ticks).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# ---- duration parsing -------------------------------------------------------

_DUR_RE = re.compile(r"^\s*(\d+)\s*(ms|s|m|h)?\s*$")
_DUR_MULT = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, None: 1}


def parse_duration(value: str | int | float) -> int:
    """``"5m"`` → 300, ``"30s"`` → 30, ``90`` → 90. Returns virtual seconds."""
    if isinstance(value, (int, float)):
        return int(value)
    m = _DUR_RE.match(str(value))
    if not m:
        raise ValueError(f"invalid duration: {value!r} (use e.g. '30s', '5m', '1h')")
    return int(int(m.group(1)) * _DUR_MULT[m.group(2)])


# ---- config sections --------------------------------------------------------


class TargetConfig(BaseModel):
    type: Literal["mcp", "http", "mock", "evm"] = "mock"
    transport: Literal["stdio", "http", "sse"] = "stdio"
    command: str | None = None  # mcp/stdio: the server launch command
    url: str | None = None  # mcp/http, http: the endpoint
    spec: str | None = None  # http: path/URL to an OpenAPI spec
    world: str | None = None  # mock: which built-in world (e.g. "crm", "payments")
    rpc_url: str | None = None  # evm: the fork RPC (v0.2)


class PopulationConfig(BaseModel):
    size: int = Field(default=50, ge=1)
    mix: dict[str, float] = Field(default_factory=lambda: {"naive": 1.0})
    models: list[str] = Field(default_factory=lambda: ["dry-run:heuristic"])
    pack: str = "core"  # persona pack name or path

    @field_validator("mix")
    @classmethod
    def _mix_positive(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("population.mix must name at least one persona")
        if any(w < 0 for w in v.values()):
            raise ValueError("population.mix weights must be non-negative")
        if sum(v.values()) <= 0:
            raise ValueError("population.mix weights must sum to > 0")
        return v


class GoalsConfig(BaseModel):
    autogenerate: bool = True
    mode: Literal["llm", "template", "traffic"] = "template"
    extra: list[str] = Field(default_factory=list)


class ConcurrencyConfig(BaseModel):
    curve: Literal["ramp", "spike", "steady"] = "ramp"
    peak: int | None = None  # defaults to population.size when None
    hold: int = 0  # virtual seconds

    @field_validator("hold", mode="before")
    @classmethod
    def _parse_hold(cls, v: Any) -> int:
        return parse_duration(v)


class ChaosConfig(BaseModel):
    kill_agents_at: list[str | int] = Field(default_factory=list)  # ["random"] | step ints
    inject: list[str] = Field(default_factory=list)  # tool_timeout, malformed_output, ...
    rate: float = 0.15  # probability a given eligible invoke is faulted
    assert_recovery: bool = False


class SafetyConfig(BaseModel):
    """The Target Safety Gate config (⊕ FR-TA-05, ADR-6). On by default."""

    allow_targets: list[str] = Field(
        # stdio:* = a local MCP subprocess (no network) — safe by construction.
        default_factory=lambda: ["localhost:*", "127.0.0.1:*", "mock:*", "dry-run:*", "stdio:*"]
    )
    acknowledge_non_production: bool = False
    evm_require_fork: bool = True


class ReportConfig(BaseModel):
    out: str = "./stampede-report.html"
    live: bool = False
    budget_usd: float = Field(default=5.0, ge=0)
    plan_only: bool = False
    trace_db: str = "./stampede-run.db"


class StampedeConfig(BaseModel):
    """The whole ``stampede.yaml``."""

    target: TargetConfig = Field(default_factory=TargetConfig)
    population: PopulationConfig = Field(default_factory=PopulationConfig)
    goals: GoalsConfig = Field(default_factory=GoalsConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    chaos: ChaosConfig = Field(default_factory=ChaosConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    seed: int = 42

    @model_validator(mode="after")
    def _default_peak(self) -> StampedeConfig:
        if self.concurrency.peak is None:
            self.concurrency.peak = self.population.size
        return self

    # ---- loading ----

    @classmethod
    def load(cls, path: str | Path) -> StampedeConfig:
        raw = yaml.safe_load(Path(path).read_text()) or {}
        return cls.model_validate(raw)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StampedeConfig:
        return cls.model_validate(data)
