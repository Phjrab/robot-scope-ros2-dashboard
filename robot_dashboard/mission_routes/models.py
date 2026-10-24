"""Strict versioned authoring contracts; no hardware addresses or actions."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_serializer, model_validator

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


class CompetitionAction(StrictModel):
    """PROPOSED v0.1 port, deliberately separate from legacy arrival_action."""
    schema_version: Literal["mission-action.v0.1"] = "mission-action.v0.1"
    step_id: Identity
    type: Literal["NAVIGATE_ADAPTIVE", "TRAFFIC_STOP_AND_GO", "TRAVERSE_TERRAIN", "PARK_SIT_HOLD", "FINISH_CROSSING"]
    zone_id: Label | None = None
    signal_id: Label | None = None
    crossing_id: Label | None = None
    corridor_id: Label | None = None
    avoidance_profile: Label | None = None
    terrain_segment: Label | None = None
    gait_profile: Label | None = None
    approach_heading: float = Field(default=0, ge=-math.pi, le=math.pi)
    dwell_seconds: float = Field(default=2, ge=2, le=300)
    sit_seconds: float = Field(default=5, ge=5, le=300)
    exit_pose: Pose | None = None
    timeout_seconds: float = Field(default=120, ge=10, le=3600)

    @model_validator(mode="after")
    def required_references(self):
        required = {
            "NAVIGATE_ADAPTIVE": ("avoidance_profile",),
            "TRAFFIC_STOP_AND_GO": ("zone_id", "signal_id", "crossing_id"),
            "TRAVERSE_TERRAIN": ("terrain_segment", "gait_profile"),
            "PARK_SIT_HOLD": ("zone_id",), "FINISH_CROSSING": ("zone_id",),
        }[self.type]
        if any(getattr(self, key) is None for key in required):
            raise ValueError("action reference missing: " + ", ".join(required))
        return self


class CompetitionDefinition(StrictModel):
    schema_version: Literal["competition.v0.1"] = "competition.v0.1"
    review_status: Literal["DRAFT", "REVIEWED"] = "DRAFT"
    arena_id: Label = "DRAFT"
    arena_revision: Label = "DRAFT"
    model_revision: Label = "DRAFT"
    profile_revision: Label = "DRAFT"
    rules_version: Label = "rulebook-20261015"
    maintenance_limit: Literal[2] = 2
    maintenance_counts_in_total: Literal[True] = True
    resume_position_rule: Label = "PROPOSED: 규정 재개 위치 확인 필요"


class Visit(StrictModel):
    visit_id: Identity
    label: Label
    kind: Literal["STOP", "TASK", "PASS_THROUGH"] = "STOP"
    target: Literal["annotation_ref", "mission_local_pose", "unplaced"] = "mission_local_pose"
    annotation_id: Hex24 | None = None
    pose: Pose | None = None
    heading_yaw: float | None = Field(default=None, ge=-math.pi, le=math.pi)
    hold_seconds: float = Field(default=0.0, ge=0, le=300)
    requires_operator_confirmation: bool = False
    after_arrival_confirmation: bool = False
    arrival_tolerance: float | None = Field(default=None, ge=0.05, le=2)
    speed: Literal["DEFAULT", "SLOW", "NORMAL"] = "DEFAULT"
    action: Literal["none", "photo", "sit_then_rise", "dock"] = "none"
    mission_action: CompetitionAction | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler):
        result = handler(self)
        if self.mission_action is None:
            result.pop("mission_action", None)
        return result

    @model_validator(mode="after")
    def exclusive_target(self):
        if self.target == "annotation_ref":
            if self.annotation_id is None or self.pose is not None:
                raise ValueError("annotation_ref requires only annotation_id")
        elif self.target == "unplaced":
            if self.pose is not None or self.annotation_id is not None or self.mission_action is None:
                raise ValueError("unplaced is only an explicit competition draft without coordinates")
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
    competition: CompetitionDefinition | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler):
        result = handler(self)
        if self.competition is None:
            result.pop("competition", None)
        return result

    @model_validator(mode="after")
    def unique_visits(self):
        if len({v.visit_id for v in self.visits}) != len(self.visits):
            raise ValueError("visit_id must be unique; repeated POIs need separate visits")
        actions = [v.mission_action for v in self.visits if v.mission_action]
        if bool(actions) != bool(self.competition) or self.competition and len(actions) != len(self.visits):
            raise ValueError("competition definitions require one versioned action per visit")
        if len({a.step_id for a in actions}) != len(actions):
            raise ValueError("step_id must be unique, including repeated zones")
        if self.competition:
            if any(v.action != "none" or v.hold_seconds != 0 or v.arrival_tolerance is not None or v.speed != "DEFAULT" or v.requires_operator_confirmation or v.after_arrival_confirmation or v.kind == "PASS_THROUGH" for v in self.visits):
                raise ValueError("competition uses action evidence; legacy actions, holds, overrides and operator confirmations are unavailable")
            if self.competition.review_status == "REVIEWED" and (any(v.target == "unplaced" for v in self.visits) or any(getattr(self.competition, key) == "DRAFT" for key in ("arena_id", "arena_revision", "model_revision", "profile_revision"))):
                raise ValueError("review requires placed visits and explicit revision pins")
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


class FixtureRunRequest(RevisionRequest):
    scenario: Literal["normal", "red", "unknown", "one_foot", "stale_image", "missing_pose", "obstacle", "nav_failure"] = "normal"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
