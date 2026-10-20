# Historical global observation and temporal sensor candidates — 2026-10-19

> 2026-10-20: 사용자 승인 후의 실제 배포·ARM 시험·정지 관측 결과와 한계는 [최신 실행 기록](STAGE3_ARM_RUNTIME_20261020.md)을 참조한다. 아래의 배포 전 상태와 제한은 해당 시점의 기록이다.

The original global-observation implementation was **not deployed** when this
document was first written. The handoff reported dashboard commit
`d7807de8f15fb457942039bb90ab41cf68d384c6` on the robot; that is historical evidence,
not a fresh verification of its current checkout. No backend installation, new sensor
session, registration against real input, TF, initialpose, goal or movement was
performed for this change. The user subsequently authorized GitHub publication
of source and the [public desktop handoff](DESKTOP_HANDOFF.md), while deployment
and private evidence transfer remained held at that point. These are historical
milestones, not deployment authorization or the current robot state. Stage 3
software contracts are described below; deployment and runtime results belong
in the separately dated verification report.

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

## Independent stationary diagnostic recorder (local preparation only)

`scripts/capture_stationary_lidar.py` is a separate, opt-in diagnostic. Its
default path validates a JSON plan without importing ROS, creating a node or
writing a capture. It reuses the existing full-XYZ decoder and observation
identity helpers; it does not change dashboard subscriptions or localization.
Only synthetic ROS-shaped tests have been run for this recorder.

The plan requires `cloud_topic`, `odom_topic`, and one to sixteen explicit
`tf_edges` with `parent`, `child`, and boolean `static`. Optional fields are
`duration_s` (default 5, maximum 15), `cloud_count` (1–3, default 3),
`max_cloud_bytes` (at most 33,554,432), `max_total_bytes` (at most 268,435,456),
and `max_events` (at most 5,000). The input JSON is limited to 16 KiB. Extra keys,
duplicate JSON keys, nonfinite numbers, conflicting topic roles, and invalid
layouts are rejected. Derived policy fields in the output manifest are not
accepted as input plan keys.

Before any future live use, establish the actual ROS distribution, compatible
Python/NumPy and message packages, existing producer ownership, DDS/domain/NIC
configuration, topic types/QoS, and actual TF edges. Do not guess or overwrite
sensor-to-body extrinsics or equate FAST-LIO pose with controller odometry.
The recorder subscribes to one explicitly chosen odometry stream; the manifest
does not prove that its frames form the required geometric chain to the scan.
Existing launch scripts for different hosts are not interchangeable environment
profiles. This procedure does not start sensors or repair a missing ROS graph.

From an isolated checkout or the supplied minimal runtime bundle, first run:

```sh
python3 scripts/capture_stationary_lidar.py --plan /absolute/confirmed-plan.json
```

The expected output is `PLAN_VALIDATED_ONLY`. After separate authorization and
operator preparation, the following is the single bounded capture command:

```sh
timeout --signal=INT --kill-after=2s 20s python3 scripts/capture_stationary_lidar.py \
  --plan /absolute/confirmed-plan.json --execute --stationary-confirmed \
  --output /absolute/existing-private-parent/new-capture-directory
```

The output directory must be new and absolute; existing directories and symlink
parents are rejected. The command must use a confirmed ROS-compatible Python.
There is a graph discovery preflight of at most three seconds, followed by the
declared capture interval. A fixed 0.5-second odometry/TF pre-roll is inside
that interval. The outside timeout bounds an unresponsive native middleware
call or teardown; a forced kill can leave partial artifacts and no manifest.
Neither Python checks nor the timeout provide an OS memory hard limit.

For each retained cloud, output includes exact `PointCloud2.data` bytes, all
declared fields/layout/header/frame, and a separate full numeric XYZ file in
source order, including zeros and nonfinite values. SHA256 hashes distinguish
raw bytes from converted XYZ. This is not CDR, rosbag, or original sensor-packet
archival. At most the requested first clouds are retained; later callbacks are
counted and checked for continuity, not advertised as stored scans.
Odometry pose/twist/covariance and declared TF edges retain original stamps.
Callback receipt monotonic time and available RMW timestamps remain separate.
No original source time is replaced by the current time.

Dynamic odometry/TF must bracket each retained cloud within 150 ms of callback
receipt. This is receipt association, not sensor-clock synchronization or
interpolation. Static transforms may retain stamp zero and repeat unchanged;
they do not supply fresh dynamic pose evidence. Each stream has its own local
subscription/observer continuity fence. A local epoch is not a native sensor
session. Missing or ambiguous authority is retained as incomplete evidence;
unknown clocks, extrinsics, native sessions, physical stationarity, and tracking
remain unverified even for a complete record.

