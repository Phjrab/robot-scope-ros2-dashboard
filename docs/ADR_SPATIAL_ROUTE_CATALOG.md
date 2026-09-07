# ADR: revisioned spatial route catalog

Status: accepted for Track E0

## Context

The existing Route Planner recommendations and Mission queue are execution-side
objects.  Track E needs a separate authoring object that may contain thousands
of map-frame samples without implying a Mission, navigation goal, lease, or
robot command.  Every route must remain attached to the exact D0 3D/2D map
family from which it was authored.

## Decision

Robot Scope stores `robot-scope.spatial-route.v1` documents in a private
service-owned root.  A route contains a 24-hex opaque ID, a content-derived
64-hex revision, all six D0 family/member pins, authoring provenance, policy,
and one to 4,096 finite map-frame poses.  Optional `z` is visual-only.  It is
not projected into a Navigation or Mission pose.

Each semantic revision is an immutable mode-0600 JSON record.  A separate
mode-0600 current pointer is atomically replaced after the immutable file is
fsynced.  Updates, copies, and deletes require the current revision as a CAS
pin.  Deletion removes only the active pointer and retains immutable revisions
privately for audit/recovery.  HTTP callers provide no path, root, topic,
command, script, or hook.

The API surface is:

```text
GET    /api/v1/routes
POST   /api/v1/routes
GET    /api/v1/routes/{route_id}
PATCH  /api/v1/routes/{route_id}
DELETE /api/v1/routes/{route_id}?base_revision=...
POST   /api/v1/routes/{route_id}/copy
```

Every mutation uses the shared same-origin guard and Competition Lock.  This
phase deliberately has no Mission export, start, goal, or motion endpoint.

## Validation contract

Creation, update, and copy resolve the exact current occupancy map and D0
family.  A mismatch fails closed before publication.  The validator samples
every segment at spacing no larger than the map resolution or half the fixed
0.25 m robot-radius footprint.  Work is capped at 100,000 samples and route
length at 1,000 m.

The validator rejects map boundaries, unknown cells, occupied cells, circular
footprint clearance failures, and KEEP_OUT polygons.  SLOW_ZONE and WAIT_ZONE
are retained as advisory tags.  `minimum_clearance_m` is intentionally a
conservative proven lower bound, not an unverified distance-field claim.  The
validation snapshot pins the annotation revision used for zone evaluation.

FLEXIBLE routes may be marked eligible for a later Mission export only after
both the raw path and its deterministic, at-most-32-waypoint projection pass
the same validator.  CORRIDOR and STRICT remain authoring/preview-only.  Even
an eligible result reports `mission_created=false` and `route_executed=false`.

## Simplification utilities

Pure hardware-free helpers provide duplicate removal, yaw wrap/unwrap,
deterministic RDP, bounded highest-error corner selection, maximum segment
length insertion, final-orientation preservation, and route length.  The
bounded selector is iterative so the 4,096-pose schema limit cannot exhaust
Python recursion depth.

## Consequences

- Existing annotation-based Mission behavior is unchanged.
- Existing Route Planner recommendation IDs are a separate namespace and API.
- Existing Track A/B/C, strict wireless odometry guards, D2 registration, and
  control/navigation safety boundaries are unchanged.
- E1 can add the Cockpit point-click editor against this catalog.
- E2/E3 must revalidate the exact current route/map/annotation revisions before
  export; the stored E0 validation snapshot alone is not execution authority.
