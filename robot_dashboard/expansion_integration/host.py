"""Opt-in product routes. Authentication and producer context belong to the host."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
import inspect
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from robot_dashboard.api.dependencies import require_same_origin
from .flags import ExpansionFlags

STATIC = Path(__file__).resolve().parents[1] / "static"


@dataclass
class ExpansionOwner:
    """Explicit host capabilities; no bearer, ROS discovery or implicit authority."""
    authorize: object = None
    require_mutation: object = None
    catalogue: object = None
    manager: object = None
    store: object = None
    scene: object = None
    scene_context: object = None


async def _invoke(callback, *args):
    result = callback(*args)
    return await result if inspect.isawaitable(result) else result


def install_expansion(app, flags=ExpansionFlags(), owner=None):
    if not flags.enabled:
        return None
    owner = owner or ExpansionOwner()
    app.state.expansion_owner = owner

    async def authorize(request: Request):
        feature = "multimap" if "/multimap/" in request.url.path else "scene"
        if not getattr(flags, feature):
            raise HTTPException(404, "FEATURE_DISABLED")
        if not callable(owner.authorize):
            raise HTTPException(401, "BLOCKED_AUTH")
        await _invoke(owner.authorize, request)

    async def mutation(request: Request):
        require_same_origin(request)
        if not callable(owner.require_mutation):
            raise HTTPException(403, "BLOCKED_AUTH: mutation policy unavailable")
        await _invoke(owner.require_mutation, request)

    class Port:
        def __init__(self, name):
            self.name = name

        def __getattr__(self, key):
            # Resolve only inside C1's call: its body/origin policy runs first.
            def invoke(*args, **kwargs):
                component = getattr(owner, self.name)
                if component is None:
                    raise HTTPException(503, "BLOCKED_INPUTS")
                return getattr(component, key)(*args, **kwargs)
            return invoke

    from robot_dashboard.expansion_services.router import create_router
    app.include_router(create_router(Port("manager"), Port("catalogue"), Port("scene"), Port("store"),
                                     authorize=authorize, require_origin=mutation))
    router = APIRouter()

    @router.get("/extensions", response_class=HTMLResponse)
    async def page():
        config = {"flags": flags.public(), "auth": "OWNER_POLICY" if callable(owner.authorize) else "BLOCKED_AUTH"}
        template = (STATIC / "features/expansion/index.html").read_text()
        return HTMLResponse(template.replace("__I0_CONFIG__", json.dumps(config)),
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                     "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})

    @router.get("/api/v1/extensions/scene/context", dependencies=[Depends(authorize)])
    async def context():
        if not callable(owner.scene_context):
            raise HTTPException(503, "UNAVAILABLE: producer context not configured")
        return await _invoke(owner.scene_context)

    app.include_router(router)
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with previous_lifespan(application) as state:
                yield state
        finally:
            if owner.manager is not None:
                owner.manager.close()

    app.router.lifespan_context = lifespan
    return owner


def dashboard_index(flags):
    """Only opt-in HTML differs; existing app/navigation modules stay untouched."""
    html = (STATIC / "index.html").read_text()
    if flags.enabled:
        html = html.replace('<div class="top-actions">', '<div class="top-actions">'
                            '<a class="ghost-button" href="/extensions">확장 기능 · Offline review</a>', 1)
    return html
