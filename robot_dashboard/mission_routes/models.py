"""Strict versioned authoring contracts; no hardware addresses or actions."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Hex24 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{24}$")]
Revision = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Identity = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
RequestId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,64}$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Pose(StrictModel):
    x: float = Field(ge=-10000, le=10000)
    y: float = Field(ge=-10000, le=10000)
    yaw: float = Field(ge=-math.pi, le=math.pi)


class Family(StrictModel):
    family_id: Hex24
    family_revision: Revision
    pcd_map_id: Hex24
    pcd_revision: Revision
    occupancy_map_id: Hex24
    occupancy_revision: Revision


class Visit(StrictModel):
    visit_id: Identity
    label: Label
    kind: Literal["STOP", "TASK", "PASS_THROUGH"] = "STOP"
    target: Literal["annotation_ref", "mission_local_pose"] = "mission_local_pose"
    annotation_id: Hex24 | None = None
    pose: Pose | None = None
    heading_yaw: float | None = Field(default=None, ge=-math.pi, le=math.pi)
    hold_seconds: float = Field(default=0.0, ge=0, le=300)
    requires_operator_confirmation: bool = False
    after_arrival_confirmation: bool = False
    arrival_tolerance: float | None = Field(default=None, ge=0.05, le=2)
    speed: Literal["DEFAULT", "SLOW", "NORMAL"] = "DEFAULT"
    action: Literal["none", "photo", "sit_then_rise", "dock"] = "none"

    @model_validator(mode="after")
    def exclusive_target(self):
        if self.target == "annotation_ref":
            if self.annotation_id is None or self.pose is not None:
                raise ValueError("annotation_ref requires only annotation_id")
        elif self.pose is None or self.annotation_id is not None:
            raise ValueError("mission_local_pose requires only pose")
        if self.target == "mission_local_pose" and self.heading_yaw is not None:
            raise ValueError("local pose uses pose.yaw; heading_yaw overrides annotations only")
        return self


class RouteRef(StrictModel):
    route_id: Hex24
    revision: Revision


class DefinitionInput(StrictModel):
    label: Label
    map_family: Family
    annotation_revision: Revision
    mode: Literal["FLEXIBLE", "CORRIDOR", "STRICT"] = "FLEXIBLE"
    visits: list[Visit] = Field(min_length=1, max_length=32)
    route_ref: RouteRef | None = None

    @model_validator(mode="after")
    def unique_visits(self):
        if len({v.visit_id for v in self.visits}) != len(self.visits):
            raise ValueError("visit_id must be unique; repeated POIs need separate visits")
        return self


class CreateRequest(DefinitionInput):
    request_id: RequestId


class UpdateRequest(CreateRequest):
    base_revision: Revision


class RevisionRequest(StrictModel):
    request_id: RequestId
    revision: Revision


class PreviewRequest(RevisionRequest):
    start_source: Literal["current_operational_pose", "hypothetical_preview_start"]
    start: Pose | None = None

    @model_validator(mode="after")
    def start_is_explicit(self):
        if (self.start_source == "hypothetical_preview_start") != (self.start is not None):
            raise ValueError("only a hypothetical preview accepts an explicit start")
        return self


class RunActionRequest(StrictModel):
    request_id: RequestId
    confirmation_token: Identity | None = None


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
