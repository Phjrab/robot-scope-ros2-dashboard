"""Authenticated DI router. Deliberately never mounted by the product app."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from robot_dashboard.expansion_contracts import ContractError
from robot_dashboard.expansion_contracts.messages import MAX_DOCUMENT_BYTES
from robot_dashboard.pcd_editing.geometry import PcdEditError
from .catalogue import Busy, Conflict


def create_router(manager, catalogue, scene, store, *, authorize, require_origin):
    if not callable(authorize) or not callable(require_origin):
        raise TypeError("host auth and origin policies are required")
    router = APIRouter(prefix="/api/v1/extensions", dependencies=[Depends(authorize)])

    async def body(request, expected_fields=None):
        outcome = require_origin(request)
        if hasattr(outcome, "__await__"):
            await outcome
        if (
            request.headers.get("content-type", "").split(";", 1)[0]
            != "application/json"
        ):
            raise HTTPException(415, "requires application/json")
        length = request.headers.get("content-length")
        if length is not None and (
            not length.isascii() or not length.isdecimal() or len(length) > 8
        ):
            raise HTTPException(400, "invalid content length")
        if length is not None and int(length) > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, "request too large")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_DOCUMENT_BYTES:
                raise HTTPException(413, "request too large")
            data.extend(chunk)

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = value
            return result

        try:
            value = json.loads(
                data,
                object_pairs_hook=unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
            )
            if not isinstance(value, dict) or (
                expected_fields is not None and set(value) != expected_fields
            ):
                raise ValueError("invalid fields")
            return value
        except (ValueError, UnicodeError, RecursionError):
            raise HTTPException(422, "invalid bounded JSON document") from None

    async def call(fn, *args, **kwargs):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except Busy:
            raise HTTPException(429, "bounded worker capacity unavailable") from None
        except Conflict:
            raise HTTPException(
                409, "stale input/revision or immutable conflict"
            ) from None
        except (FileNotFoundError, KeyError):
            raise HTTPException(404, "candidate not found") from None
        except (ContractError, PcdEditError, TypeError):
            raise HTTPException(422, "invalid candidate contract") from None
        except OSError:
            raise HTTPException(503, "private candidate storage unavailable") from None

    @router.get("/multimap/sources")
    async def sources():
        return {"sources": await call(catalogue.list)}

    @router.get("/multimap/sources/{map_id}/preview")
    async def preview(map_id: str):
        return {"preview": await call(catalogue.preview, map_id)}

    @router.post("/multimap/jobs", status_code=202)
    async def enqueue(request: Request):
        return await call(manager.enqueue, await body(request))

    @router.get("/multimap/jobs/{job_id}")
    async def status(job_id: str):
        return await call(manager.status, job_id)

    @router.post("/multimap/jobs/{job_id}/cancel")
    async def cancel(job_id: str, request: Request):
        await body(request, set())
        return await call(manager.cancel, job_id)

    @router.post("/multimap/jobs/{job_id}/review")
    async def review(job_id: str, request: Request):
        value = await body(
            request, {"expected_proposal_revision", "accepted", "manual_selection"}
        )
        return await call(
            manager.review,
            job_id,
            value["expected_proposal_revision"],
            value["accepted"],
            value["manual_selection"],
        )

    @router.post("/multimap/jobs/{job_id}/exports", status_code=201)
    async def export(job_id: str, request: Request):
        value = await body(request, {"name", "expected_proposal_revision"})
        return await call(
            manager.export, job_id, value["name"], value["expected_proposal_revision"]
        )

    @router.get("/multimap/exports/{export_id}")
    async def get_export(export_id: str):
        return await call(store.get, export_id)

    @router.get("/scene/snapshot")
    async def snapshot():
        return await call(scene.snapshot)

    return router
