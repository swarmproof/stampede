"""MCPTarget — connect to a real MCP server (FR-TA-01).

Priority transports per the current MCP spec (2025-06-18): **stdio** and
**Streamable HTTP** (plain SSE is deprecated). Trace context propagates via MCP
``_meta``: ``call_tool(meta={...})`` injects the W3C ``traceparent`` into
``params._meta`` so a trace-aware server nests its SERVER spans under our CLIENT
span (ARCHITECTURE §4.1). Requires the ``[mcp]`` extra at run time.

Concurrency: the MCP SDK's ``ClientSession`` is built on anyio structured
concurrency — it must be created *and used* inside one task, and a single stdio
pipe is request/response. So a **dedicated worker task** owns the session lifecycle
and serves discover/invoke commands off a queue; the swarm's many agent tasks
enqueue and await. This keeps SDK access single-tasked (no cross-task cancel-scope
hangs) and correctly serialized.
"""

from __future__ import annotations

import asyncio
import shlex
from contextlib import AsyncExitStack, suppress
from typing import Any

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

_SHUTDOWN = object()


class MCPTarget(TargetAdapter):
    def __init__(
        self,
        transport: str = "stdio",
        command: str | None = None,
        url: str | None = None,
    ) -> None:
        self.transport = transport
        self.command = command
        self.url = url
        if transport == "stdio" and not command:
            raise ValueError("MCPTarget stdio transport needs target.command")
        if transport in {"http", "sse"} and not url:
            raise ValueError("MCPTarget http transport needs target.url")
        self._queue: asyncio.Queue | None = None
        self._worker: asyncio.Task | None = None
        self._ready: asyncio.Event | None = None
        self._start_error: Exception | None = None

    # ---- worker task (owns the session) ----

    async def _ensure_worker(self) -> None:
        if self._worker is not None:
            if self._start_error is not None:
                raise self._start_error
            return
        self._queue = asyncio.Queue()
        self._ready = asyncio.Event()
        self._worker = asyncio.create_task(self._serve())
        await self._ready.wait()
        if self._start_error is not None:
            raise self._start_error

    async def _serve(self) -> None:
        try:
            from mcp import ClientSession
        except ImportError:  # pragma: no cover - env-dependent
            self._start_error = RuntimeError(
                "MCPTarget needs the MCP SDK: pip install 'stampede[mcp]'"
            )
            assert self._ready is not None
            self._ready.set()
            return

        try:
            async with AsyncExitStack() as stack:
                read, write = await self._open_transport(stack)
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                assert self._ready is not None
                self._ready.set()
                assert self._queue is not None
                while True:
                    item = await self._queue.get()
                    if item is _SHUTDOWN:
                        break
                    op, args, fut = item
                    try:
                        fut.set_result(await self._dispatch(session, op, args))
                    except Exception as exc:  # surface per-call errors to the caller
                        if not fut.done():
                            fut.set_exception(exc)
        except Exception as exc:  # startup/transport failure
            self._start_error = exc
            if self._ready is not None and not self._ready.is_set():
                self._ready.set()

    async def _open_transport(self, stack: AsyncExitStack):
        if self.transport == "stdio":
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            assert self.command is not None
            parts = shlex.split(self.command)
            params = StdioServerParameters(command=parts[0], args=parts[1:])
            read, write = await stack.enter_async_context(stdio_client(params))
            return read, write
        assert self.url is not None  # validated in __init__ for http/sse transports
        if self.transport == "http":
            from mcp.client.streamable_http import streamablehttp_client

            read, write, _sid = await stack.enter_async_context(streamablehttp_client(self.url))
            return read, write
        from mcp.client.sse import sse_client  # legacy fallback

        read, write = await stack.enter_async_context(sse_client(self.url))
        return read, write

    async def _dispatch(self, session: Any, op: str, args: Any) -> Any:
        if op == "discover":
            return await self._do_discover(session)
        if op == "invoke":
            return await self._do_invoke(session, *args)
        raise ValueError(f"unknown MCP op {op!r}")

    async def _do_discover(self, session: Any) -> ToolSet:
        tools_result = await session.list_tools()
        tools = [
            ToolSpec(
                name=t.name,
                description=t.description or "",
                input_schema=dict(t.inputSchema or {}),
                output_schema=dict(t.outputSchema) if getattr(t, "outputSchema", None) else None,
            )
            for t in tools_result.tools
        ]
        resources: list[str] = []
        prompts: list[str] = []
        with suppress(Exception):  # server may not support resources
            resources = [str(r.uri) for r in (await session.list_resources()).resources]
        with suppress(Exception):  # server may not support prompts
            prompts = [p.name for p in (await session.list_prompts()).prompts]
        return ToolSet(tools=tools, resources=resources, prompts=prompts)

    async def _do_invoke(self, session: Any, call: ToolCall, ctx: AgentContext) -> ToolResult:
        meta = {"traceparent": ctx.traceparent} if ctx.traceparent else None
        try:
            if meta is not None:
                result = await session.call_tool(call.tool, arguments=call.arguments, meta=meta)
            else:
                result = await session.call_tool(call.tool, arguments=call.arguments)
        except TypeError:
            result = await session.call_tool(call.tool, arguments=call.arguments)
        except Exception as exc:
            return ToolResult(ok=False, is_error=True, error=f"{type(exc).__name__}: {exc}")

        text = _content_text(getattr(result, "content", []))
        is_error = bool(getattr(result, "isError", False))
        return ToolResult(
            ok=not is_error,
            content=text,
            structured=getattr(result, "structuredContent", None),
            is_error=is_error,
            error=text if is_error else "",
        )

    async def _call(self, op: str, args: Any) -> Any:
        await self._ensure_worker()
        assert self._queue is not None
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put((op, args, fut))
        return await fut

    # ---- public adapter API ----

    async def discover(self) -> ToolSet:
        return await self._call("discover", None)

    async def invoke(self, call: ToolCall, ctx: AgentContext) -> ToolResult:
        return await self._call("invoke", (call, ctx))

    async def health(self) -> HealthStatus:
        try:
            await self._ensure_worker()
            return HealthStatus(ok=True)
        except Exception as exc:
            return HealthStatus(ok=False, detail=str(exc))

    def safety_descriptor(self) -> SafetyDescriptor:
        if self.transport == "stdio":
            return SafetyDescriptor(kind="mcp", endpoint="stdio:local")
        from urllib.parse import urlparse

        parsed = urlparse(self.url or "")
        host = parsed.hostname or ""
        endpoint = f"{host}:{parsed.port}" if parsed.port else host
        is_prod = host not in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        return SafetyDescriptor(kind="mcp", endpoint=endpoint, is_probably_production=is_prod)

    async def aclose(self) -> None:
        if self._worker is not None and self._queue is not None:
            await self._queue.put(_SHUTDOWN)
            try:
                await asyncio.wait_for(self._worker, timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                self._worker.cancel()
            self._worker = None


def _content_text(blocks: list[Any]) -> str:
    out: list[str] = []
    for block in blocks:
        text = getattr(block, "text", None)
        out.append(text if text is not None else str(block))
    return "\n".join(out)
