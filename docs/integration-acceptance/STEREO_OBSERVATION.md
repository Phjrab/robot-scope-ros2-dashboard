# Stereo VSLAM observation — 2026-10-16

The current user priority is dashboard-controlled Stereo mapping observation:
SLAM button → API → broker → preserved Isaac environment → real stereo/VSLAM →
WebSocket → image, camera 6DoF, tracking, current points, available global map and
trajectory. This request supersedes the prior closed stage40 scope. It does not
reopen motion or operating localization.

Nav2 policy readback, MR-MS-003, missions, complete native map reuse, MAP-02 full
retained export and independent accuracy evaluation are deferred. Their open
rows are not admission gates for this observation/new-map task. VIO IMU absence
is not a Stereo gate. Camera-to-Go2 extrinsics remain unverified.

## First actual observation completed

The user approved the grouped deployment/current stationary conditions and ran
the reviewed administrator installer. Source `ffa1b21` was deployed for this run; exact CI
[38841524522](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38841524522)
passed both Linux matrices. The actual dashboard button → API → same-UID broker
→ preserved Isaac image → stereo/VSLAM → WebSocket → screen path ran, then the
dashboard stop cleaned the native processes and returned the camera.

The first session produced 180 READY/TRACKING frames over a sampled57.56s span.
All180 stereo pairs matched with0ns skew; image/camera6DoF/current observations
(86–314 points) and SLAM trajectory were fresh. Overlay aligned65/180 frames;
115 were correctly withheld by the unchanged20ms guard because the latest
image preceded completed pose/observations by1–4 frames. No freshness/timeout
threshold was widened. The maximum reported global snapshot was238 points,
coverage unknown; its coordinates were not retained in the first collector.
This is not a full retained export or independent accuracy result.

Cleanup readback: IDLE, cleanup_required=false, device owner free, zero native
children, camera/domain locks released, RGB available. No lock was deleted.
Control bridge invocation stayed unchanged; movement/initialpose counts are0
and goal idle. Exact source/runtime/config hashes, timestamps, metrics and
limitations are in [STEREO_OBSERVATION.json](STEREO_OBSERVATION.json).

## Second observation: matched pixels confirmed, native save failed

Source `6590c97` ran the second stationary dashboard session. Actual UI image,
camera 6DoF, overlay, global landmarks and trajectory were observed. The collector
received549 WebSocket messages, including90 active frames, plus one separately
recorded connection-close error. READY/TRACKING held for81/90 active frames
(90%) over a sampled24.265264297s READY span. The full active-frame span was
26.768485389s. Session creation to first observed IDLE was35.683131s; polling
places actual cleanup completion after34.615950s and at or before35.683131s.
These sample spans do not establish an exact continuous runtime duration.

All81 READY frames had an aligned overlay (100%). Across all90 active frames,
84 aligned (93.33%), two were withheld for NO_VALID_TIME_ALIGNMENT and four for
STALE_SOURCE. The last nine frames, around save/cleanup, were not READY and
reported the source-publisher-uniqueness guard. All84 aligned payloads used the
exact selected image stamp in the transmitted image, overlay reference and
alignment quartet. Quartet skew was8–992ns; camera-view skew was0ns. In35 of
81 READY frames the selected pixels preceded the latest image, confirming that
the completed quartet selects matching actual pixels. The1s freshness,5ms
stereo and20ms overlay guards were unchanged.

The retained observation snapshot contains501 actual finite bounded XYZ points;
source/export/display counts, frame and map epoch agree, with no decimation or
rejected points. Coverage remains unknown and engine total/completeness evidence
remain absent. The SLAM trajectory reached666 source points. This confirms
visualization data, not a complete retained native map or accuracy qualification.

Clicking native map save produced a FAILED job with INVALID_NATIVE_PATH and no
package. Fail-safe cleanup reached IDLE with cleanup_required=false, camera free,
RGB available, zero native children and both locks released. The unsaved flag
remained true. UI stop was not performed in this second run; the first run's
successful UI stop remains separate evidence. The minimum package-token
permission correction is now implemented: create its directory with mode0700
before native save. Actual save/requery revalidation and subsequent native reuse
were pending at this checkpoint; the third run below completes save/requery.
Native reuse remains deferred. No initialpose, goal, operational pose application
or movement occurred.

## Third observation: native save, requery and normal UI stop completed

Source `50a30f29580df19450e033fd35777862845b99f7` completed the final stationary
session. Its CI [38844522011](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38844522011)
passed both Linux matrices. The preceding `6590c97` CI
[38843818559](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38843818559)
also passed. The preserved Isaac image, input/camera contracts, runtime config,
managed scope and operational DDS remained unchanged; exact hashes are recorded
in the JSON runtime record.

