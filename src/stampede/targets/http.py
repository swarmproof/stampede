"""HTTPTarget — any OpenAPI/REST endpoint becomes an agent toolset (FR-TA-02).

Each OpenAPI operation maps to one tool; the agent gets the operation's parameters
as the tool's input schema. Requests carry the W3C ``traceparent`` header so a
trace-aware server nests its SERVER spans under our CLIENT span. Requires the
``[dev]``/``httpx`` extra at run time (kept out of the core dry-run path).
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

from stampede.targets.base import (
    AgentContext,
    HealthStatus,
    SafetyDescriptor,
    TargetAdapter,
    ToolCall,
    ToolResult,
    ToolSet,
    ToolSpec,
)


class HTTPTarget(TargetAdapter):
    def __init__(self, url: str | None, spec: str | None = None) -> None:
        if not url:
            raise ValueError("HTTPTarget needs target.url")
        self.base_url = url.rstrip("/") + "/"
        self.spec_ref = spec
        self._toolset: ToolSet | None = None
        self._op_index: dict[str, dict[str, Any]] = {}
        self._client: Any = None

    def _http(self) -> Any:
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise RuntimeError(
                    "HTTPTarget needs httpx: pip install 'stampede[dev]' or 'httpx'"
                ) from exc
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _load_spec(self) -> dict[str, Any]:
        ref = self.spec_ref or urljoin(self.base_url, "openapi.json")
        if ref.startswith(("http://", "https://")):
            resp = await self._http().get(ref)
            resp.raise_for_status()
            return resp.json()
        # A one-time local spec read at discover() — blocking is fine here.
        from pathlib import Path

        return json.loads(Path(ref).read_text())  # noqa: ASYNC240

    async def discover(self) -> ToolSet:
        spec = await self._load_spec()
        tools: list[ToolSpec] = []
        for path, methods in spec.get("paths", {}).items():
            for method, op in methods.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                    continue
                op_id = op.get("operationId") or f"{method}_{path.strip('/').replace('/', '_')}"
                props: dict[str, Any] = {}
                required: list[str] = []
                for param in op.get("parameters", []):
                    props[param["name"]] = param.get("schema", {"type": "string"})
                    if param.get("required"):
                        required.append(param["name"])
                body = (
                    op.get("requestBody", {})
                    .get("content", {})
                    .get("application/json", {})
                    .get("schema")
                )
                tools.append(
                    ToolSpec(
                        name=op_id,
                        description=op.get("summary") or op.get("description", ""),
                        input_schema={"type": "object", "properties": props, "required": required},
                        destructive=method.lower() == "delete",
                    )
                )
                self._op_index[op_id] = {"method": method.upper(), "path": path, "body": body}
        self._toolset = ToolSet(tools=tools)
        return self._toolset

    async def invoke(self, call: ToolCall, ctx: AgentContext) -> ToolResult:
        op = self._op_index.get(call.tool)
        if op is None:
            return ToolResult(ok=False, is_error=True, error=f"unknown operation {call.tool!r}")
        headers = {"traceparent": ctx.traceparent} if ctx.traceparent else {}
        url = urljoin(self.base_url, op["path"].lstrip("/"))
        try:
            resp = await self._http().request(
                op["method"], url, params=call.arguments, headers=headers
            )
        except Exception as exc:  # network failure surfaced to the agent as a tool error
            return ToolResult(ok=False, is_error=True, error=f"{type(exc).__name__}: {exc}")
        ok = resp.status_code < 400
        return ToolResult(
            ok=ok,
            content=resp.text[:2000],
            is_error=not ok,
            error="" if ok else f"HTTP {resp.status_code}",
        )

    async def health(self) -> HealthStatus:
        try:
            resp = await self._http().get(self.base_url)
            return HealthStatus(ok=resp.status_code < 500, detail=f"HTTP {resp.status_code}")
        except Exception as exc:
            return HealthStatus(ok=False, detail=str(exc))

    def safety_descriptor(self) -> SafetyDescriptor:
        from urllib.parse import urlparse

        parsed = urlparse(self.base_url)
        host = parsed.hostname or ""
        endpoint = f"{host}:{parsed.port}" if parsed.port else host
        is_prod = host not in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        return SafetyDescriptor(kind="http", endpoint=endpoint, is_probably_production=is_prod)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
