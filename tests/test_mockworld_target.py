"""MockworldTarget — the mockworld library as a stampede target (FR-TA-03).

Skips cleanly if `mockworld-mcp` isn't installed (it's an optional extra).
"""

from __future__ import annotations

import pytest

from stampede.config import TargetConfig
from stampede.targets import build_target
from stampede.targets.base import AgentContext, IsolationMode, ToolCall

pytest.importorskip("mockworld", reason="install stampede[mockworld]")

from stampede.targets.mockworld import MockworldTarget  # noqa: E402


async def test_discover_maps_mock_tools():
    t = MockworldTarget(world="payments", faults="none")
    try:
        tools = await t.discover()
        names = set(tools.names())
        assert {"create_charge", "refund_charge", "create_customer"} <= names
        charge = tools.get("create_charge")
        assert charge.input_schema["type"] == "object"
        assert charge.idempotency_arg == "idempotency_key"  # inferred from the mock's params
    finally:
        await t.aclose()


async def test_exactly_once_is_reported_on_repeated_key():
    t = MockworldTarget(world="payments", faults="none")
    try:
        ctx = AgentContext(agent_id="a1", isolation_key="a1")
        cust = (await t.invoke(ToolCall("create_customer", {"name": "A", "balance": 10_000}), ctx)).structured
        args = {"customer_id": cust["id"], "amount": 2_500, "idempotency_key": "k1"}
        first = await t.invoke(ToolCall("create_charge", args), ctx)
        second = await t.invoke(ToolCall("create_charge", args), ctx)
        assert first.ok and second.ok
        assert first.side_effect_deduped is False
        assert second.side_effect_deduped is True  # the retry did not double-charge
    finally:
        await t.aclose()


async def test_reset_is_deterministic_and_isolated():
    t = MockworldTarget(world="payments", faults="none")
    try:
        assert t.isolation() is IsolationMode.PER_AGENT

        async def first_id() -> str:
            await t.reset(7)
            r = await t.invoke(
                ToolCall("create_customer", {"name": "X", "balance": 1}),
                AgentContext(agent_id="x", isolation_key="x"),
            )
            return r.structured["id"]

        assert await first_id() == await first_id()  # reset(seed) is a pure function of the seed

        await t.reset(7)
        a = await t.invoke(ToolCall("create_customer", {"name": "A", "balance": 5000}),
                           AgentContext(agent_id="A", isolation_key="A"))
        charge = await t.invoke(ToolCall("create_charge",
                                {"customer_id": a.structured["id"], "amount": 100}),
                                AgentContext(agent_id="A", isolation_key="A"))
        # agent B cannot see agent A's charge (per-agent isolation)
        got = await t.invoke(ToolCall("get_charge", {"charge_id": charge.structured["id"]}),
                             AgentContext(agent_id="B", isolation_key="B"))
        assert got.is_error is True
    finally:
        await t.aclose()


async def test_crm_delete_is_marked_destructive():
    t = MockworldTarget(world="crm", faults="none")
    try:
        tools = await t.discover()
        assert tools.get("delete_record").destructive is True
        assert tools.get("archive_record").destructive is False
    finally:
        await t.aclose()


def test_build_target_and_safety():
    t = build_target(TargetConfig(type="mockworld", world="payments"))
    assert isinstance(t, MockworldTarget)
    sd = t.safety_descriptor()
    assert sd.kind == "mock" and sd.endpoint == "mock:payments"  # matches the mock:* allowlist