The actual UI start produced495 WebSocket messages, including162 active frames.
All162 were READY/TRACKING with fresh image, camera pose and current observations,
matched stereo pairs and0ns stereo skew. The READY sample span was55.143477513s.
Overlay aligned159/162 frames (98.15%), with exact selected-image/overlay/quartet
stamp identity and8–992ns quartet skew. Three frames were withheld for
NO_VALID_TIME_ALIGNMENT under the unchanged guard. Current observations ranged
104–332 points; the live SLAM path reached1024 points. A308-point actual global
XYZ snapshot was finite, bounded and consistent with its frame, epoch and counts.
Coverage and engine total remain unknown.

Native save succeeded through the UI and returned package
`np_0a62c6f8130f493baca70a94f57201ad`, revision
`e57e9d40da3165440c848ea13228424df64230048ada3b4ec1fca635fcb8d7aa`.
The official save acknowledgement and nonempty `data.mdb` (1,159,168 bytes) were
verified. After stopping, catalog requery returned the same package/revision;
the archive hash and native artifact size/hash matched, all archive manifest
fields matched the API package, and archived preview exactly matched the reread
preview. The UI showed one native saved map and its308-point preview with a
460-point saved trajectory. Preview consistency is approximate; native load,
reuse and complete retained-map coverage were not exercised.

After save success was confirmed, the normal dashboard stop dialog's
“저장하지 않고 중지” action discarded only observations accumulated after that
save. The saved package remained queryable. The first IDLE sample was
2026-10-16T03:17:38.802235Z; polling bounds creation-to-cleanup at more than
63.925205s and at most65.025593s. Cleanup readback confirmed IDLE, unsaved=false,
cleanup_required=false, camera owner free, RGB available, zero native children
and released camera/domain locks.

Independent before/after comparison confirmed the existing saved-maps API,
missions API, dashboard environment and configuration inventory were unchanged.
The control bridge retained PID982 and InvocationID
`f721d0ea26274d00a0c5bf19456a8cf9`, with identical unit readback. All ten preserved experiment containers retained
their IDs, image references and stopped states. Movement and
initialpose counts remained0, goal idle and operational pose application false.

## Historical pre-deployment baseline and ownership

Fetched source main/origin was `caa4472`; the clean deployed checkout remains
`47c77af19246bd6a455ee873a7c55884ed6e4122` at the read-only 2026-10-16T02:28Z
inspection. The dashboard, control bridge and on-demand RGB relay are running.
There is no installed broker service or dashboard broker socket configuration;
its Stereo capability correctly reports unavailable. The installed RGB relay
lacks the repository's cooperative camera flock. Ten preserved experiment
containers are stopped. No existing container was acquired or changed.

The installed relay unit protects home directories and the filesystem. Merely
pointing its executable at a user checkout would not establish a working
installation. A root-owned release copy, narrow service drop-in and shared
runtime directory are prepared separately. The current unprivileged deployment
account cannot install root units noninteractively. No Docker host-root write
workaround is used.

## Software changes

- Optional fixed managed scope replaces repeated manual expiring ownership
  attestations for the broker. Historical sensor contracts keep their original
  timestamps. Legacy standalone freshness/timeout rules remain unchanged.
- Each start holds a shared camera lock, verifies the actual cooperative relay
  source/process/lock configuration and queries a root-owned, fixed-device,
  read-only owner probe. Incomplete visibility, occupied devices, missing/stale
  reports or mismatched scope fail with a named resource. No producer is killed.
- The same-UID broker reserves its distinct ROS domain and checks its live DDS
  graph before launching. Child proof checks the original observation times and
  live parent lock FDs/inodes. Locks remain held through uncertain cleanup.
- Stereo readiness selects a real timestamp-matched pair from a bounded history
  of sixteen metadata records. The existing 5ms synchronization and 1s freshness
  thresholds are unchanged; source stamps, skew and receive age are exposed.
- Image, camera 6DoF, tracking, overlay, global-map and trajectory availability
  are independent in the UI. Partial/unknown landmark coverage does not hide
  image/pose/path. Resource conflicts survive asynchronous failure and uncertain
  cleanup. Camera pose is not labeled as verified Go2 body pose.

## Approved deployment and first observation

The private reviewed bundle pins exact source, the existing Isaac camera image
`sha256:f9d47c621390b34544de684fea8d62c9bba82f834daa6696733277773f85fdb5`,
source/config hashes, actual device inventory, separate camera/domain locks,
shared canonical paths and rollback. It uses UID1000, host PID visibility,
network=none and private IPC; no Docker socket or privileged broker is supplied.
The dashboard keeps domain0/CycloneDDS; only its Unix broker socket is added.
The broker sources `/opt/ros/humble/setup.bash` and the preserved
`/opt/vslam_lab/realsense/setup.bash` and uses localhost FastDDS/domain71.

