# Route Planner Advisory Behavior Contract

This contract defines software-only competition decisions derived from the existing Route Planner route, guidance, order, and perception contracts. An advisory describes what an operator or a future separately owned action layer may consider. It is never a command and grants no motion authority.

## Authority boundary

The behavior package has no adapter for velocity, ROS, Nav2 actions, Mission start, lease, ARM/deadman, or sit/stand requests. It neither imports nor calls `ControlManager`, `NavigationCoordinator`, `NavigationRosGateway`, or `MissionCoordinator.start`. Replay remains fixture-only and publishes zero for every side-effect counter.

`ready_for_manual_proceed` means the current advisory evidence is sufficient for a human-owned proceed decision. `autonomous_edge_ready` is only a declarative route-edge input for a future safety owner. Neither flag causes execution.

## Common snapshot

Every evaluation returns exactly these fields:

```json
{
  "behavior": "CROSSWALK",
  "state": "WAIT_SIGNAL",
  "advisory": "WAIT",
  "ready_for_manual_proceed": false,
  "autonomous_edge_ready": false,
  "reason_codes": ["TRAFFIC_RED"],
  "requirements": {"traffic_green": false},
  "updated_at_ns": 10000000000
}
```

Behavior is one of `CROSSWALK`, `DOCKING`, `UNDERPASS`, `DELIVERY`, `NORMAL_GUIDANCE`, or `FAULT`. Advisory is one of `WAIT`, `ALIGN`, `PROCEED_RECOMMENDED`, `HOLD`, `REPLAN_RECOMMENDED`, `SEARCH_MARKER`, `DOCKING_READY`, `PICKUP_CONFIRMATION_REQUIRED`, `DROPOFF_CONFIRMATION_REQUIRED`, `COMPLETE`, or `FAULT`. State/reason identifiers are bounded uppercase tokens and time is uint64-compatible.

Control-shaped fields such as `linear_x`, `linear_y`, `angular_z`, `cmd_vel`, `sport_request`, and `navigation_goal` are forbidden.

## Behavior rules

### Crosswalk

States are `IDLE`, `APPROACH`, `STOP_LINE`, `ALIGN`, `WAIT_SIGNAL`, `WAIT_PERSON`, `READY`, `CROSSING_OBSERVE`, `EXIT_CONFIRMED`, `HOLD`, and `FAULT`.

`READY` requires a fresh perception envelope, current pose and revisions, monotonic sequence, stable GREEN for at least two consecutive frames, CLEAR person evidence, a visible crosswalk, lateral offset at most 0.15 m, heading error at most 0.2 rad, and valid boundary distances. UNKNOWN or STALE never becomes ready. Route deviation over 1.5 m recommends replan. A supplied `feet_outside_count >= 3` is a boundary violation; a missing count remains `null`/unknown and Route Planner performs no foot kinematics.

After stale data, rollback, pose/revision invalidation, or alignment loss after ready, a strictly newer fresh sequence is required before readiness can return.

### Docking

States are `IDLE`, `COARSE_APPROACH`, `SEARCH_MARKER`, `TRACK_MARKER`, `ALIGN`, `READY`, `DOCKED_CANDIDATE`, `LOST`, and `FAULT`.

The advisor checks the expected venue and optional zone, marker presence, finite target pose, confidence of at least 0.8, freshness, monotonic sequence, and `docking_ready`. Successive target motion above 0.5 m or 0.5 rad fails closed. Venue/zone mismatch, rollback, stale pose, or revision change cannot produce readiness. Marker contact is only a candidate requiring an external operator/action-owner confirmation.

### Underpass

States are `IDLE`, `APPROACH`, `WAIT_CLEAR`, `READY`, `TRAVERSING_OBSERVE`, `EXIT`, `BLOCKED`, and `FAULT`.

Clear underpass, person, and service-robot evidence plus a current operator confirmation are required. Stale perception or pose/revision invalidation increments the confirmation epoch, invalidating prior confirmation. `autonomous_edge_ready` is always false because special gait/action ownership remains outside Route Planner.

### Delivery

The pure mock-event workflow uses `ORDER_READY`, `EN_ROUTE_PICKUP`, `PICKUP_DOCK_REQUIRED`, `PICKUP_CONFIRMATION_REQUIRED`, `CARGO_UPDATED`, `EN_ROUTE_DESTINATION`, `DROPOFF_DOCK_REQUIRED`, `DROPOFF_CONFIRMATION_REQUIRED`, `ORDER_COMPLETE`, `PAUSED`, and `FAILED`.

It preserves restaurant order, caps total and live cargo at five, rejects drop-off before all pickups, makes duplicate pickup confirmation idempotent, and keeps a bounded 32-entry operator audit. A restart pauses the workflow; only an explicit resume payload containing fresh evidence and operator confirmation restores the prior state. Dock/sit/stand completion is represented only by mock events.

## Composite selection and invalidation

The coordinator emits exactly one snapshot. Its priority is global `FAULT`, then current-segment `DOCKING`, `CROSSWALK`, `UNDERPASS`, pending delivery confirmation/failure, then `NORMAL_GUIDANCE`. Off-route guidance yields `REPLAN_RECOMMENDED`.

Server restart, invalid external input, changed map/graph/order revision, stale pose, or unavailable current segment fails closed before segment dispatch. Per-behavior stale/rollback/venue checks add stricter local invalidation. Recovery never silently reuses evidence that was invalidated.

## Deterministic replay

GP1 replay now adds `advisory_behavior` to each result while retaining its public projection and zero side-effect counters. `tests/fixtures/route_planner/advisory-golden-v1.json` pins the behavior/state/advisory projection for every GP1 scenario. The replay clock remains deterministic and no model inference is implemented here.
