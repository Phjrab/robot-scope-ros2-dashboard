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
the reviewed administrator installer. Source `ffa1b21` is deployed; exact CI
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
| Actual observation success | PASS: actual UI start, image/camera6DoF/TRACKING/current points/trajectory/global-count readback, UI stop and device cleanup |
| Incomplete visualization | PARTIAL: overlay65/180; global238 count observed but first collector omitted its coordinates; coverage remains unknown |
| Precision evaluation not performed | NOT_RUN; no independent ground truth or body extrinsic qualification |
| No driving integration | No operational TF/initialpose/goal/movement; camera observation only |

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
Next minimum action is a short same-scope stationary display/save/requery check.
Supervised motion remains separate.