`manifest.json` reports `READY_FOR_OFFLINE_INSPECTION`, `PARTIAL`, `TIMED_OUT`,
or `CANCELLED`. `runtime-summary.json` reports middleware cleanup separately.
Only data ready plus cleanup `COMPLETE` yields exit code 0. Missing graph before
arming is `NOT_RUN` and creates no capture. A ready record is not a current
robot pose, successful map registration, accuracy proof, or navigation approval.
Check both JSON records and file hashes before offline use.

The application creates only the declared subscriptions, disables rosout and
parameter services, and creates no command publisher, client, action, or
control service. Native rclpy may still create its own node infrastructure
(for example parameter-event publication); zero DDS writes are not promised.
No deployment, service change, robot connection or live subscription was part
of the local preparation and regression tests.

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
extrinsic or same-epoch odometry propagation is implemented. The global result
never updates the current robot marker. The separate sensor-observation owner
below can use an admissible result to seed new-scan checks.

The received v0.3.1 backend is preserved byte for byte. For the exact reviewed
seven-file source hash set, a dashboard-owned adapter calls the original scorer
and removes only its numerical residual gate before original branch
ranking/retention and ambiguity checks. This supersedes the earlier 10 cm
selection policy following the user's subsequent policy change. Both 5 cm and
10 cm remain comparison values; neither selects a candidate. Two distinct
otherwise admissible alternatives remain ambiguous.
Stationarity/overlap/inliers/geometry and transform gates are unchanged.
Scoring still uses every supplied scan point and the full original reference,
with the original 0.75 m association mask; full-scan/capped metrics also survive.
No fitting subset becomes the evaluation population.

`selection_policy` uses `robot-scope.global-provisional-selection.v2`, with
`rmse_selection_gate_enabled=false` and comparison-only thresholds. Candidate/stage
`original_residual_gate` preserves the original 5 cm residual decision; this
does **not** replay or claim the old stochastic pipeline's overall selection.
Unknown pinned source versions run their original policy without this label.
The original deduplication/search is not an exhaustive uniqueness proof.

### Explicit temporary ambiguity observation option

The subsequent user request permits ambiguous candidates for stationary
observation/development. Set `ROBOT_SCOPE_OBSERVATION_ALLOW_AMBIGUOUS=1` explicitly
in the server process; the default is disabled. This is not a client pose input
or a navigation setting. The provider reports `allow_ambiguous`.

After the original finish, the adapter may choose a candidate only when the
original top-level rejection is exactly `AMBIGUOUS_ALTERNATIVES`. Eligible
candidates must have that sole reason and satisfy the unchanged finite rigid
transform, stationarity, support, overlap and geometry checks. The explicit
rule is the lowest original `rmse_m`, then the original candidate array index
for a tie. This may differ from the backend's capped-full-RMSE ordering and is
not asserted to be the correct physical location.

Original top/candidate gates, all alternatives, metrics, stages and transforms
are retained. `ambiguity_override` records the original null selection, original
gate, enabled/applied flags and `LOWEST_RMSE_M_THEN_ORIGINAL_INDEX` rule. An applied
override has `estimate_label=AMBIGUOUS_UNVERIFIED_ESTIMATE`; it does not change
the observation-only status or any body/clock/tracking verification flag. A
sensor session keeps the ambiguous label if its global seed or a later local
observation needed the override. The API retains the complete most recent
accepted local result in `last_alignment` as historical diagnostics, including
after loss/stop. That record is never a fresh pose by itself.

The independent `residual_comparisons` sidecar only compares stored RMSE; it
does not perform further selection. Its policy metadata is stored once, with
candidate-index-aligned comparison rows, to avoid repeated metadata exceeding
64 KiB. Failed candidates and complete backend diagnostics remain visible.
A numerical comparison never verifies physical accuracy, current body pose,
temporal tracking or navigation readiness.

## Separate temporal sensor observations (Stage 3)

`GET/POST /api/v1/observations/sensor-tracking` and
`POST /api/v1/observations/sensor-tracking/stop` expose a process-local owner.
Start accepts only a successful server-owned `global_job_id` and an idempotency
`request_id`; client poses and transforms are forbidden. The historical result,
full input counts and hashes, reviewed source pin, independent candidate gates,
map revision, source identity and receipt freshness must match.