The approved authorization bundle covers the root-owned read-only probe,
cooperative RGB relay installation, broker user service/new pinned container,
dashboard candidate restart and a short stationary mapping observation plus
normal same-scope rechecks and cleanup. The user confirmed current stationarity, onsite immediate physical stop and
independent recovery and completed the reviewed administrator action. The
previously root:root mode0664 D435i USB node now uses the approved D435i-only
video-group mode0660 rule; the previous owner/mode is retained for rollback.

First acceptance requires the actual dashboard start path, advancing exact
session/generation WebSocket frames, actual mono8 Image/CameraInfo geometry,
frame IDs/source timestamps/calibration baseline, camera 6DoF and tracking.
Current points, overlay, available global landmarks and trajectory are recorded
separately. Then stop the same session and verify native child/observer exit,
camera lock release and restored camera availability. Preserve raw sensor data
and runtime logs privately. No operational TF, initialpose, Nav2 goal or motion.
Saving/requery and supervised motion are subsequent extensions after this first
observation; they do not block its first screen.

## Validation and current outcome

New focused software checks passed for runtime/pair selection, broker/scope
reservation, fixed read-only ownership probe, API/session conflicts and UI.
One integrated local Python run: 2042 tests, 2040 passed, 2 expected skips
(optional rosbags and Linux /proc on macOS), 0 failures. JavaScript: 385 passed.
SLAM Chromium: 10 passed, plus the final cleanup-conflict focused case passed.
The source secret scan, 83-module JavaScript syntax and Python compilation passed.
Ruff and configured mypy (four existing modules) also passed.
These are hardware-free tests, not sensor acceptance.
The prior exact `47c77af` CI38733978639 remains historical evidence, not evidence
for the new changes. No unchanged baseline suite or VSLAM installation is repeated.

| Requested reporting category | Current evidence |
| --- | --- |
| Actual observation | PASS: third UI start, image/camera6DoF/TRACKING/current points, aligned overlay159/162, finite308-point global snapshot and live trajectory |
| Native map save | PASS: official save acknowledgement, native package and nonempty1,159,168-byte data.mdb |
| Requery and saved preview | PASS: same package/revision, archive/native hashes and exact preview match; UI native map count1, preview308 points and saved trajectory460 |
| Normal UI stop and preservation | PASS: post-save observation discard through stop modal, IDLE/free camera/released locks; existing maps, missions, configuration and bridge invocation preserved |
| Incomplete visualization | Overlay withheld in3/162 frames by unchanged alignment guard; complete global coverage and engine total unknown |
| Precision evaluation not performed | NOT_RUN: independent ground truth and camera-to-Go2 body extrinsic qualification |
| No driving application | NOT_APPLIED: operational TF, initialpose, Nav2 goal and movement0; supervised motion remains separate |
| Deferred follow-up | Native localization/reuse and MAP-02 full retained export remain separate |

Private evidence/bundle: sibling `robot-scope-hardware-validation-private/`
`vslam-observation-20261016/`. Original calibration/profile observations, device
config/environment contents, raw images/maps and installation bytes stay out of
Git. Existing maps, missions, bags and the preserved VSLAM installation remain.
The matched-image correction now retains actual left pixels for at most16
frames/16MiB and selects the newest fresh completed image/calibration/pose/
observations quartet, preserving the1s/20ms guards. Exact selected pixels are
sent with the overlay; current raw camera pose remains independently available.
Real measured33.298ms-lag regression selects the matching pixels at392ns skew.

Correction validation: full Python2046 execution (2020 passed,2 expected skips,
24 broker tests initially blocked by local socket sandbox permission); those24
passed on a focused permitted rerun, yielding2044 passed/2 skipped overall.
JavaScript386, SLAM Chromium10, Ruff, configured mypy, syntax and secret scan
passed. The unchanged old baseline was not rerun.
The package-token0700 correction passed2049 Python cases (2047 passed,2 expected
skips),15 relevant JavaScript cases, Ruff, configured mypy and the secret scan.
Package regressions also passed under both0022 and0077 umasks (20 each);
unsafe-directory fixtures now explicitly set their intended permissions.
The third actual run above supplies the native save/requery acceptance evidence.

The stationary observation, native save, requery/preview and normal-stop scope
is complete. Full retained coverage, native reuse with a validated hint,
independent ground truth, camera-to-Go2 extrinsic qualification and supervised
motion remain separate follow-up work under their applicable current conditions.
