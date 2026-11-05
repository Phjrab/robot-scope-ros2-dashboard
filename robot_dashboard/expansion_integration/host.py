"""Opt-in product routes. Authentication and producer context belong to the host."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
import inspect
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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
    session_login: bool = False


async def _invoke(callback, *args):
    result = callback(*args)
    return await result if inspect.isawaitable(result) else result


def install_landing(app, flags, owner=None, *, review_origin=None):
    """Public discovery only. Reading the page never resolves private providers."""
    @app.get("/extensions", response_class=HTMLResponse)
    async def page(request: Request):
        if review_origin and request.url.scheme != "https":
            return RedirectResponse(review_origin + "/extensions", status_code=307,
                                    headers={"Cache-Control": "no-store"})
        auth = "OWNER_POLICY" if callable(getattr(owner, "authorize", None)) else "BLOCKED_AUTH"
        config = {"flags": flags.public(),
                  "auth": "REVIEW_SESSION" if getattr(owner, "session_login", False) else auth}
        template = (STATIC / "features/expansion/index.html").read_text()
        return HTMLResponse(template.replace("__I0_CONFIG__", json.dumps(config)),
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                     "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})


def install_expansion(app, flags=ExpansionFlags(), owner=None, *, review_origin=None):
    install_landing(app, flags, owner, review_origin=review_origin)
    if not flags.enabled:
        return None
    owner = owner or ExpansionOwner()
    app.state.expansion_owner = owner

    async def authorize(request: Request):
        feature = "multimap" if request.url.path.startswith("/api/v1/extensions/multimap/") else "scene"
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
                                     authorize=authorize, require_origin=mutation,
                                     before_dispatch=mutation if owner.session_login else None))
    router = APIRouter()

    @router.get("/api/v1/extensions/scene/context", dependencies=[Depends(authorize)])
    async def context():
        if not callable(owner.scene_context):
            raise HTTPException(503, "UNAVAILABLE: producer context not configured")
        from .review_owner import qualified_context
        return qualified_context(await _invoke(owner.scene_context))

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
    """Add ordinary links through the existing host hook, outside SPA actions."""
    html = (STATIC / "index.html").read_text()
    html = html.replace('</head>', '<link rel="stylesheet" href="/static/features/expansion/entry.css"></head>', 1)
    html = html.replace('<div class="top-actions">', '<div class="top-actions">'
                        '<a class="ghost-button expansion-entry-top" href="/extensions">확장 기능</a>', 1)
    menu_end = '          </nav>\n        </details>'
    return html.replace(menu_end,
                        '<a class="nav-item" href="/extensions" aria-label="확장 기능">'
                        '<i aria-hidden="true">＋</i><span><b>확장 기능</b>'
                        '<small>지도 합치기·관측·재생</small></span></a>' + menu_end, 1)
