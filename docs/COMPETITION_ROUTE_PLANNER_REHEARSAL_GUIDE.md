# Competition Route Planner Rehearsal Guide

## Purpose and safety boundary

Rehearsal Mode runs the competition order-to-delivery workflow with fixture data on a development MacBook or mock backend. The banner is always explicit:

```text
REHEARSAL — VIRTUAL DATA — ROBOT WILL NOT MOVE
```

The mode never creates or starts a Mission, activates navigation, submits a goal, acquires control, arms, asserts deadman, emits velocity, calls Sport APIs, or restarts a service. It does not read live service state into replay results.

The production UI is hidden unless the server process sets:

```bash
ROBOT_SCOPE_ROUTE_PLANNER_REHEARSAL=1
```

This flag is read only by the server when the Route Planner coordinator is constructed. The browser cannot enable it. GP1 scenario files must also be installed under the repository fixture root; no client-supplied path is accepted.

## Operator workflow

1. Enter an order and calculate recommendations normally.
2. Select one revision-pinned route.
3. Open the Development / Rehearsal section and choose a fixed scenario.
4. Start Rehearsal Mode and verify the virtual-data banner.
5. Use RESET, PLAY, PAUSE, STEP, 0.5x/1x/2x/5x speed, or timeline scrub.
6. Inspect expected/actual replay state, advisory state, virtual pose, current segment, and cargo timeline.
7. Use rehearsal-only pickup and drop-off confirmations.
8. Inspect Mission Dry-Run and export the bounded JSON/Markdown report response.
9. Select EXIT before returning to normal Route Planner mutations.

During an active session, the Route Planner server rejects order/graph/recommendation changes, manual guidance mutations, pickup/drop-off guidance confirmations, and real Mission draft export. The pure preview endpoint remains safe.

## Virtual pose and 3D progress

The server interpolates pose by polyline distance and derives yaw from the active segment tangent. Output is labeled `VIRTUAL ROBOT` and `VIRTUAL_ROUTE_REPLAY`, uses the `map` frame, and declares a maximum update rate of 10 Hz. OFF-ROUTE injects a deterministic 2 m lateral offset and yields `REPLAN_RECOMMENDED`.

The existing Cockpit `SceneHost` remains the only renderer. Route state changes the selected route and progressively clipped current-segment overlay. No second renderer and no actual Nav2 path layer are created; the UI reports `UNAVAILABLE_IN_REHEARSAL` for that layer. The virtual pose is shown as an explicit textual readout and as the endpoint of the progressive current-segment overlay.

## Deterministic decisions and explainability

Each server snapshot replays only the applied prefix of a GP1 scenario. STEP applies exactly one event; scrub applies all events at or before its position. PLAY advances server-authoritative position from the injected server clock and the selected fixed speed.

Recommendation explanations are deterministic templates derived from travel time, food wait, signal wait, distance, risk, crosswalk count, underpass count, turn count, and special-behavior count. No LLM output is used.

## Cargo workflow

The GP2 `DeliveryWorkflow` owns rehearsal cargo state. Confirmation changes only this in-memory session. It enforces ordered restaurants and capacity five, rejects early drop-off, and records bounded confirmation audit entries. No dock, sit, stand, gait, or other action owner is invoked.

## Mission dry-run

`POST /api/v1/route-planner/routes/{route_id}/mission-dry-run` resolves the same semantic waypoint compiler used by the existing Mission export. It returns annotation IDs, labels, arrival tolerance, hold time, operator confirmation, special-segment requirement links, map/revision pins, waypoint count, eligibility, and rejection reason.

Dry-run returns `mission_created=false`, `mission_started=false`, `navigation_goal_submitted=false`, and zero side-effect counters. Revision mismatch, missing annotation, no waypoint, and more than 32 waypoints fail closed. Existing Mission export behavior remains a separate explicit operation and is disabled while rehearsal is active.

## Rehearsal endpoints

```text
GET  /api/v1/route-planner/rehearsal/scenarios
POST /api/v1/route-planner/rehearsal/start
POST /api/v1/route-planner/rehearsal/control
GET  /api/v1/route-planner/rehearsal/report
POST /api/v1/route-planner/routes/{route_id}/mission-dry-run
```

Requests use fixed identifiers and bounded strict bodies. No endpoint accepts a filesystem path, ROS name, host, URL, or action-server identifier.

## Known integration boundary

Route Planner can enforce its own mutation fence and requires navigation, Mission, and mapping to be idle at entry. Disabling every independent Control/Nav/Mission API across the whole application would require changes to core runtime/dependency gates outside the GP3 allowlist. That work was deliberately not performed and is recorded for GP4 as:

```text
GLOBAL_REHEARSAL_INTERLOCK=BLOCKED_BY_CORE_INTEGRATION
```
