"""EVMTarget — point a wallet-swarm at an onchain protocol (FR-TA-04, v0.2).

The premium "open-Gauntlet" surface: agents hold funded test wallets and their tool
calls become transactions. Two backends behind one adapter:

* **mock lending world** (default, no chain) — a deterministic in-process lending
  pool (borrow / repay / liquidate) so the wallet-swarm demo runs in ``--dry-run``
  with zero infra. This is what makes the EVM story verifiable in CI.
* **Anvil fork** (``rpc_url``) — a real fork via web3.py. Guarded by the fork check
  below and the Safety Gate: an ``EVMTarget`` **refuses a non-fork mainnet RPC**
  (ADR-6, NFR-SEC), so a chaos/adversarial swarm can never touch real value.

Requires the ``[evm]`` extra (web3) only for the Anvil backend.
"""

from __future__ import annotations

from typing import Any

from stampede.targets.base import (
    AgentContext,
    HealthStatus,
    IsolationMode,
    SafetyDescriptor,
    TargetAdapter,
    ToolCall,
    ToolResult,
    ToolSet,
    ToolSpec,
)

_LTV = 0.75  # loan-to-value: you can borrow up to 75% of collateral


# ---- the mock lending world (deterministic, no chain) -----------------------


def _lending_toolset() -> ToolSet:
    amount_schema = {"type": "object", "properties": {"amount": {"type": "integer"}}}
    return ToolSet(
        tools=[
            ToolSpec(
                name="borrow",
                description="Borrow against your collateral. Fails if it would leave you undercollateralized.",
                input_schema=amount_schema,
                destructive=True,
            ),
            ToolSpec(
                name="repay",
                description="Repay part of your debt.",
                input_schema=amount_schema,
            ),
            ToolSpec(
                name="liquidate",
                description="Liquidate an undercollateralized account and seize its collateral.",
                input_schema={"type": "object", "properties": {"account": {"type": "string"}}},
                destructive=True,
            ),
            ToolSpec(
                name="positions",
                description="Read the current accounts and their health.",
                input_schema={"type": "object", "properties": {}},
            ),
        ]
    )


def _seed_state() -> dict[str, Any]:
    # The agent's own wallet + phantom accounts (two already underwater → liquidatable).
    return {
        "wallet": {"collateral": 1000, "debt": 0},
        "accounts": {
            "acct_0": {"collateral": 1000, "debt": 100},  # healthy
            "acct_1": {"collateral": 1000, "debt": 900},  # underwater (debt > 750)
            "acct_2": {"collateral": 500, "debt": 480},  # underwater
        },
        "liquidations": 0,
    }


def _healthy(pos: dict[str, int]) -> bool:
    return pos["debt"] <= pos["collateral"] * _LTV


def _lending_handler(tool: str, args: dict[str, Any], state: dict[str, Any]) -> ToolResult:
    wallet = state["wallet"]
    if tool == "positions":
        underwater = [a for a, p in state["accounts"].items() if not _healthy(p)]
        return ToolResult(ok=True, content=f"{len(underwater)} liquidatable", structured={"underwater": underwater})
    if tool == "borrow":
        amount = _as_int(args.get("amount"), 300)
        if wallet["debt"] + amount <= wallet["collateral"] * _LTV:
            wallet["debt"] += amount
            return ToolResult(ok=True, content=f"borrowed {amount}", structured=dict(wallet))
        return ToolResult(ok=False, is_error=True, error="borrow would leave position undercollateralized")
    if tool == "repay":
        amount = _as_int(args.get("amount"), 200)
        wallet["debt"] = max(0, wallet["debt"] - amount)
        return ToolResult(ok=True, content=f"repaid {amount}", structured=dict(wallet))
    if tool == "liquidate":
        account = str(args.get("account") or "acct_1")
        pos = state["accounts"].get(account)
        if pos is None:
            return ToolResult(ok=False, is_error=True, error=f"no such account {account!r}")
        if _healthy(pos):
            # Griefing attempt: trying to liquidate a healthy position → reverts.
            return ToolResult(ok=False, is_error=True, error=f"{account} is healthy; cannot liquidate")
        state["liquidations"] += 1
        pos["debt"] = 0
        return ToolResult(ok=True, content=f"liquidated {account}", structured={"seized": account})
    return ToolResult(ok=False, is_error=True, error=f"unknown tool {tool!r}")


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---- the adapter ------------------------------------------------------------


class EVMTarget(TargetAdapter):
    def __init__(
        self,
        rpc_url: str | None = None,
        world: str | None = None,
        require_fork: bool = True,
        _is_fork: bool | None = None,  # test seam for the fork probe
    ) -> None:
        self.rpc_url = rpc_url
        self.world_name = world or ("lending" if not rpc_url else None)
        self.require_fork = require_fork
        self._state: dict[str, dict[str, Any]] = {}

        if self.world_name and not rpc_url:
            self._is_fork: bool | None = True  # in-process sandbox is a "fork"
            self._toolset = _lending_toolset()
        else:
            self._toolset = ToolSet()  # discovered from the chain contract (v0.2+)
            self._is_fork = _is_fork if _is_fork is not None else self._probe_fork()

    # ---- fork detection (the safety-critical bit) ----

    def _probe_fork(self) -> bool | None:
        """True if ``rpc_url`` is an Anvil/Foundry fork, False if a real node,
        None if unreachable. Anvil answers the ``anvil_nodeInfo`` RPC with a
        ``forkConfig`` block; a real node does not."""
        if not self.rpc_url:
            return None
        try:
            import httpx

            resp = httpx.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": "anvil_nodeInfo", "params": []},
                timeout=5.0,
            )
            info = resp.json().get("result") or {}
            fork_url = (info.get("forkConfig") or {}).get("forkUrl")
            return bool(fork_url)
        except Exception:
            return None  # unreachable / not Anvil → gate refuses (safe default)

    # ---- adapter API ----

    async def discover(self) -> ToolSet:
        if self.world_name:
            return self._toolset
        raise NotImplementedError(
            "EVMTarget against a live fork discovers tools from a contract ABI — "
            "supply an ABI (v0.2+). The mock lending world runs today: target.world=lending."
        )

    async def invoke(self, call: ToolCall, ctx: AgentContext) -> ToolResult:
        if not self.world_name:
            raise NotImplementedError("live-fork invoke (signed tx) lands in a follow-up")
        bucket = self._state.setdefault(ctx.isolation_key, _seed_state())
        return _lending_handler(call.tool, call.arguments, bucket)

    async def reset(self, seed: int | None = None) -> None:
        self._state.clear()

    async def health(self) -> HealthStatus:
        if self.world_name:
            return HealthStatus(ok=True, detail=f"mock evm world {self.world_name!r}")
        return HealthStatus(ok=self._is_fork is True, detail=f"fork={self._is_fork}")

    def isolation(self) -> IsolationMode:
        return IsolationMode.PER_AGENT

    def safety_descriptor(self) -> SafetyDescriptor:
        if self.world_name and not self.rpc_url:
            # mock: prefix → matches the default allowlist; is_fork=True passes the gate.
            return SafetyDescriptor(kind="evm", endpoint=f"mock:evm-{self.world_name}", evm_is_fork=True)
        from urllib.parse import urlparse

        parsed = urlparse(self.rpc_url or "")
        host = parsed.hostname or ""
        endpoint = f"{host}:{parsed.port}" if parsed.port else host
        return SafetyDescriptor(kind="evm", endpoint=endpoint, evm_is_fork=self._is_fork)
