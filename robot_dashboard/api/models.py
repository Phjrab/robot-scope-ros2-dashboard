"""Strict bounded request models shared by domain routers."""

from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSelection(StrictRequest):
    camera: str | None = Field(default=None, max_length=255)
    pointcloud: str | None = Field(default=None, max_length=255)
    odometry: str | None = Field(default=None, max_length=255)
    occupancy_grid: str | None = Field(default=None, max_length=255)


class RobotTarget(StrictRequest):
    ip: str = Field(min_length=7, max_length=45)
    robot_type: str = Field(min_length=2, max_length=32)
    hostname: str | None = Field(default=None, max_length=253)


class RobotDiscoveryRequest(StrictRequest):
    robot_type: str = Field(min_length=2, max_length=32)


class MapSaveRequest(StrictRequest):
    name: str
    create_2d: bool = True


class CloudPointLimitRequest(StrictRequest):
    max_points: int | None


class SavedMapRenameRequest(StrictRequest):
    name: str


class SavedMapConvert2DRequest(StrictRequest):
    name: str
    z_min: float = Field(strict=True, ge=-20.0, le=20.0)
    z_max: float = Field(strict=True, ge=-20.0, le=20.0)
    resolution: float = Field(strict=True, ge=0.01, le=1.0)
    noise_radius: float = Field(default=0.1, strict=True, ge=0.01, le=2.0)
    min_neighbors: int = Field(default=10, strict=True, ge=1, le=1_000)
    background: Literal["unknown", "free"] = "unknown"


class SavedMapEditRun(StrictRequest):
    start: int = Field(strict=True, ge=0)
    length: int = Field(strict=True, ge=1)
    value: int = Field(strict=True)


class SavedMapEditedCopyRequest(StrictRequest):
    name: str
    source_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    runs: list[SavedMapEditRun] = Field(min_length=1, max_length=10_000)


class MapAnnotationPose(StrictRequest):
    x: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    y: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    yaw: float = Field(strict=True, ge=-3.141592653589793, le=3.141592653589793)


class MapAnnotationVertex(StrictRequest):
    x: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    y: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)


class MapPointAnnotation(StrictRequest):
    id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    type: Literal["POI", "HOME", "DOCK", "INSPECTION_POINT"]
    name: str = Field(min_length=1, max_length=64)
    pose: MapAnnotationPose


class MapPolygonAnnotation(StrictRequest):
    id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    type: Literal["KEEP_OUT", "SLOW_ZONE", "WAIT_ZONE"]
    name: str = Field(min_length=1, max_length=64)
    vertices: list[MapAnnotationVertex] = Field(min_length=3, max_length=64)


class SavedMapAnnotationsRequest(StrictRequest):
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_annotation_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    points: list[MapPointAnnotation] = Field(default_factory=list, max_length=64)
    polygons: list[MapPolygonAnnotation] = Field(default_factory=list, max_length=32)


class ControlArmRequest(StrictRequest):
    input_source: Literal["keyboard", "gamepad"]


class ControlLeaseRequest(StrictRequest):
    lease_id: str = Field(min_length=16, max_length=256)


class ControlStopRequest(StrictRequest):
    reason: str = Field(default="dashboard_button", min_length=1, max_length=128)


class ControlClearEstopRequest(StrictRequest):
    confirmed: bool = Field(strict=True)


class NavigationParameterPatchRequest(StrictRequest):
    base_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    values: Dict[str, Any] = Field(min_length=1, max_length=27)


class NavigationStartRequest(StrictRequest):
    map_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    parameters_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class NavigationStopRequest(StrictRequest):
    pass


class NavigationLocalizationStartRequest(NavigationStartRequest):
    pass


class NavigationLocalizationStopRequest(StrictRequest):
    pass


class NavigationPose(StrictRequest):
    x: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    y: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    yaw: float = Field(strict=True, ge=-3.141592653589793, le=3.141592653589793)


class NavigationPoseRequest(StrictRequest):
    map_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    pose: NavigationPose


class NavigationLocalizationPoseRequest(NavigationPoseRequest):
    confirmed: bool = Field(strict=True)


class NavigationGoalRequest(NavigationPoseRequest):
    confirmed: bool = Field(strict=True)


class NavigationAnnotationGoalRequest(StrictRequest):
    map_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    confirmed: bool = Field(strict=True)


class NavigationCancelRequest(StrictRequest):
    goal_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")


class NavigationClearCostmapsRequest(StrictRequest):
    scope: Literal["both"]


class RelocalizationSeedRequest(StrictRequest):
    mode: Literal["REGION", "POSE", "NONE"]
    x: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    y: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    yaw: float = Field(strict=True, ge=-3.141592653589793, le=3.141592653589793)
    radius_m: float = Field(strict=True, ge=0.0, le=10.0)
    yaw_half_range: float = Field(strict=True, ge=0.0, le=3.141592653589793)


class RelocalizationStartRequest(StrictRequest):
    map_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pcd_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    source_pcd_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: RelocalizationSeedRequest


class RelocalizationCancelRequest(StrictRequest):
    pass


class MissionWaypointRequest(StrictRequest):
    annotation_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    arrival_tolerance: float | None = Field(default=None, strict=True, ge=0.05, le=2.0)
    hold_seconds: float = Field(default=0.0, strict=True, ge=0.0, le=300.0)
    requires_operator_confirmation: bool = Field(default=False, strict=True)
    label: str = Field(min_length=1, max_length=64)


class MissionCreateRequest(StrictRequest):
    label: str = Field(min_length=1, max_length=64)
    map_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    waypoints: list[MissionWaypointRequest] = Field(min_length=1, max_length=32)


