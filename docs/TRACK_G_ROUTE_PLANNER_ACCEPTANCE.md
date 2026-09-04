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

## 2026-09-04 software verification

- Base audit: branch started at `520a9b7`; latest `origin/main` advanced through `718a625`
  to `ee315d2`.
- Main integration: both main updates were merged into the feature branch only. Their C4
  goal-progress and localization-health evidence, bounded SportModeState diagnostics, and
  Foxy `numpy.float32` telemetry compatibility remain intact.
- Python: `1045/1045 PASS` under the repository-pinned quality environment and coverage runner.
- JavaScript unit: `274/274 PASS`.
- Playwright E2E: `33/33 PASS`, including the full Route Planner software-only workflow.
- Frontend syntax: `55/55 modules PASS`.
- Ruff, mypy, tracked-source secret scan and `git diff --check`: `PASS`.
- Hardware/Nav2 execution: `NOT_RUN`. Mission start, Navigation goal, lease, ARM, deadman,
  service restart and robot motion were not invoked.

One pre-existing Go2 dashboard-supervisor test exceeded its three-second timeout on the first
coverage run. It passed immediately in isolation and the complete `1045`-test coverage rerun
passed, so no product assertion was relaxed.
