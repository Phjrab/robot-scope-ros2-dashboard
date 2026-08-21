"""FastAPI dependencies backed by the explicit application runtime."""

from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException, Request, WebSocket

from ..application.runtime import ApplicationRuntime
from ..http_security import is_same_origin


T = TypeVar("T")


def runtime_from_request(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise HTTPException(status_code=503, detail="application runtime is not configured")
    return runtime


def runtime_from_websocket(websocket: WebSocket) -> ApplicationRuntime:
    runtime = getattr(websocket.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise RuntimeError("application runtime is not configured")
    return runtime


def require_component(value: T | None, detail: str) -> T:
    if value is None:
        raise HTTPException(status_code=503, detail=detail)
    return value


def require_same_origin(request: Request) -> None:
    if not is_same_origin(
        request.headers.get("origin", ""),
        request.headers.get("host", ""),
    ):
        raise HTTPException(status_code=403, detail="mutation requests must be same-origin")


def websocket_same_origin(websocket: WebSocket) -> bool:
    return is_same_origin(
        websocket.headers.get("origin", ""),
        websocket.headers.get("host", ""),
    )
