"""Executor backends (FR-OR-04/05) — the shared concurrency-core primitive.

``AsyncioExecutor`` is the default: hundreds of stateful agents on a laptop, bound
by LLM I/O not CPU, so a semaphore-capped ``gather`` is the right shape. A Ray
backend slots behind the same ``Executor`` protocol in v0.2. A failing agent
coroutine is isolated — it resolves to an exception in the results list and never
aborts the run (NFR-REL-01).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class Executor(Protocol):
    async def run(
        self, factories: list[Callable[[], Awaitable[Any]]], concurrency: int
    ) -> list[Any]: ...


class AsyncioExecutor:
    async def run(
        self, factories: list[Callable[[], Awaitable[Any]]], concurrency: int
    ) -> list[Any]:
        sem = asyncio.Semaphore(max(1, concurrency))

        async def _guarded(factory: Callable[[], Awaitable[Any]]) -> Any:
            async with sem:
                return await factory()

        # return_exceptions=True → one crashed agent can't abort the swarm.
        return await asyncio.gather(*(_guarded(f) for f in factories), return_exceptions=True)
