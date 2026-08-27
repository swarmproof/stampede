"""Unit scope for the shared primitives (TEST-PLAN §2): trace-format, persona-pack,
concurrency curves, the six-state machine, config."""

from __future__ import annotations

import pytest

from stampede.config import StampedeConfig, parse_duration
from stampede.orchestrator.curves import schedule_offsets
from stampede.personas.loader import load_pack, sample_mix
from stampede.population.agent import AgentState, StateMachine, TransitionError
from stampede.trace.schema import (
    REDACT_PLACEHOLDER,
    Span,
    new_span_id,
    new_trace_id,
    traceparent,
)

# ---- trace-format ----


def test_ids_are_deterministic_in_seed_and_counter():
    assert new_trace_id(42, 1) == new_trace_id(42, 1)
    assert new_trace_id(42, 1) != new_trace_id(42, 2)
    assert new_trace_id(42, 1) != new_trace_id(7, 1)
    # W3C sizes: trace-id 32 hex, span-id 16 hex.
    assert len(new_trace_id(42, 1)) == 32
    assert len(new_span_id(42, 1)) == 16


def test_traceparent_format():
    tp = traceparent("a" * 32, "b" * 16)
    assert tp == f"00-{'a' * 32}-{'b' * 16}-01"


def test_span_redacts_secrets():
    s = Span(name="x", trace_id="t", span_id="s")
    s.set("api_key", "sk-secret")
    s.set("authorization", "Bearer xyz")
    s.set("gen_ai.request.model", "claude-haiku")
    assert s.attributes["api_key"] == REDACT_PLACEHOLDER
    assert s.attributes["authorization"] == REDACT_PLACEHOLDER
    assert s.attributes["gen_ai.request.model"] == "claude-haiku"
    # Token *counts* must NOT be redacted — "token" is not a bare secret marker.
    s.set("gen_ai.usage.input_tokens", 1200)
    s.set("gen_ai.usage.output_tokens", 300)
    assert s.attributes["gen_ai.usage.input_tokens"] == 1200
    assert s.attributes["gen_ai.usage.output_tokens"] == 300


# ---- persona-pack ----


def test_core_pack_has_six_personas():
    pack = load_pack("core")
    assert set(pack.personas) == {"naive", "expert", "impatient", "frugal", "adversarial", "drunk"}


def test_extends_inheritance_merges_overrides_only():
    pack = load_pack("core")
    naive = pack.get("naive")
    impatient = pack.get("impatient")  # extends naive, overrides patience + retry
    assert impatient.temperament.patience == 2  # overridden
    assert impatient.temperament.retry_policy == "aggressive"  # overridden
    assert impatient.temperament.misread_rate == naive.temperament.misread_rate  # inherited


def test_adversarial_is_flagged_and_loads_attacks():
    pack = load_pack("core")
    adv = pack.get("adversarial")
    assert adv.is_adversarial
    assert "denial_of_wallet" in adv.attacks


def test_sample_mix_is_deterministic_and_sums_to_size():
    pack = load_pack("core")
    mix = {"naive": 0.6, "expert": 0.3, "adversarial": 0.1}
    a = sample_mix(pack, mix, 50, seed=42)
    b = sample_mix(pack, mix, 50, seed=42)
    assert [p.name for p in a] == [p.name for p in b]  # same seed → same assignment
    assert len(a) == 50
    counts = {n: sum(1 for p in a if p.name == n) for n in mix}
    assert counts == {"naive": 30, "expert": 15, "adversarial": 5}


def test_unknown_persona_in_mix_errors_clearly():
    pack = load_pack("core")
    with pytest.raises(KeyError):
        sample_mix(pack, {"wizard": 1.0}, 10, seed=1)


# ---- concurrency curves ----


def test_curves():
    assert schedule_offsets(4, "steady", 4, 30) == [0, 0, 0, 0]
    ramp = schedule_offsets(4, "ramp", 4, 30)
    assert ramp[0] == 0 and ramp[-1] == 30 and ramp == sorted(ramp)
    spike = schedule_offsets(5, "spike", 2, 30)
    assert spike == [0, 0, 30, 30, 30]
    with pytest.raises(ValueError):
        schedule_offsets(3, "nope", 3, 10)


# ---- six-state machine ----


def test_legal_transitions_and_terminal_stickiness():
    sm = StateMachine()
    sm.transition(AgentState.PLANNING)
    sm.transition(AgentState.ACTING)
    sm.transition(AgentState.WAITING)
    sm.transition(AgentState.DONE)
    assert sm.terminal
    with pytest.raises(TransitionError):
        sm.transition(AgentState.PLANNING)  # terminal is sticky


def test_illegal_transition_rejected():
    sm = StateMachine()
    with pytest.raises(TransitionError):
        sm.transition(AgentState.DONE)  # CREATED → DONE is illegal


def test_kill_from_any_state_goes_recovering():
    sm = StateMachine()
    sm.transition(AgentState.PLANNING)
    sm.transition(AgentState.ACTING)
    assert sm.kill() is True
    assert sm.state is AgentState.RECOVERING
    sm.transition(AgentState.DONE)
    assert sm.kill() is False  # already terminal → nothing to kill


# ---- config ----


def test_duration_parsing():
    assert parse_duration("5m") == 300
    assert parse_duration("30s") == 30
    assert parse_duration("1h") == 3600
    assert parse_duration(90) == 90
    with pytest.raises(ValueError):
        parse_duration("soon")


def test_mix_must_be_positive():
    with pytest.raises(ValueError):
        StampedeConfig.from_dict({"population": {"mix": {}}})


def test_peak_defaults_to_size():
    cfg = StampedeConfig.from_dict({"population": {"size": 33}})
    assert cfg.concurrency.peak == 33
