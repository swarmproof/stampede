"""Schema-aware goal synthesis: actionable for discovered targets, unchanged for built-ins."""

from __future__ import annotations

from stampede.goals.synth import _fabricate_value, synthesize
from stampede.targets.base import ToolSet, ToolSpec


def _tool(name: str, required=None, props=None) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"do {name}",
        input_schema={"type": "object", "properties": props or {}, "required": required or []},
    )


def test_fabricated_values_respect_type_enum_and_name():
    assert _fabricate_value("amount_cents", {"type": "integer"}, 0) == 500
    assert _fabricate_value("qty", {"type": "integer"}, 2) == 3          # non-money int
    assert _fabricate_value("ratio", {"type": "number"}, 0) == 1.0   # non-money number
    assert _fabricate_value("active", {"type": "boolean"}, 0) is True
    assert _fabricate_value("currency", {"type": "string", "enum": ["eur", "usd"]}, 0) == "eur"
    assert _fabricate_value("customer_id", {"type": "string"}, 0) == "cus_1"
    assert _fabricate_value("charge_id", {"type": "string"}, 1) == "ch_2"
    assert _fabricate_value("email", {"type": "string"}, 0) == "user1@example.com"
    assert _fabricate_value("currency", {"type": "string"}, 0) == "usd"


def test_discovered_tool_goal_is_actionable():
    ts = ToolSet(tools=[_tool("create_charge", ["customer_id", "amount"],
                              {"customer_id": {"type": "string"}, "amount": {"type": "integer"}})])
    g = synthesize(ts, mode="template", count=1, seed=42)[0]
    # concrete values appear in BOTH the text (for a live model) and args (for the heuristic)
    assert "customer_id=cus_1" in g.text and "amount=500" in g.text
    assert g.args == {"customer_id": "cus_1", "amount": "500"}
    assert g.intent.expected_tool == "create_charge" and g.labeled


def test_read_tool_with_required_id_is_actionable():
    ts = ToolSet(tools=[_tool("get_charge", ["charge_id"], {"charge_id": {"type": "string"}})])
    g = synthesize(ts, mode="template", count=1, seed=42)[0]
    assert "charge_id=ch_1" in g.text and g.args == {"charge_id": "ch_1"}


def test_no_required_params_keeps_legacy_text_unchanged():
    # A read tool with no required params must produce the exact legacy phrasing.
    ts = ToolSet(tools=[_tool("list_charges", [], {"customer_id": {"type": "string"}})])
    g = synthesize(ts, mode="template", count=1, seed=42)[0]
    assert g.text == "Look up the current records using list_charges."
    assert g.args == {}


def test_synthesis_is_deterministic():
    ts = ToolSet(tools=[_tool("create_charge", ["customer_id", "amount"],
                              {"customer_id": {"type": "string"}, "amount": {"type": "integer"}})])
    a = [(g.text, g.args) for g in synthesize(ts, mode="template", count=6, seed=42)]
    b = [(g.text, g.args) for g in synthesize(ts, mode="template", count=6, seed=42)]
    assert a == b
