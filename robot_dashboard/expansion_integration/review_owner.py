"""Server-owned review session and data ports. No discovery or control clients."""
import asyncio
from dataclasses import dataclass
import json
import logging
import sqlite3
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from robot_dashboard.api.dependencies import require_same_origin
from robot_dashboard.expansion_contracts import ContractError
from robot_dashboard.expansion_contracts.messages import HASH, ID, integer, token
from .host import ExpansionOwner
from .review_access import AccessUnavailable, ReviewAccess, SECRET


API = "/api/v1/extensions"
COOKIE = "__Secure-robot_scope_review"


@dataclass
class ReviewInputs:
    """A1 supplies trusted ports for one fixed review workspace, independently."""
    maps_factory: object = None  # returns (catalogue, manager, private bundle store)
    scene: object = None
    scene_context: object = None


def qualified_context(value):
    """Copy only public C1/C3 join fields; absent identity cannot qualify a layer."""
    try:
        if not isinstance(value, dict) or value.get("units") != "m":
            raise ValueError
        public = {"map_id": token(value["map_id"], pattern=ID),
                  "revision": token(value["revision"], pattern=HASH),
                  "generation": integer(value["generation"], "map generation"), "units": "m"}
        for key in ("source_epoch", "stream_epoch", "clock_domain", "frame_id",
                    "source_identity", "calibration_id"):
            public[key] = token(value[key], key)
            if public[key].upper() in {"UNKNOWN", "UNAVAILABLE", "UNVERIFIED"}:
                raise ValueError
        if "space_kind" in value:
            public["space_kind"] = token(value["space_kind"], "space kind")
        return public
    except (ContractError, ValueError, KeyError):
        raise HTTPException(503, "UNAVAILABLE: incomplete producer context") from None


class QualifiedScene:
    """Use a bounded local C1 snapshot and current A1 qualification for private reads."""
    def __init__(self, service, context):
        self.service, self.context = service, context

    def _read(self):
        current = qualified_context(self.context())
        snapshot = self.service.snapshot()
        binding = {key: current[key] for key in ("map_id", "revision", "generation")}
        if snapshot.get("map_binding") != binding or snapshot.get("stream_epoch") != current["stream_epoch"]:
            raise HTTPException(409, "STALE_SCENE_CONTEXT")
        return current, snapshot

    def _confirm(self, before):
        if qualified_context(self.context()) != before:
            raise HTTPException(409, "STALE_SCENE_CONTEXT")

    def snapshot(self):
        context, snapshot = self._read()
        self._confirm(context)
        return snapshot

    def get_asset(self, asset_id, revision):
        context, snapshot = self._read()
        refs = snapshot.get("sources", {}).get("assets", ())
        if not any(ref["id"] == asset_id and ref["revision"] == revision for ref in refs):
            raise KeyError("asset unavailable in current context")
        asset = self.service.get_asset(asset_id, revision)
        self._confirm(context)
        return asset


class PrivateResponses:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(API + "/"):
            return await self.app(scope, receive, send)

        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message["headers"] if k.lower() != b"cache-control"]
                message = {**message, "headers": [*headers, (b"cache-control", b"private, no-store")]}
            await send(message)

        await self.app(scope, receive, private_send)


class SessionPolicy:
    def __init__(self, access, origin):
        address = urlsplit(origin)
        if (address.scheme != "https" or not address.hostname or address.username is not None
                or address.password is not None or origin != f"https://{address.netloc}"
                or address.netloc != address.netloc.lower()):
            raise ValueError("A canonical HTTPS review origin is required")
        self.access, self.origin, self.host = access, origin, address.netloc

    def check_transport(self, request, *, mutation=False):
        if request.url.scheme != "https" or request.headers.getlist("host") != [self.host]:
            raise HTTPException(403, "REVIEW_HTTPS_ORIGIN_REQUIRED")
        origins = request.headers.getlist("origin")
        if (mutation or origins) and origins != [self.origin]:
            raise HTTPException(403, "REVIEW_ORIGIN_REQUIRED")
        if mutation:
            require_same_origin(request)

    async def query(self, operation, *args):
        try:
            return await asyncio.to_thread(operation, *args)
        except (OSError, AccessUnavailable, sqlite3.Error, RuntimeError):
            raise HTTPException(503, "REVIEW_ACCESS_UNAVAILABLE") from None

    async def authorize(self, request):
        self.check_transport(request)
        grant = await self.query(self.access.lookup, request.cookies.get(COOKIE))
        if grant is None:
            raise HTTPException(401, "REVIEW_SESSION_REQUIRED")
        return grant

    async def require_review(self, request):
        self.check_transport(request, mutation=True)
        grant = await self.authorize(request)
        if grant["role"] != "review":
            raise HTTPException(403, "REVIEW_WRITE_REQUIRED")

    def install(self, app):
        app.add_middleware(PrivateResponses)
        router = APIRouter(prefix=API)

        @router.get("/session")
        async def current(request: Request):
            return await self.authorize(request)

        @router.post("/session")
        async def login(request: Request):
            self.check_transport(request, mutation=True)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise HTTPException(415, "REVIEW_JSON_REQUIRED")
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 256:
                    raise HTTPException(413, "REVIEW_CODE_LIMIT")
                body.extend(chunk)
            try:
                # Exactly one JSON string; no schema errors can echo its contents.
                code = json.loads(body)
            except (ValueError, UnicodeError, RecursionError):
                code = None
            if not isinstance(code, str) or not SECRET.fullmatch(code):
                raise HTTPException(401, "REVIEW_CODE_INVALID")
            session = await self.query(self.access.redeem, code)
            if not session:
                raise HTTPException(401, "REVIEW_CODE_INVALID")
            response = JSONResponse({"authenticated": True})
            response.set_cookie(COOKIE, session, path=API, secure=True, httponly=True, samesite="strict")
            return response

        @router.post("/session/logout")
        async def logout(request: Request):
            self.check_transport(request, mutation=True)
            await self.query(self.access.logout, request.cookies.get(COOKIE))
            response = JSONResponse({"authenticated": False})
            response.delete_cookie(COOKIE, path=API, secure=True, httponly=True, samesite="strict")
            return response

        app.include_router(router)


def configured_owner(app, flags, environ, inputs):
    db = environ.get("ROBOT_SCOPE_EXPANSION_REVIEW_DB")
    origin = environ.get("ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN")
    if not (db and origin and (flags.multimap or flags.scene)):
        return None
    try:
        policy = SessionPolicy(ReviewAccess(db), origin)
    except ValueError:
        return None
    policy.install(app)
    owner = ExpansionOwner(authorize=policy.authorize, require_mutation=policy.require_review,
                           session_login=True)
    if inputs:
        if flags.multimap and inputs.maps_factory:
            try:
                owner.catalogue, owner.manager, owner.store = inputs.maps_factory()
            except (ImportError, OSError, ValueError):
                logging.getLogger(__name__).warning("Offline map review inputs unavailable")
        if flags.scene and callable(inputs.scene_context):
            owner.scene_context = inputs.scene_context
            if inputs.scene is not None:
                owner.scene = QualifiedScene(inputs.scene, inputs.scene_context)
    return owner
