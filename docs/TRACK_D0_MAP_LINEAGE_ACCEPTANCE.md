# Track D0 map-family lineage acceptance

Status: `MAP_LINEAGE_SOFTWARE_PASS`

```text
MAP_LINEAGE_SOFTWARE_PASS
REGISTRATION_NOT_IMPLEMENTED
LIVE_SENSOR_NOT_RUN
INITIAL_POSE_NOT_RUN
GOAL_NOT_RUN
MOTION_NOT_RUN
```

## Baseline audit

| Question | Before D0 | D0 result |
|---|---|---|
| PCD identity | 24-hex path-derived opaque ID; 64-hex bounded filesystem-signature revision | unchanged and pinned in lineage |
| PCD→2D source pin | present only in the immediate conversion response | persisted in the private family sidecar |
| Converter parameters | response-only; no complete persistent hash | all six values and canonical SHA-256 hash persisted |
| 2D geometry/frame | PGM/YAML preserved origin, resolution and dimensions; source frame not linked | both frames, geometry and explicit planar projection pinned |
| Rename/copy/edit | no persistent ancestry | occupancy rename/edit preserves family and creates a new family revision |
| Edited-copy family | absent | exact source PCD and family preserved when the source is linked |
| Delete behavior | logical map only, with annotation sidecar | same; the selected occupancy lineage sidecar is included, counterpart is untouched |
| Arbitrary HTTP binding | absent | remains absent; new API is GET-only |
| Navigation snapshot | map ID/revision and geometry only | also privately pins family/source/occupancy identities |
| Read-only family query | absent | two bounded path-free GET projections |

The education flow establishes the required data relationship: `/Laser_map`
is saved as PCD, a height slice is projected to PGM/YAML, and Nav2 loads that
2D map. D0 preserves the identity and parameters of that exact derivation
without changing the PDF-compatible YAML.

## Acceptance matrix

| Check | Result |
|---|---|
| PCD conversion publishes exact source/occupancy lineage | PASS |
| Parameter hash deterministic and semantic | PASS |
| Stale source revision remains rejected before publication | PASS |
| Edited copy preserves family and changes occupancy revision | PASS |
| Historical/similarly named maps remain unlinked | PASS |
| Occupancy rename migrates lineage transactionally | PASS |
| Delete is pair-scoped and does not delete source PCD | PASS |
| Symlink/corrupt/oversized sidecar fails closed | PASS |
| API is path-free and has no arbitrary bind mutation | PASS |
| Navigation snapshot exact-family placeholder | PASS |
| Existing conversion/editor/PGM origin and resolution behavior | PASS |
| Runtime map artifacts added to Git | NONE |

## Safety and execution evidence

All work was hardware-free. No Jetson connection, service restart, live ROS
subscriber/publisher, map runtime mutation, registration, initial pose,
navigation goal, lease, ARM, deadman, nonzero command or robot motion was used.
Track A/B/C, strict wireless odometry and its time guards, the C2 FAST-LIO
profile, C3 localization ownership and control safety boundaries are unchanged.

## D1 handoff

D1 may use only a lineage-aware occupancy map and must pin its exact
`family_revision`. Historical `unlinked` maps require a new explicit PCD→2D
conversion; they cannot be repaired by filename inference. Registration and
live sensor validation remain unimplemented and require their own phase gates.

