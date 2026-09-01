"""EVMTarget — mock lending wallet-swarm + the fork-guard (FR-TA-04, ADR-6)."""

from __future__ import annotations

import pytest

from stampede.config import SafetyConfig, StampedeConfig
from stampede.run import run_simulation
from stampede.targets.base import AgentContext, ToolCall
from stampede.targets.evm import EVMTarget
from stampede.targets.safety import SafetyGate, SafetyViolation


def _ctx() -> AgentContext:
    return AgentContext(agent_id="a1", isolation_key="a1")


async def _invoke(t: EVMTarget, tool: str, **args):
    return await t.invoke(ToolCall(tool=tool, arguments=args), _ctx())


# ---- the mock lending world ----


async def test_lending_toolset():
    ts = await EVMTarget(world="lending").discover()
    assert set(ts.names()) == {"borrow", "repay", "liquidate", "positions"}
    assert ts.get("liquidate").destructive


async def test_borrow_respects_ltv():
    t = EVMTarget(world="lending")
    ok = await _invoke(t, "borrow", amount=300)  # 300 <= 1000*0.75
    assert ok.ok and ok.structured["debt"] == 300
    over = await _invoke(t, "borrow", amount=600)  # 300+600 > 750 → revert
    assert not over.ok and "undercollateralized" in over.error


async def test_liquidate_underwater_but_not_healthy():
    t = EVMTarget(world="lending")
    good = await _invoke(t, "liquidate", account="acct_1")  # underwater → seizable
    assert good.ok and good.structured["seized"] == "acct_1"
    grief = await _invoke(t, "liquidate", account="acct_0")  # healthy → revert (griefing)
    assert not grief.ok and "healthy" in grief.error


# ---- the fork-guard (ADR-6) ----


def test_mock_evm_is_allowlisted_and_fork_ok():
    t = EVMTarget(world="lending")
    d = t.safety_descriptor()
    assert d.kind == "evm" and d.evm_is_fork is True and d.endpoint.startswith("mock:")
    SafetyGate(SafetyConfig()).check(d)  # does not raise


def test_non_fork_rpc_is_refused():
    t = EVMTarget(rpc_url="https://mainnet.example.com", _is_fork=False)
    with pytest.raises(SafetyViolation):
        SafetyGate(SafetyConfig()).check(t.safety_descriptor())


def test_detected_fork_on_localhost_is_allowed():
    t = EVMTarget(rpc_url="http://localhost:8545", _is_fork=True)
    posture = SafetyGate(SafetyConfig()).check(t.safety_descriptor())
    assert posture.allowed


def test_unreachable_rpc_treated_as_non_fork():
    t = EVMTarget(rpc_url="http://127.0.0.1:1/", _is_fork=None)
    with pytest.raises(SafetyViolation):  # is_fork None → gate refuses
        SafetyGate(SafetyConfig()).check(t.safety_descriptor())


# ---- end-to-end wallet-swarm (dry-run, no chain) ----


async def test_wallet_swarm_runs_and_reports():
    cfg = StampedeConfig.from_dict(
        {
            "target": {"type": "evm", "world": "lending"},
            "population": {"size": 40, "mix": {"naive": 0.5, "expert": 0.3, "adversarial": 0.2}, "models": ["dry-run:heuristic"]},
            "seed": 42,
        }
    )
    result = await run_simulation(cfg, dry_run=True)
    d = result.report.to_dict()
    assert d["meta"]["safety_posture"] == "allowlisted"
    assert d["performance"]["tool_calls"] >= 40
    # The adversarial cohort reached the destructive liquidate path (griefing surface).
    assert d["adversarial"]["cohort_size"] > 0


async def test_wallet_swarm_is_deterministic():
    def cfg():
        return StampedeConfig.from_dict(
            {
                "target": {"type": "evm", "world": "lending"},
                "population": {"size": 30, "mix": {"naive": 0.7, "adversarial": 0.3}, "models": ["dry-run:heuristic"]},
                "seed": 7,
            }
        )

    a = (await run_simulation(cfg(), dry_run=True)).report.to_dict()
    b = (await run_simulation(cfg(), dry_run=True)).report.to_dict()
    assert a == b
