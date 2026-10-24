"""PROPOSED shared-contract v0.1 adapters. No ROS, camera or command publisher.

Capabilities are deployment facts, not authoring flags. Production registration
is intentionally absent pending VM integration and robot qualification.
"""
from __future__ import annotations

import copy
import math
import secrets
from typing import Literal

from pydantic import Field

from .models import CompetitionAction, CompetitionDefinition, Identity, Label, Pose, StrictModel

REQUIREMENTS = {
    "NAVIGATE_ADAPTIVE": ("navigation_adapter", "pose_to_body", "collision_observations", "command_arbiter"),
    "TRAFFIC_STOP_AND_GO": ("navigation_adapter", "signal_detector", "signal_state", "feet_evidence", "physical_stop", "command_arbiter"),
    "TRAVERSE_TERRAIN": ("navigation_adapter", "terrain_gait_executor", "pose_to_body", "command_arbiter"),
    "PARK_SIT_HOLD": ("full_body_containment", "posture_executor", "physical_stop", "command_arbiter"),
    "FINISH_CROSSING": ("full_body_crossing", "pose_to_body", "command_arbiter"),
}


def capabilities():
    from .competition_assets import arena_manifest, vm_evidence
    evidence = vm_evidence()
    return {
        "schema_version": "mission-action-registry.v0.1", "contract_status": "PROPOSED",
        "execution_owner": "onboard_backend", "native_enabled": False,
        "actions": {kind: {
            "version": "mission-action.v0.1", "mode": "fixture", "stage": "PRESENT",
            "native_enabled": False, "fixture_enabled": True,
            "components": [{"id": name, "stage": None, "status": "UNCONNECTED", "reason": f"{name.upper()}_UNCONNECTED"} for name in requirements],
        } for kind, requirements in REQUIREMENTS.items()},
        "arena": arena_manifest(), "vm_evidence": evidence,
        "vm_limitations": {"detector":"ADAPTER_IMPLEMENTED / INPUT_REQUIRED", "color_fsm":"VM_SYNTHETIC_VERIFIED", "feet":"CANDIDATE_GEOMETRY_ONLY", "native_nav2":"NOT_RUN", "real_rgb":False, "jetson":"NOT_RUN"},
        "notice": "VM 합성 검증과 온보드 실장비 연결은 별도입니다. detector 입력·발 실측·native Nav2·Jetson 검증은 아직 필요합니다.",
    }


def arena_view(manifest, *, map_id=None, map_revision=None, arena_revision=None):
    """Only exact reviewed alignment pins may permit an overlay; GLB != map.

    This diagnostic projection does not load assets or alter transforms. The
    model team's adapter supplies a verified T_map_arena_design, never a GLB pose.
    """
    manifest = manifest or {}
    alignment = manifest.get("alignment") or {}
    matrix = alignment.get("T_map_arena_design")
    valid_matrix = isinstance(matrix, list) and len(matrix) == 16 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in matrix)
    if valid_matrix:
        # Row-major rigid transform, not a scale/shear or GLB axis relabeling.
        rows = [matrix[0:3], matrix[4:7], matrix[8:11]]
        determinant = sum(rows[0][i] * (rows[1][(i+1)%3] * rows[2][(i+2)%3] - rows[1][(i+2)%3] * rows[2][(i+1)%3]) for i in range(3))
        valid_matrix = (all(abs(a-b) < 1e-6 for a, b in zip(matrix[12:16], [0, 0, 0, 1]))
                        and all(abs(sum(a*b for a, b in zip(rows[i], rows[j])) - (1 if i == j else 0)) < 1e-6 for i in range(3) for j in range(3))
                        and abs(determinant - 1) < 1e-6)
    aligned = bool(map_id and map_revision and arena_revision and valid_matrix and alignment.get("status") == "VERIFIED" and alignment.get("map_id") == map_id and alignment.get("map_revision") == map_revision and manifest.get("revision") == arena_revision and alignment.get("arena_revision") == arena_revision)
    return {"status": "ALIGNED" if aligned else "ALIGNMENT_UNVERIFIED", "pose_overlay_allowed": aligned,
            "view_mode": "aligned" if aligned else "side_by_side_design_coordinates", "design_frame": "arena_design", "design_up": "Z", "visual_up": "Y", "units": "m", "quaternion_order": "xyzw", "handedness": "right",
            "matrix_layout": "row_major", "arena_id": manifest.get("arena_id"), "revision": manifest.get("revision"), "visual_asset": copy.deepcopy(manifest.get("visual_asset")),
            "reason": None if aligned else "MODEL_MANIFEST_OR_EXACT_ALIGNMENT_UNAVAILABLE"}


