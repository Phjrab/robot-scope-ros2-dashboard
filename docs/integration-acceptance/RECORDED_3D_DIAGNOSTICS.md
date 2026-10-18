# Recorded 3D registration diagnostics — local only

The existing `/static/experiments.html` now accepts a separate recorded diagnostic
JSON alongside its unchanged synthetic benchmark importer. It displays a saved
3D reference and registered query in one `RobotScene3D`, before/after alignment,
a reference Go2 model, available recorded trajectory, 6DoF session transform,
solver decision, convergence, residual/overlap and source identities. It does not
solve registration, contact a robot, upload the selected file, subscribe to live
telemetry or apply a pose. The only additional fetch is the existing local model
asset. No API or relocalization acceptance gate changed.

## Use

1. Serve the repository static files locally, e.g.
   `UI_REGRESSION_PORT=4187 UI_PROBE_PORT=4188 node tests/e2e/static_server.mjs`.
2. Open `http://127.0.0.1:4187/static/experiments.html` and choose a JSON under
   **저장된 3D 지도 · LiDAR 정합 → 저장 기록 JSON**.
3. Toggle **정합 전/후**, fit the map or center the candidate, and orbit/zoom the
   shared scene. These controls affect only the view. Clear removes the loaded
   recording. The source file is never changed.

The recorded importer and synthetic benchmark importer are independent. A
recorded file cannot be passed through the synthetic validator or silently
reclassified as synthetic. Production live verification is `NOT_RUN`.

## Contract

Schema: `robot-scope.recorded-se3-view.v1`, maximum 12 MB. See
`tests/recorded_se3_fixture.mjs` for a complete **synthetic** example.

| Field | Meaning |
|---|---|
| `data_kind` | `RECORDED_SENSOR` or explicitly `SYNTHETIC_FIXTURE` |
| `diagnostic_only`, `qualification` | true; `BLOCKED` or `UNQUALIFIED` |
| `operational_application`, `live_verification` | Both `NOT_RUN` |
| `absolute_accuracy_m` | null; residual never fills this field |
| `generated_at`, `captured_at`, `source_commit` | Report time, retained observation receipt time, analysis source identity |
| `target`, `source` | Distinct session IDs, exact frame names, original artifact SHA256, original count and XYZ points in metres |
| `source.stamp_ns`, `clock_domain` | Exact decimal string, never epoch nanoseconds in a JavaScript Number; explicitly state unverified clock relationships |
| `source.point_semantics` | `REGISTERED_QUERY`; already registered cloud, not raw sensor input |
| `result.T_target_source` | Query-session coordinates → reference-session coordinates, proper rigid 4×4 transform |
| `result.status` | `CANDIDATE`, `REJECTED`, or `UNCERTAIN`; never operational acceptance |
| `result.solver_metrics` | Fit-reference count, query count, gate, directional overlap and RMSE |
| `result.full_reference_metrics` | Optional separate postmetric against the same original full reference; cannot upgrade solver rejection |
| `body_relation` | null, or explicitly unverified `T_source_body` with source frame/session and provenance |
| `trajectory` | Up to 400 XYZ source-frame points, distinct estimand label and matching source session |

Limits: 100,000 reference points and 10,000 query points; finite coordinates
within ±1,000 m. Points are previews when fewer than `original_count`; preview
sampling cannot redefine numeric evaluation. The supplied artifact hashes are
provenance declarations, not browser cryptographic attestation. Session labels
must identify separate coordinate origins; identical `camera_init` strings do
not prove identical origins. A map conversion lineage token is not native
mapping-session evidence.

`T_target_source` is applied once to the registered query and source trajectory.
If supplied, body pose is composed as `T_target_source * T_source_body`; absence
of this relation leaves a **QUERY ORIGIN · BODY UNVERIFIED** reference glyph,
not an inferred body pose. The panel always names the session-origin transform.
With no result, the view disables “after”, labels the comparison unaligned and
hides the robot candidate. Rigid matrix validation rejects scale and reflection.

Captured data older than 30 days remain inspectable as `STALE_RECORDING`;
updating the report generation time does not refresh observation age. Recent
recordings still say `ARCHIVED_NOT_LIVE`. Missing, loading or invalid input clears
previous geometry/results immediately. Generation checks cover both asynchronous
success and failure, so old reads cannot resurrect or erase newer input.

## Model and scale

Reuses `static/assets/go2/go2-official-lite.json`, a metre-unit, Z-up mesh derived
from Unitree's Go2 URDF/DAE at source revision
`f3772ce54c56ef2d34c6aee8100bc768896c7d19`, with the existing BSD-3-Clause notice.
It retains 17 visual links and 12 motor joints. Unique source triangles were
reduced from 196,836 to 3,845 (7,033 assembled triangles). It is **not original
precision CAD or a measured as-mounted model**; XT16/RealSense attachments are
absent. Coordinate quantization does not bound physical or simplification error.

Official geometry, procedural fallback and generic placeholder no longer grow
with zoom-out. `adaptiveScale` remains accepted for caller compatibility but is
false; requested explicit model scale remains available. Dashboard saved-map and
navigation scenes select fixed scale, as the live scene already intended.
Screen labels/point markers retain readable pixel sizes. Fallback supports full
RPY and is labeled approximate in the recorded panel. Persistent asset failures
remain in fallback without a request loop; explicit model loading can retry.

## Verification and limits

- JavaScript unit coverage: strict recorded/synthetic separation, nanosecond
  precision, candidate gates, invalid frame/session/transform, no-result/stale
  states, before/after transforms, body composition, late read races, overlay
  invalidation, official/fallback world geometry across 100× zoom and full RPY.
- Browser fixtures: recorded controls, rejection/postmetric separation, stale
  replacement, missing result, unverified body label, model fallback, no API or
  WebSocket access. These fixtures are synthetic.
- Existing private sensor recordings were separately imported locally: original
  map and query points, exact timestamp, rejected decision and two residual
  supports displayed. No new sensor acquisition, live performance trial, field
  validation or deployment occurred in this work.
- Read-only live integration remains future work. It must preserve map revision,
  capture identity, point semantics, timestamp and source/body provenance; existing
  SE2 preview endpoints must not be relabeled as this 6DoF contract.

Local source changes require independent deployment approval before appearing on
the robot. Independent ground truth, historical map initial state/calibration,
clock relationship and sensor-to-body relation remain physical evidence gaps.
