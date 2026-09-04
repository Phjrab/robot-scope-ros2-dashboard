# ADR — Competition Route Planner

Status: implemented on `feature/competition-route-planner` (software only)

## Decision

Robot Scope owns one server-authoritative `RoutePlan`. The same selected plan is projected as advisory manual guidance and exported as a revision-pinned Mission draft. Route Planner never starts a Mission, sends a Nav2 goal, acquires a lease, arms control, or emits velocity/action commands.

## Existing implementation audit

| Capability | Existing implementation | Reuse | New implementation |
|---|---|---|---|
| Map annotation | `SavedMapCatalog` + `map_annotations.py` | Node location and goal identity source | Graph nodes reference `annotation_id`; coordinates are not duplicated |
| Point goal resolve | `SavedMapCatalog.resolve_annotation_goal` | Mission validates the same IDs again | None |
| Mission state/API | `MissionCoordinator`, `/api/v1/missions` | Create ready draft only | Persist route↔mission revision link |
| Navigation preview/status | `NavigationCoordinator.view()` | Current map, pose and actual-path read only | Exact graph preview; live plan-only Nav2 remains blocked |
| SceneHost overlay | `createCockpitSceneHost`, `RobotScene3D.setSpatialOverlay` | One existing renderer | Selected/alternative/current-segment/stop overlay layers |
| Panel lifecycle | registry, manager, layout store | Floating/focus/resize/cleanup | `route-planner.main` singleton panel |
| Competition Lock | `CompetitionStateManager` and API dependency | All mutations use the existing lock gate | None |
| Order model | None | — | Strict fixed-catalog `OrderSheet` |
| Route graph | None | Annotation and exact 2D map geometry | Bounded revision-pinned semantic graph |
| Recommendation | None | — | Exact permutation + deterministic Dijkstra |
| Manual guidance | Localization pose in `NavigationCoordinator.view()` | Existing pose authority | Polyline projection and advisory state only |

## Boundaries

Control safety remains owned by `ControlManager` and the signed Control Bridge. Navigation safety remains owned by `NavigationCoordinator` and its ROS gateway. Mission execution remains owned by `MissionCoordinator`. `RoutePlannerCoordinator` owns only orders, graph revisions, recommendations, selection, advisory guidance state, and Mission draft links.

Manual guidance differs from automatic execution: it computes instruction, remaining distance, ETA, cross-track error, and requirement warnings, but `control_authority` is always false. Mission export calls only `MissionCoordinator.create`; it never calls `start` or any Navigation goal method.

The 3D overlay is explanatory. Feasibility is validated from the exact 2D occupancy map and annotation revisions. Point-cloud height never becomes a traversability decision.

## Order contract

- Exactly one registered destination.
- Two to five lines, two or more distinct restaurants, and three to five items.
- The destination-zone restaurant is forbidden.
- Menus must belong to their restaurant.
- Sequences are unique and continuous from 1.
- Difficulty is derived: LOW `(2,3)`, MEDIUM `(2,4)`, HIGH `(3,5)`.
- Production readiness follows `ORDER_SEQUENCE_20S`: cumulative ordered items × 20 seconds.
- Capacity is five. HTTP callers cannot supply `difficulty`, totals, coordinates, paths, topics, or plugins.

## Route Graph

Nodes carry semantic role, zone/venue identity and an annotation reference. Edges carry a bounded 2D polyline, distance, speed, risk, expected wait, manual/autonomous eligibility, and typed requirements. `UNDERPASS` is the only internal underpass/overpass semantic.

Limits are 128 nodes, 512 edges, 128 points per edge, 4096 total points, and 1 MiB serialized graph/state. Every node annotation and polyline point is validated against the exact map and annotation revision. Revisions are SHA-256 over canonical content.

Production graph coordinates are intentionally not guessed. Operators must create validated map annotations and import a graph pinned to those revisions.

## Recommendations and weights

All pickup permutations (at most six) are evaluated. Each leg uses deterministic Dijkstra with stable edge/node ordering. Tie-breaks are score, distance, risk, then node sequence.

| Profile | Time | Risk | Crosswalk | UNDERPASS | Turn |
|---|---:|---:|---:|---:|---:|
| BALANCED | 1.0 | 4.0 | 2.0 | 4.0 | 0.5 |
| FASTEST | 1.0 | 0.5 | 0.5 | 0.5 | 0.1 |
| SAFEST | 0.35 | 12.0 | 8.0 | 12.0 | 1.0 |

Travel, food wait, expected signal wait, distance, risk, crossings, turns and special behaviors remain visible separately. Equal node paths are deduplicated and retain multiple profile badges.

## Revision invalidation

Selection becomes `STALE` when order, graph, map, annotation, planner configuration, start node, or operation mode differs from the recommendation context. Current annotation pins are checked on every snapshot, preview, guidance start, and export. Stale selection is not executed or exported.

## Perception

Traffic, crosswalk/lane, person and ArUco inputs use a typed envelope with monotonic sequence, timestamp, confidence, fixed source/frame, bounded lists and a one-second freshness gate. The mock provider is the only provider in this software track. UNKNOWN/STALE creates a manual warning and keeps autonomous special edges not ready. Model training, inference, visual servo and motion behavior are separate work.

## Persistence and restart

The state root is service-owned mode `0700`; its atomically replaced JSON file is mode `0600`, fsynced, symlink-rejected and bounded to 1 MiB. A selected route may survive restart. Guidance never auto-resumes and no execution authority is restored.

## Concurrent subsystem policy

- Navigation or Mission active: order/graph/route mutation and export fail closed.
- Mapping active: graph update and recommendation fail closed.
- Localization/read-only state: snapshot and graph overlay remain allowed.
- Manual control: advisory guidance is allowed and remains separate from control.
- Panel close: releases polling subscription only; it does not stop control or Mission. Guidance stops only via its explicit endpoint or server restart.

## No-motion acceptance and rollback

Acceptance uses pure Python, mock providers, JavaScript unit tests and browser fixtures. It asserts zero Mission starts, Navigation goals, leases, ARM/deadman, `/cmd_vel`, Sport actions and robot/service operations.

Rollback is code-only: stop using the feature branch or revert its focused commit. Persistent route-planner state can be archived separately while leaving map annotations, Mission state, Nav2 settings and C4 evidence untouched.

## Integration rule

Before integration, fetch `origin/main`, audit every main commit since the branch base, merge/rebase without discarding either track, and rerun all Python/JavaScript/E2E checks. Do not merge into `main` until the user explicitly directs it.