def template_visits():
    specs = [
        ("장애물 구간", "NAVIGATE_ADAPTIVE", {"avoidance_profile": "DRAFT"}),
        ("신호 1", "TRAFFIC_STOP_AND_GO", {"zone_id": "DRAFT-stop-1", "signal_id": "DRAFT-signal-1", "crossing_id": "DRAFT-crossing-1"}),
        ("경사·계단", "TRAVERSE_TERRAIN", {"terrain_segment": "DRAFT", "gait_profile": "DRAFT"}),
        ("신호 2", "TRAFFIC_STOP_AND_GO", {"zone_id": "DRAFT-stop-2", "signal_id": "DRAFT-signal-2", "crossing_id": "DRAFT-crossing-2"}),
        ("주차", "PARK_SIT_HOLD", {"zone_id": "DRAFT-parking"}),
        ("OUT 완전 통과", "FINISH_CROSSING", {"zone_id": "DRAFT-out"}),
    ]
    from .competition_assets import arena_manifest
    arena = arena_manifest()
    metadata = CompetitionDefinition().model_dump()
    if arena['available']:
        metadata.update(arena_id=arena['arena_id'], arena_revision=arena['revision'], model_revision=arena['visual_asset']['sha256'])
        for _, kind, params in specs:
            if kind == 'TRAFFIC_STOP_AND_GO':
                number = params['signal_id'].rsplit('-', 1)[-1]
                params.update(zone_id=f'stop_zone_{int(number):02d}', signal_id=f'signal_{int(number):02d}')
    return {"competition": metadata, "visits": [
        {"visit_id": secrets.token_hex(16), "label": label, "kind": "TASK", "target": "unplaced", "pose": None,
         "mission_action": CompetitionAction(step_id=secrets.token_hex(16), type=kind, **params).model_dump()}
        for label, kind, params in specs], "notice": "DRAFT · 순서·좌표 미확정. 각 방문 위치와 규정 순서를 검토하세요. 실제 goal을 만들지 않습니다."}


def readiness(definition):
    registry = capabilities()
    steps = []
    for visit in definition["visits"]:
        action = visit.get("mission_action")
        if not action:
            continue
        reasons = [item["reason"] for item in registry["actions"][action["type"]]["components"]]
        if visit["target"] == "unplaced":
            reasons.append("STEP_COORDINATES_DRAFT")
        if action["type"] == "TRAFFIC_STOP_AND_GO" and action["exit_pose"] is None:
            reasons.append("FRESH_EXIT_LEG_TARGET_REQUIRED")
        steps.append({"visit_id": visit["visit_id"], "step_id": action["step_id"], "type": action["type"], "status": "BLOCKED", "blocking_reasons": reasons})
    return {"status": "BLOCKED", "mode": "native", "steps": steps, "blocking_reasons": ["COMPETITION_ADAPTER_UNCONNECTED"], "registry": registry}


class Evidence(StrictModel):
    """Trusted adapter input only. No public HTTP observation ingestion.

    source_age_s must be computed by a clock-aware adapter (not subtraction of
    monotonic clocks on separate hosts); receipt time stays inside the executor.
    """
    schema_version: Literal["competition-evidence.v0.1"] = "competition-evidence.v0.1"
    producer_id: Label
    producer_epoch: Label
    sequence: int = Field(ge=0)
    source_stamp_ns: str = Field(pattern=r"^[0-9]{1,24}$")
    source_clock: Literal["fixture", "synchronized_ros", "synchronized_utc"]
    frame_id: Literal["map"] = "map"
    evidence_type: Literal["fixture", "robot_observation"]
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_age_s: float = Field(ge=0, le=3600)
    owner_id: Label
    mission_run_id: Identity
    step_id: Identity
    goal_id: Identity
    goal_generation: int = Field(ge=1)
    goal_state: Literal["ACTIVE", "SUCCEEDED", "CANCELED", "FAILED"] = "ACTIVE"
    cancel_ack: bool = False
    hold_ack: bool = False
    pose: Pose | None = None
    path_clear: bool = False
    obstacle_state: Literal["FOLLOWING", "REPLANNING", "WAIT_OBSTACLE", "SENSOR_UNAVAILABLE", "GOAL_REACHED", "FAILED"] = "FOLLOWING"
    obstacle_source: Label | None = None
    observation_age_s: float | None = Field(default=None, ge=0)
    planned_path_revision: Label | None = None
    minimum_clearance_m: float | None = Field(default=None, ge=0)
    signal_id: Label | None = None
    crossing_id: Label | None = None
    raw_state: Literal["RED", "GREEN", "UNKNOWN", "AMBIGUOUS"] = "UNKNOWN"
    stable_state: Literal["RED", "GREEN", "UNKNOWN", "AMBIGUOUS"] = "UNKNOWN"
    confidence: float | None = Field(default=None, ge=0, le=1)
    quality_flags: list[Label] = Field(default_factory=list, max_length=16)
    roi_xyxy_native: list[int] | None = Field(default=None, min_length=4, max_length=4)
    native_image_size: list[int] | None = Field(default=None, min_length=2, max_length=2)
    exposure_metadata: dict[str, float] = Field(default_factory=dict, max_length=16)
    model_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    preprocess_profile: Label | None = None
    # Image handles are diagnostics only; the UI never classifies their colors.
    native_image: Label | None = None
    processed_image: Label | None = None
    zone_id: Label | None = None
    front_left_status: Literal["INSIDE", "OUTSIDE", "UNKNOWN"] = "UNKNOWN"
    front_right_status: Literal["INSIDE", "OUTSIDE", "UNKNOWN"] = "UNKNOWN"
    feet_evidence_kind: Literal["SIM_GT", "KINEMATIC", "VISUAL", "PROXY"] = "PROXY"
    body_motion_status: Literal["STOPPED", "MOVING", "UNKNOWN"] = "UNKNOWN"
    full_body_inside: bool = False
    posture: Literal["SIT", "STAND", "UNKNOWN"] = "UNKNOWN"
    full_body_crossed: bool = False
    terrain_complete: bool = False
