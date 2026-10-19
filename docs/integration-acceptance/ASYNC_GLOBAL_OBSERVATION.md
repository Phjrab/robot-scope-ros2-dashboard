# Historical raw global observation — local software, 2026-10-19

This change is **not deployed**. The robot remains on approved dashboard commit
`d7807de8f15fb457942039bb90ab41cf68d384c6`. No backend installation, new sensor
session, registration against real input, TF, initialpose, goal or movement was
performed for this change. The user subsequently authorized GitHub publication
of source and the [public desktop handoff](DESKTOP_HANDOFF.md), while deployment
and private evidence transfer remain held.

## Path and input contract

Maps has a separate historical observation panel. Start/get/cancel use
`/api/v1/observations/global-jobs`, `/{job_id}`, and `/{job_id}/cancel`.
Start accepts only `request_id`, catalogue `map_id` and `map_revision`; no client
path, command, interpreter, frame, pose, array or executable is accepted.
Same request IDs are idempotent within bounded process-local history; a changed
request with the same ID conflicts. After an uncertain response the UI queries
the owner and retains the same request ID.

An explicit one-shot latch captures the next existing PointCloud2 callback
**before** display throttling, sampling or filtering. It preserves all numeric
XYZ rows/order/zeros/nonfinite rows as immutable little-endian float64 bytes,
plus exact decimal source nanoseconds, original frame, observation epoch,
receipt time, counts and hashes. This is the entire received XYZ population,
not an archive of all original ROS fields or upstream sensor packets. Raw and
converted sources are allowed; registered/map-stage sources are rejected.
For `/velodyne_points`, upstream bridge reduction/restamping remains unverified
provenance, not native sensor-clock or original 64,000-point proof.

The map reader pins catalogue revision and original binary PCD hash, extracts
the full numeric XYZ population without viewport normalization, and hashes the
float64 array separately. `camera_init` and metres are explicitly unverified
product conventions because PCD does not encode ROS frame/unit semantics.
The backend currently requires finite input: any nonfinite row fails explicitly;
it is never silently filtered. Zero XYZ rows remain. Default input limits are
one million points and 32 MiB per array/source; acquisition timeout is 5 seconds.

## Ownership and result semantics

The existing 600 ms live fit, 1 Hz limit, 1-second freshness, 150 ms receipt pair
and live display gates are unchanged. A separate job owner retains the execution
slot until the actual worker exits, even after cancel/timeout. Map revision,
source topic/frame, observer epoch and source time regression invalidate a job.
Completion checks a fresh receipt in the same observer clock. Advancing source
time does not make the captured historical result current. Lost/late results
cannot repopulate a current pose.

Every result has `historical_only=true`, `current_result=null`, `body_pose=null`,
`tracking_verified=false`, and `operational_application=NOT_RUN`. The native
matrix is **T_map_sensor**, not T_map_odom or T_map_base. No verified sensor-to-body
extrinsic or same-epoch propagation/new-scan validation is implemented. The UI
does not receive the live scene or apply a result to its current robot marker.

The frozen backend keeps its original 5 cm ranking, ambiguity and all gates.
An additive `residual_comparisons` field compares stored RMSE with exact
`<= 0.10 m` and original `<= 0.05 m`. It does not reselect a global candidate,
relax stationarity/overlap/inliers/geometry, or establish physical accuracy.
In particular, a saved `selected_candidate=null` stays null even if its residual
alone passes 10 cm. Failed candidates and complete diagnostics remain visible.

## Backend preparation and limits

Default provider status is unavailable. A future separately reviewed deployment
must configure all three server-side variables:

- `ROBOT_SCOPE_GLOBAL_OBSERVATION_PYTHON`: absolute existing Python interpreter
  with the required NumPy/Open3D dependencies.
- `ROBOT_SCOPE_GLOBAL_OBSERVATION_SOURCE`: absolute canonical directory containing
  the reviewed immutable `auto_localization` package.
- `ROBOT_SCOPE_GLOBAL_OBSERVATION_PIN`: absolute JSON pin manifest:
  `{"schema":"robot-scope.global-source-pin.v1","files":{"auto_localization/__init__.py":"<sha256>","auto_localization/isolated.py":"<sha256>","...":"..."}}`.

The manifest must cover every package `.py` file exactly. Configuration status
checks source hashes; it does not import/probe Open3D. The fixed product worker
copies only verified source (excluding existing bytecode), loads the fixed
`run_se3_isolated` callable under the configured interpreter, and accepts one
result with matching input hashes/counts/frames/stamp. The parent owns a separate
process group, drains bounded logs, requires normal exit, and terminates/kills on
cancel, timeout or invalid/oversized output. Deadline is 120 seconds including
input preparation/import/spawn/execution, with up to two 200 ms cleanup waits.
Acquisition/reference preparation is a preceding phase. Result limit is 64 KiB,
including the additive residual diagnostics; nothing is truncated to fit.
There is no OS memory hard limit or security sandbox. No install or DDS change
is performed by configuration or start.

## Validation and next work

Focused tests cover lifecycle races, idempotency, cancel/late completion,
map/frame/epoch/time fences, exact XYZ/PCD preservation, wrong hashes/frames,
nonfinite input, missing backend, startup hang/deadline and output limits.
Browser cases use synthetic records, not hardware. Final full-suite results and
the exact local commit are recorded in the accompanying desktop handoff.

Next: on the new workstation, confirm sole ownership and read current robot
source/service state; recover the local source and private backend artifacts by
an explicitly authorized transfer. Review the configuration, dependency runtime
and a bounded observation plan before proposing a new deployment. No automatic
continuation or device action is scheduled.
