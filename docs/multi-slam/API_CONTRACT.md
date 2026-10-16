# Additive API

Existing mapping/saved-map APIs retain their meanings. New routes use
`/api/v1/slam`. Mutations keep same-origin, manual-mode and competition gates;
owned stop remains available for cleanup. Strict request models reject extra
command/path/topic/image/domain fields. Errors expose reason codes, not stderr.

| Route | Contract |
|---|---|
| GET engines / session / navigation-context | Read-only capabilities, authority and ownership |
| POST sessions | engine_id lidar_fastlio/visual_stereo, task tracking/mapping, request_id, explicit operator_confirmed |
| POST sessions/{id}/stop | generation, request_id, explicit discard_unsaved when required |
| POST sessions/{id}/save | generation, request_id, name, optional create_2d for LiDAR |
| POST sessions/{id}/localize | generation, request_id, package_id, revision, verified hint, explicit discard_unsaved for replacing an unsaved live map |
| GET jobs/{id} | Native publication success/failure, separate from202 acceptance |
| GET packages / packages/{id} / preview | Immutable native metadata and renderer-only preview |
| POST packages/{id}/rename / copy | name, expected_revision |
| DELETE packages/{id} | expected_revision query |
| GET packages/{id}/export | expected_revision; bounded streamed ZIP |
| GET packages/{id}/preview-export | expected_revision; read-only saved-preview XYZ/CSV/provenance ZIP, <=32MiB and store quota |
| POST packages/import | raw ZIP body, bounded128MiB transport and store quotas |
| WS /api/v1/ws/slam | Same-origin latest snapshot, <=8MiB, send timeout; no per-viewer ROS subscriber |

Hint has exactly frame_id, position[3], normalized quaternion_xyzw[4],
operator_verified=true. No default origin/identity is supplied by UI or server.
Saved localization uses actual SLAM mode and scratch native copy. Native load,
localization attempt and actual official localization completion are distinct.
It never publishes an operational initial pose or Nav2 goal.

Preview export verifies the requested package revision and saved preview hash;
it does not call an adapter, start a runtime or parse native DB bytes. Its ZIP
contains `provenance.json`, plus available `global-map.xyz`, `trajectory.csv`
and `camera-pose.csv`. Each point layer is limited to60,000 finite bounded XYZ
rows; inconsistent frames/epochs, invalid poses or exceeded quotas reject the
whole export. Files have private0600 archive modes. `trajectory.csv` indices are
row order, not native IDs; `camera-pose.csv` is one saved camera pose. Neither is
a whole-run sensor trajectory or Go2 ground truth.

Provenance pins the package/native-content/preview revisions, original source
IDs/stamps, coordinate frame, calibration/sensor hashes, file hashes and row
counts. Saved `preview_consistency` and unknown capture time are preserved;
download time is not substituted. Source coverage declarations are recorded
separately: this exporter attests no full native coverage, exports no native IDs
and leaves engine total unknown. Existing native ZIP/import semantics remain
unchanged. Missing previews use PREVIEW_UNAVAILABLE; unsupported/invalid saved
snapshot geometry uses INVALID_PREVIEW_EXPORT, absent exportable layers use
PREVIEW_EXPORT_UNAVAILABLE and exceeded bounds use PACKAGE_LIMIT (422). Stale
expected revisions remain REVISION_CONFLICT (409).

Unix broker is private to the same uid, enforces operation-specific schemas and
session/epoch identity, restricts native paths to shared private staging/scratch
tokens, and has bounded requests/responses/timeouts. The broker holds physical
camera reservation until exact child cleanup. An existing socket is not removed
automatically; crashed/orphaned state requires owner investigation.
