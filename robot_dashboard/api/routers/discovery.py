"""Bounded robot discovery and target-selection HTTP transport."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from ...application.runtime import ApplicationRuntime
from ...discovery import (
    DiscoveryBusy,
    DiscoveryUnavailable,
    UnknownRobotType,
    public_robot_types,
)
from ...ros_agent import RosAgent
from ..dependencies import require_component, require_same_origin, runtime_from_request
from ..models import RobotDiscoveryRequest, RobotTarget


router = APIRouter()


def _agent(runtime: ApplicationRuntime) -> RosAgent:
    return require_component(runtime.agent, "ROS agent is not configured")


@router.get("/api/v1/robots/types")
async def robot_types(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    selected_type = (
        runtime.agent.robot_target_snapshot()["robot_type"]
        if runtime.agent is not None
        else ""
    )
    return {"types": public_robot_types(), "selected_type": selected_type}


@router.post("/api/v1/robots/discover")
async def discover_robots(
    request: Request,
    body: RobotDiscoveryRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    try:
        return await asyncio.to_thread(runtime.robot_discovery.discover, body.robot_type)
    except UnknownRobotType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DiscoveryBusy as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except DiscoveryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/v1/robot")
async def set_robot(
    request: Request,
    target: RobotTarget,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    try:
        await asyncio.to_thread(
            runtime.robot_discovery.validate_target,
            target.robot_type,
            target.ip,
        )
        selected = await asyncio.to_thread(
            _agent(runtime).set_robot_target,
            target.ip,
            target.robot_type,
            target.hostname,
        )
        if selected.get("changed"):
            runtime.control_bindings.clear()
        return {
            "robot": selected,
            "robot_ip": selected["ip"],
            "robot_type": selected["robot_type"],
            "hostname": selected["hostname"],
            "model": selected["model"],
        }
    except (UnknownRobotType, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DiscoveryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/api/v1/robot")
async def disconnect_robot(request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    selected = await asyncio.to_thread(_agent(runtime).disconnect_robot_target)
    runtime.control_bindings.clear()
    return {
        "robot": selected,
        "robot_ip": "",
        "robot_type": selected["robot_type"],
        "hostname": "",
        "model": selected["model"],
    }
