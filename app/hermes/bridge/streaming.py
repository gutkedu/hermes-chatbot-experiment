"""Bridge synchronous Hermes callback streaming into an async generator."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


async def stream_conversation(agent: Any, **kwargs: Any) -> AsyncIterator[str]:
    """Yield Hermes callback deltas and fall back to the final response.

    Hermes currently exposes a synchronous ``run_conversation`` method.  The
    AgentCore entrypoint is asynchronous, so the call runs in a worker thread
    and callback values cross back through an asyncio queue.
    """

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any, BaseException | None]] = asyncio.Queue()

    def emit(value: Any) -> None:
        if value is None:
            return
        text = value if isinstance(value, str) else str(value)
        if text:
            loop.call_soon_threadsafe(queue.put_nowait, ("delta", text, None))

    def run() -> None:
        result: Any = None
        error: BaseException | None = None
        try:
            result = agent.run_conversation(stream_callback=emit, **kwargs)
        except BaseException as exc:  # propagate the original agent failure
            error = exc
        loop.call_soon_threadsafe(queue.put_nowait, ("finished", result, error))

    worker = asyncio.create_task(asyncio.to_thread(run))
    streamed = False
    result: Any = None
    error: BaseException | None = None

    while True:
        kind, value, failure = await queue.get()
        if kind == "delta":
            streamed = True
            yield value
            continue
        result = value
        error = failure
        break

    await worker
    if error is not None:
        raise error
    if streamed:
        return

    final_response = result.get("final_response", "") if isinstance(result, dict) else ""
    if final_response:
        yield str(final_response)