class MissionActionRequest(StrictRequest):
    pass


class ServiceLifecycleRequest(StrictRequest):
    confirmed: bool = Field(strict=True)


class ControlBridgeLifecycleRequest(StrictRequest):
    confirmed: bool = Field(strict=True)


class DatasetCaptureStartRequest(StrictRequest):
    sources: Literal["go2_front", "realsense_color", "both"]
    capture_hz: float = Field(default=1.0, ge=0.2, le=5.0)
    label: str = Field(default="", max_length=64)

    @field_validator("capture_hz", mode="before")
    @classmethod
    def validate_capture_hz(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("capture_hz must be a number")
        return float(value)


class DatasetCaptureStopRequest(StrictRequest):
    session_id: str = Field(pattern=r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{32}$")


class CompetitionLockRequest(StrictRequest):
    confirmation: Literal["LOCK"]


class CompetitionUnlockRequest(StrictRequest):
    confirmation: Literal["UNLOCK"]
    stationary_confirmed: bool = Field(strict=True)


class CompetitionModeRequest(StrictRequest):
    mode: Literal["MANUAL", "ASSISTED", "AUTO", "SAFE_STOP", "SHADOW"]
    confirmation: str = Field(min_length=4, max_length=9)


class RouteOrderLineRequest(StrictRequest):
    sequence: int = Field(strict=True, ge=1, le=5)
    restaurant_id: Literal["DOMINO", "HANSOT", "EDIYA"]
    menu_id: Literal[
        "SUPER_SUPREME", "CHEESE_PIZZA", "SPAM_KIMCHI",
        "CHICKEN_MAYO", "AMERICANO", "CAFE_LATTE",
    ]
    quantity: int = Field(strict=True, ge=1, le=5)


class RouteOrderCreateRequest(StrictRequest):
    label: str = Field(min_length=1, max_length=64)
    destination_id: Literal["COEX", "WHIMOON", "GANGNAM_POLICE", "GTX_SITE"]
    lines: list[RouteOrderLineRequest] = Field(min_length=2, max_length=5)
    order_started_at: str | None = Field(default=None, max_length=32)
    locked: bool = Field(default=False, strict=True)


class RouteOrderUpdateRequest(RouteOrderCreateRequest):
    base_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class RouteGraphPointRequest(StrictRequest):
    x: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    y: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)


class RouteGraphNodeRequest(StrictRequest):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    annotation_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    role: Literal[
        "START", "INTERSECTION", "SAFE_HOLD", "RESTAURANT_APPROACH",
        "RESTAURANT_DOCK", "DESTINATION_APPROACH", "DESTINATION_DOCK",
        "CROSSWALK_WAIT", "CROSSWALK_ENTRY", "CROSSWALK_EXIT",
        "UNDERPASS_ENTRY", "UNDERPASS_EXIT",
    ]
    zone_id: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    venue_id: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    label: str = Field(min_length=1, max_length=64)
    manual_guidance: bool = Field(strict=True)
    autonomous_eligible: bool = Field(strict=True)


class RouteGraphEdgeRequest(StrictRequest):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    from_: str = Field(alias="from", pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    to: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    type: Literal["NORMAL_WALKWAY", "CROSSWALK", "UNDERPASS", "DOCKING_APPROACH"]
    bidirectional: bool = Field(strict=True)
    polyline: list[RouteGraphPointRequest] = Field(min_length=2, max_length=128)
    distance_m: float = Field(strict=True, gt=0.0, le=100_000.0)
    nominal_speed_mps: float = Field(strict=True, ge=0.01, le=3.0)
    risk: float = Field(strict=True, ge=0.0, le=100.0)
    requirements: list[Literal[
        "TRAFFIC_GREEN", "PEDESTRIAN_CLEAR", "CROSSWALK_ALIGNMENT",
        "LANE_BOUNDARY_VALID", "ARUCO_DOCKING", "SPECIAL_GAIT",
        "OPERATOR_CONFIRMATION",
    ]] = Field(default_factory=list, max_length=7)
    allow_manual: bool = Field(strict=True)
    allow_autonomous: bool = Field(strict=True)
    allow_replan: bool = Field(strict=True)
    allow_turning: bool = Field(strict=True)
    allow_lateral_motion: bool = Field(strict=True)
    speed_limit_mps: float = Field(strict=True, ge=0.01, le=3.0)
    expected_wait_s: float = Field(strict=True, ge=0.0, le=600.0)
    penalty_risk: float = Field(strict=True, ge=0.0, le=100.0)


class RouteGraphPutRequest(StrictRequest):
    schema_version: Literal[1]
    map_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_graph_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    nodes: list[RouteGraphNodeRequest] = Field(min_length=2, max_length=128)
    edges: list[RouteGraphEdgeRequest] = Field(min_length=1, max_length=512)


class RouteRecommendationRequest(StrictRequest):
    order_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    order_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_node_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    operation_mode: Literal["MANUAL_GUIDANCE", "AUTO_NAV2"]


class RouteSelectionRequest(StrictRequest):
    route_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class RouteGuidanceStartRequest(StrictRequest):
    route_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    route_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class RouteGuidanceStopRequest(StrictRequest):
    pass


class RoutePickupRequest(StrictRequest):
    venue_id: Literal["DOMINO", "HANSOT", "EDIYA"]


class RouteDropoffRequest(StrictRequest):
    destination_id: Literal["COEX", "WHIMOON", "GANGNAM_POLICE", "GTX_SITE"]


class RouteMissionExportRequest(StrictRequest):
    route_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
