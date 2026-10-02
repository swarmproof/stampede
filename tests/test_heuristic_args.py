"""The dry-run heuristic's argument generation is type-aware (helps strict targets)."""

from __future__ import annotations

from stampede.goals.schema import Goal, Intent
from stampede.population.agent import Agent, ModelBinding
from stampede.population.brain import _args_for, _placeholder
from stampede.targets.base import ToolSet, ToolSpec


def _agent(index: int = 3, **goal_args) -> Agent:
    p = __import__("stampede.personas", fromlist=["load_pack"]).load_pack("core").get("naive")
    goal = Goal(id="g", text="do it", intent=Intent(expected_tool="t"), labeled=True, args=goal_args)
    return Agent(id=f"a{index}", index=index, persona=p, binding=ModelBinding.parse("dry-run:h"), goal=goal, seed=42)


def test_placeholder_respects_declared_type():
    assert _placeholder("amount", {"type": "integer"}, 3) == 4
    assert _placeholder("ratio", {"type": "number"}, 3) == 4.0
    assert _placeholder("flag", {"type": "boolean"}, 3) is False
    assert _placeholder("items", {"type": "array"}, 3) == []
    assert _placeholder("body", {"type": "object"}, 3) == {}
    assert _placeholder("name", {"type": "string"}, 3) == "name_3"
    assert _placeholder("name", {}, 3) == "name_3"  # untyped → string fallback


def test_placeholder_prefers_enum_first_value():
    assert _placeholder("status", {"type": "string", "enum": ["open", "closed"]}, 3) == "open"


def test_args_for_fills_required_with_typed_placeholders():
    ts = ToolSet(tools=[ToolSpec(
        name="charge",
        description="charge",
        input_schema={
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "amount_cents": {"type": "integer"},
                "currency": {"type": "string", "enum": ["usd", "eur"]},
            },
            "required": ["customer_id", "amount_cents", "currency"],
        },
    )])
    args = _args_for("charge", _agent(index=5), ts)
    assert args["amount_cents"] == 6            # integer, not the string "amount_cents_5"
    assert args["currency"] == "usd"            # enum's first value
    assert args["customer_id"] == "customer_id_5"  # string field unchanged


def test_goal_args_still_win_over_placeholders():
    # A goal that already carries a value must not be overwritten by a placeholder.
    # (Goal.args are strings by schema — see note in test docstring.)
    ts = ToolSet(tools=[ToolSpec(
        name="charge",
        description="charge",
        input_schema={
            "type": "object",
            "properties": {"amount_cents": {"type": "integer"}},
            "required": ["amount_cents"],
        },
    )])
    args = _args_for("charge", _agent(index=5, amount_cents="900"), ts)
    assert args["amount_cents"] == "900"  # goal value wins over the typed placeholder