A persistent isolated worker loads the map once. Each local alignment has its
own unchanged 600 ms end-to-end limit and 65,536-byte response limit. Captures
must be newer complete XYZ populations from the same observer epoch, with
receipt age at most one second. Three successive admitted new scans are needed
before `SENSOR_CANDIDATE`. The original local refinement/scoring methods are
reused; unused FPFH computation is omitted for local point-to-point refinement.
The fitting population and full original evaluation population are unchanged.
Local branches do not establish global uniqueness after the initial search.

The API preserves exact original source stamps and separately reports observer
receipt age. It does not restamp old input or propagate it using unverified
odometry. Its `T_map_sensor` represents the accepted scan's sensor observation.
`body_pose=null`, `tracking_verified=false`, `source_clock_verified=false`,
`body_extrinsic_verified=false`, `globally_verified=false`, and
`operational_application=NOT_RUN` remain fixed. Temporal consistency is a
separate flag, not an absolute position or body-pose claim.

The 3D view draws a separate sensor marker, XYZ axes and at most 40 trail entries.
It never passes that transform to the GO2 body renderer. Map/source/global-job
replacement, stale or reversed input, rejected/ambiguous alignment, cancellation,
timeout and late responses invalidate the observation and clear its trail.
Ambiguous results invalidate it unless the explicit observation option above
is enabled and the complete override contract is valid; other rejections still
invalidate it.
Explicit operator global search is required after loss; no automatic global
retry, control command, navigation goal or operational TF update is introduced.
Workers and temporary scan files are cleaned on success, error, stop and shutdown.

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
isolated runner under the configured interpreter, and accepts one
result with matching input hashes/counts/frames/stamp. The parent owns a separate
process group, drains bounded logs, requires normal exit, and terminates/kills on
cancel, timeout or invalid/oversized output. Deadline is 120 seconds including
input preparation/import/spawn/execution, with up to two 200 ms cleanup waits.
Acquisition/reference preparation is a preceding phase. Result limit is 64 KiB,
including the additive residual diagnostics; nothing is truncated to fit.
There is no OS memory hard limit or security sandbox. No install or DDS change
is performed by configuration or start.

For the reviewed v0.3.1 source only, the adapter installs an in-memory subclass
inside the disposable spawned worker and reuses the original isolated worker
and deadline/cancellation controller. It never edits the source package. The
65,536-byte limit applies to both the worker result and the enriched observation;
oversized diagnostics still fail explicitly, without truncation or a larger cap.

## Linux local follow-up (not published or deployed)

The source archive received on this desktop has SHA256
`0e4abbc70de139fdef45e90b6958d0f1f7c997a52b7ffb24bee718355bd12593`
and size 69,619 bytes. Its per-file manifest was generated on receipt; it is not
an upstream manifest. The earlier 7.04 cm real-data report belongs to v0.3, not
evidence of v0.3.1 residual improvement. No real saved point-cloud inputs were
included. Linux synthetic regression cannot substitute for that replay.

The source-change/reanchor race also requires a fresh accepted counterpart
receipt after a stream identity changes. Per-topic subscription session IDs
remain independent. Duplicate or older messages cannot reopen the reanchor gate;
existing source, sequence, timestamp, freshness and operator-anchor checks remain.
This follow-up authorizes local edits/tests only, with no commit, push, deployment
or robot action. The earlier deployment statement above is handoff history;
current backend checkout identity still requires a trusted read-only verification.

## Full-source PCD editor integration (local only)

The integration combines editor module commit
`af30ce70c0b2ffc9ca0e8283ddb02c12ed03908f`, its common Maps wiring and the local
localization changes based on `3de44c7df57730b7ebb6f0bc1e6159e182f44c73`.
The original main working tree and editor worktree are preserved separately.

Saving an edit creates an immutable, separately identified PCD/manifest pair.
The preview buffer is never the save input. After explicit map selection, the
observation reader binds the edited semantic revision and PCD hash to the full
XYZ array, frame and metre declaration. Non-XYZ multi-count fields are retained
in the PCD and safely skipped when extracting XYZ. Nonfinite/zero XYZ rows remain
present; the external backend still rejects nonfinite inputs rather than dropping
them. Legacy file-signature revisions continue to use their existing check.

An edited reference carries only bounded parent/root IDs, revisions and hashes
in `reference_provenance`, with `parent_score_comparable=false`. A residual
against the edited reference must not be presented as an improvement against
the unchanged parent map. Both references keep their own results. Frame/unit
metadata remains a declaration, not physical calibration evidence.

The Maps save action refreshes the catalogue display and does not install the
new map, start a global observation or switch the robot's localization runtime.
The historical-only job flags, session/epoch fences and original live timing
limits remain unchanged. The deployment and real-data/field validation gates
in this document still apply.

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
