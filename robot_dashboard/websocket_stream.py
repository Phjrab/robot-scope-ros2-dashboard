"""Cancellation-safe helpers for outbound-only dashboard WebSockets."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class ReceivableWebSocket(Protocol):
    async def receive(self) -> dict[str, Any]: ...


async def _wait_for_disconnect(websocket: ReceivableWebSocket) -> None:
    while True:
        try:
            message = await websocket.receive()
        except RuntimeError:
            return
        if message.get("type") == "websocket.disconnect":
            return


async def stream_until_disconnect(
    websocket: ReceivableWebSocket,
    send_next: Callable[[], Awaitable[None]],
    *,
    poll_interval_s: float = 0.02,
) -> None:
    """Pump outbound frames while independently observing client disconnects."""

    disconnect_task = asyncio.create_task(_wait_for_disconnect(websocket))
    try:
        while not disconnect_task.done():
            await send_next()
            await asyncio.wait({disconnect_task}, timeout=poll_interval_s)
    finally:
        disconnect_task.cancel()
        await asyncio.gather(disconnect_task, return_exceptions=True)
