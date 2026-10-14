"""Goal synthesis — template (deterministic) + llm modes (FR-GS-01..04).

``template`` mode is a deterministic grammar over the target's ToolSet: no LLM, so
it's the reproducible ``--dry-run`` path (FR-GS-04). Every generated goal is
intent-labeled (the misuse oracle). ``llm`` mode derives richer goals from tool
descriptions via a model; in v0.1 it degrades to ``template`` when no provider is
wired, so the pipeline always produces labeled goals.

For *discovered* targets (an arbitrary MCP server, a mockworld world), the grammar
is **schema-aware**: a tool with required parameters gets concrete, plausible
values fabricated from its input schema and woven into the goal *text*. A live
model reads only the goal text, so without this it (correctly) asks for the missing
``customer_id``/``amount`` instead of acting. Fabrication is deterministic
(index-seeded) and only fires for required params the named templates don't already
cover, so the built-in worlds stay byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stampede.goals.schema import Goal, GoalMode, Intent
from stampede.targets.base import ToolSet, ToolSpec

_READ_HINTS = ("find", "list", "search", "get", "read", "lookup", "query", "show")

# Short, recognizable id prefixes so a fabricated id reads like the real thing
# (``customer_id`` → ``cus_3``) — helps a live model produce a sensible tool call.
_ID_PREFIXES = {
    "customer": "cus", "charge": "ch", "record": "rec", "order": "ord",
    "user": "usr", "account": "acct", "payment": "pay", "invoice": "inv",
    "product": "prod", "subscription": "sub", "session": "sess", "message": "msg",
}
_NAMES = ("Ada Lovelace", "Grace Hopper", "Alan Turing", "Katherine Johnson")


def _is_read(tool: ToolSpec) -> bool:
    lowered = tool.name.lower()
    return any(h in lowered for h in _READ_HINTS)


def _fabricate_value(field: str, spec: dict[str, Any], idx: int) -> Any:
    """A concrete, plausible value for one parameter — from its type, enum, and name.

    Deterministic (index-seeded; no wall-clock/random) so ``--dry-run`` stays
    byte-identical. Returns a native value; the caller stringifies it for
    ``Goal.args`` while the goal *text* presents it naturally.
    """
    if spec.get("enum"):
        return spec["enum"][0]
    low = field.lower()
    money = any(h in low for h in ("amount", "price", "cents", "total", "cost", "balance"))
    kind = spec.get("type")
    if kind in ("integer", "number"):
        val: Any = 500 + (idx % 10) * 100 if money else (idx % 20) + 1
        return float(val) if kind == "number" else val
    if kind == "boolean":
        return True
    if kind == "array":
        return []
    if kind == "object":
        return {}
    # string (and untyped) — lean on the field name for realism
    n = (idx % 50) + 1
    if "email" in low:
        return f"user{n}@example.com"
    if low == "id" or low.endswith("_id") or low.endswith("id"):
        root = low[:-3] if low.endswith("_id") else low[:-2]
        pref = next((v for k, v in _ID_PREFIXES.items() if k in root), (root[:3] or "id"))
        return f"{pref}_{n}"
    if "currency" in low:
        return "usd"
    if "name" in low:
        return _NAMES[idx % len(_NAMES)]
    if money:
        return str(500 + (idx % 10) * 100)
    if any(h in low for h in ("key", "token", "idempot")):
        return f"idem_{n}"
    if "date" in low or "time" in low:
        return "2026-01-01"
    if low in ("q", "query", "search", "term"):
        return "invoice"
    return f"{field}_{idx}"


def _fabricate_required_args(tool: ToolSpec, idx: int) -> dict[str, str]:
    """Concrete string args for a tool's *required* params (empty if none)."""
    schema = tool.input_schema or {}
    props = schema.get("properties", {})
    return {
        req: str(_fabricate_value(req, props.get(req, {}), idx))
        for req in schema.get("required", [])
    }


