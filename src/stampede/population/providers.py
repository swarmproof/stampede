"""Provider-agnostic model layer + cost model (FR-PF-04, NFR-COST-*).

The swarm mixes providers (Anthropic + OpenAI-compatible + Ollama). This module
normalizes them behind one ``ModelProvider`` protocol and owns the price table that
drives the cost profile and the ``budget_usd`` hard-stop. In ``--dry-run`` no
provider is called at all — the heuristic brain decides — but pricing still applies
to *modeled* token counts, so a dry run doubles as a cost estimate.

Prices are USD per 1M tokens (input, output), approximate as of 2026-07 and easy to
override. They are estimates for planning, not a billing source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# (input_per_1M, output_per_1M) USD. Keyed by "provider:model", then "provider".
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "anthropic:claude-haiku": (0.80, 4.00),
    "anthropic:claude-sonnet": (3.00, 15.00),
    "anthropic:claude-opus": (15.00, 75.00),
    "openai:gpt-4o-mini": (0.15, 0.60),
    "openai:gpt-4o": (2.50, 10.00),
    # local models are free to run
    "ollama": (0.0, 0.0),
    "dry-run": (0.0, 0.0),
}
_DEFAULT_PRICE = (1.00, 3.00)  # unknown paid model → a conservative middle estimate


def price_for(provider: str, model: str) -> tuple[float, float]:
    key = f"{provider}:{model}"
    if key in PRICE_TABLE:
        return PRICE_TABLE[key]
    if provider in PRICE_TABLE:
        return PRICE_TABLE[provider]
    return _DEFAULT_PRICE


def cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    inp, outp = price_for(provider, model)
    return (input_tokens / 1_000_000) * inp + (output_tokens / 1_000_000) * outp


@dataclass
class ToolCallRequest:
    name: str
    arguments: dict


@dataclass
class Completion:
    text: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class ModelProvider(Protocol):
    """A provider that can pick a tool given a goal + a toolset (live mode)."""

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
        temperature: float = 0.0,
    ) -> Completion: ...


class OpenAICompatProvider:
    """OpenAI + any OpenAI-compatible endpoint, incl. Ollama's ``/v1`` (NFR-DX-02).

    Experimental in v0.1: live swarms need an API key / local server and are not on
    the CI blocking path (the deterministic ``--dry-run`` path is)."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = base_url
        self.api_key = api_key

    async def complete(self, *, system, messages, tools, model, temperature=0.0) -> Completion:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key or "not-needed")
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, *messages],
            tools=oai_tools or None,
            temperature=temperature,
        )
        choice = resp.choices[0].message
        calls = [
            ToolCallRequest(name=tc.function.name, arguments=_loads(tc.function.arguments))
            for tc in (choice.tool_calls or [])
        ]
        usage = resp.usage
        return Completion(
            text=choice.content or "",
            tool_calls=calls,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class AnthropicProvider:
    """Anthropic Messages API tool-use. Experimental in v0.1 (see above)."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def complete(self, *, system, messages, tools, model, temperature=0.0) -> Completion:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.api_key) if self.api_key else AsyncAnthropic()
        anth_tools = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema") or {"type": "object", "properties": {}},
            }
            for t in tools
        ]
        resp = await client.messages.create(
            model=model,
            system=system,
            messages=messages or [{"role": "user", "content": "Proceed toward your goal."}],
            tools=anth_tools or None,
            temperature=temperature,
            max_tokens=1024,
        )
        calls: list[ToolCallRequest] = []
        text = ""
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                calls.append(ToolCallRequest(name=block.name, arguments=dict(block.input)))
            elif getattr(block, "type", None) == "text":
                text += block.text
        return Completion(
            text=text,
            tool_calls=calls,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )


def build_provider(provider: str):
    """Instantiate a live provider by name. Ollama uses OpenAI-compat locally."""
    if provider == "anthropic":
        return AnthropicProvider()
    if provider in {"openai", "openai-compat"}:
        return OpenAICompatProvider()
    if provider == "ollama":
        return OpenAICompatProvider(base_url="http://localhost:11434/v1", api_key="ollama")
    raise ValueError(f"no live provider for {provider!r} (use --dry-run for zero-LLM runs)")


def _loads(s: str) -> dict:
    import json

    try:
        return json.loads(s) if s else {}
    except json.JSONDecodeError:
        return {}
