# Track G Route Planner Software-Only Acceptance

## Scope

The acceptance is performed in an isolated clone and `feature/competition-route-planner`. No robot, Jetson, ROS command, Navigation goal, Mission start, control lease or service restart is used.

## Scenarios

### A — Order entry

COEX with HANSOT/CHICKEN_MAYO ×2 and EDIYA/AMERICANO ×1 validates as LOW, total three, two restaurants. Invalid destination, menu mismatch, same-zone restaurant, gaps/duplicates, forged derived fields, fewer than three, more than five and custom competition shapes are rejected.

### B — Recommendations

The fixture graph is pinned to an exact map and annotation revision. The bounded exact search returns BALANCED, FASTEST and SAFEST profiles, deduplicates identical paths, exposes all metric components and uses a stable tie-break. SAFEST prefers the lower-risk detour. UNKNOWN perception keeps special autonomous edges not ready.

### C — 3D

Selected, alternative and current-segment lines and stop markers are added to the existing `SceneHost`. The selected overlay is capped at 2048 points and each of two alternatives at 1024. Renderer count and peak renderer count remain one.

### D — Manual guidance

Mock poses project to a current segment, progress, remaining distance, ETA and cross-track error. Missing pose pauses. Large deviation offers recalculation. Traffic/person/alignment/ArUco are advisory. `control_authority=false` is asserted.

### E — Mission draft

The selected route resolves only semantic waypoint nodes to annotation IDs, rejects more than 32, retains segment-requirement links and idempotently calls `MissionCoordinator.create`. Start, goal, lease and motion counts remain zero.

## Expected gates

- ORDER_CATALOG_PASS
- ORDER_ENTRY_UI_PASS
- ORDER_VALIDATION_PASS
- ROUTE_GRAPH_PASS
- RECOMMENDATION_BALANCED_PASS
- RECOMMENDATION_FASTEST_PASS
- RECOMMENDATION_SAFEST_PASS
- 3D_ROUTE_PREVIEW_PASS
- MANUAL_GUIDANCE_PASS
- PERCEPTION_CONTRACT_PASS
- MISSION_DRAFT_EXPORT_PASS
- NAV2_PATH_PREVIEW_BLOCKED: `SAFE_PLAN_ONLY_NAV2_INTERFACE_NOT_AVAILABLE`
- MISSION_START_NOT_RUN
- NAVIGATION_GOAL_NOT_RUN
- CONTROL_LEASE_NOT_ACQUIRED
- ARM_NOT_RUN
- DEADMAN_NOT_RUN
- MOTION_NOT_RUN

Test commands and final counts are recorded in the completion report after all repository suites and CI finish.