def _phrase(tool: ToolSpec, idx: int) -> tuple[str, Intent, str, dict[str, str]]:
    """Return (text, intent, difficulty, args) for one goal targeting ``tool``."""
    rid = f"rec_{(idx % 20) + 1}"
    cid = f"cust_{(idx % 50) + 1}"
    amount = str(500 + (idx % 10) * 100)
    name = tool.name

    if name == "archive_record":
        return (
            f"Take record {rid} out of the active list, but keep it so it can be restored later.",
            Intent(expected_tool="archive_record", expected_effect="record archived (recoverable)"),
            "easy",
            {"record_id": rid},
        )
    if name == "delete_record":
        return (
            f"Permanently remove record {rid}. It should be gone for good.",
            Intent(expected_tool="delete_record", expected_effect="record deleted (permanent)"),
            "easy",
            {"record_id": rid},
        )
    if name == "charge_customer":
        return (
            f"Charge customer {cid} {amount} cents for their order; don't double-charge on retry.",
            Intent(expected_tool="charge_customer", expected_effect="exactly one charge applied"),
            "medium",
            {"customer_id": cid, "amount_cents": amount, "idempotency_key": f"idem_{cid}_{amount}"},
        )
    # Discovered tools: fabricate concrete values for any required params so the
    # goal text is actionable for a live model (no required params → unchanged).
    args = _fabricate_required_args(tool, idx)
    detail = ", ".join(f"{k}={v}" for k, v in args.items())

    if _is_read(tool):
        if not args:
            return (
                f"Look up the current records using {name}.",
                Intent(expected_tool=name, expected_effect="records read"),
                "easy",
                {},
            )
        return (
            f"Use {name} to look up {detail}.",
            Intent(expected_tool=name, expected_effect="records read"),
            "easy",
            args,
        )
    desc = tool.description.strip() or f"use the {name} tool"
    if not args:
        return (
            f"Use {name} to accomplish: {desc}",
            Intent(expected_tool=name, expected_effect=f"{name} executed"),
            "medium",
            {},
        )
    return (
        f"Use {name} with {detail} to accomplish: {desc}",
        Intent(expected_tool=name, expected_effect=f"{name} executed"),
        "medium",
        args,
    )


def _goals_from_traffic(toolset: ToolSet, traffic_path: str, count: int) -> list[Goal]:
    """Replay recorded tool calls as intent-labeled goals (FR-GS-05).

    The recording is a JSON array of observed calls — your real system's traffic, or
    a prior run's: ``[{"tool": str, "arguments"?: {...}, "text"?: str}, …]``. Each call
    becomes one goal, labeled with the tool actually called (the misuse oracle knows
    the intended tool *from the recording*, not a guess). Calls for tools the target
    doesn't expose are skipped. Deterministic: file order, cycled to fill ``count``.
    """
    raw = json.loads(Path(traffic_path).read_text())
    if not isinstance(raw, list):
        raise ValueError(f"traffic recording must be a JSON array of calls, got {type(raw).__name__}")
    calls = [e for e in raw if isinstance(e, dict) and toolset.get(str(e.get("tool"))) is not None]
    if not calls:
        raise ValueError(
            f"no recorded calls in {traffic_path!r} name a tool this target exposes "
            f"(have: {', '.join(t.name for t in toolset.tools)})"
        )
    goals: list[Goal] = []
    i = 0
    while len(goals) < max(count, 1):
        entry = calls[i % len(calls)]
        tool = str(entry["tool"])
        args = {str(k): str(v) for k, v in (entry.get("arguments") or {}).items()}
        detail = ", ".join(f"{k}={v}" for k, v in args.items())
        text = str(entry.get("text") or (f"Use {tool} with {detail}." if detail else f"Use {tool}."))
        goals.append(
            Goal(
                id=f"g_traffic_{i}",
                text=text,
                difficulty="easy",
                intent=Intent(expected_tool=tool, expected_effect=f"{tool} (replayed from traffic)"),
                labeled=True,
                args=args,
            )
        )
        i += 1
    return goals


class GoalSynthesizer:
    def synthesize(
        self,
        toolset: ToolSet,
        extra: list[str],
        mode: GoalMode = "template",
        count: int = 12,
        seed: int = 42,
        traffic: str | None = None,
    ) -> list[Goal]:
        if mode == "traffic":
            if not traffic:
                raise ValueError(
                    "goals.mode='traffic' needs goals.traffic: a path to a recorded-calls JSON "
                    "(see FR-GS-05)"
                )
            return _goals_from_traffic(toolset, traffic, count)
        # llm mode falls back to template in v0.1 when offline — still labeled.
        goals: list[Goal] = []

        # Author-supplied extras first. Intent unknown → unlabeled (excluded from
        # the misuse denominator, ADR-5) unless the text names a known tool.
        for i, text in enumerate(extra):
            expected = next((t.name for t in toolset.tools if t.name in text), None)
            goals.append(
                Goal(
                    id=f"g_extra_{i}",
                    text=text,
                    intent=Intent(expected_tool=expected),
                    labeled=expected is not None,
                )
            )

        # Round-robin over tools (actionable first so misuse-bearing goals dominate).
        tools = sorted(toolset.tools, key=lambda t: (_is_read(t), t.name))
        if not tools:
            return goals
        i = 0
        while len(goals) < max(count, len(extra) + 1):
            tool = tools[i % len(tools)]
            text, intent, difficulty, args = _phrase(tool, i)
            goals.append(
                Goal(
                    id=f"g_{i}_{tool.name}",
                    text=text,
                    difficulty=difficulty,
                    intent=intent,
                    labeled=True,
                    args=args,
                )
            )
            i += 1
        return goals


def synthesize(
    toolset: ToolSet,
    extra: list[str] | None = None,
    mode: GoalMode = "template",
    count: int = 12,
    seed: int = 42,
    traffic: str | None = None,
) -> list[Goal]:
    return GoalSynthesizer().synthesize(toolset, extra or [], mode, count, seed, traffic)
