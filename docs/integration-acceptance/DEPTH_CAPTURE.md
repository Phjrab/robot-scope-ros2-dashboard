# Stationary RealSense depth collection

This additive mode collects evidence for a separate pitch-calibration UI. It does
not estimate an angle, assume a level seated body, change factory calibration,
write camera flash, publish TF, change the VSLAM base frame, or send robot commands.
Existing stereo VSLAM and Isaac versions remain unchanged.

## Baseline and hardware qualification

Source baseline: `c6fedc05e5086fa755cc92b1a2cf2daa56ffc41a`; the working tree was clean
before this task and `origin/main` matched. Read-only inspection on 2026-10-17 found
robot source `91f9006de6162d9e48f635f5f79a76e014950fd8`, clean; `robot-scope.service`
PID 19437 and the user `robot-scope-slam-broker.service` PID 19266 active. The last
Stereo session was IDLE with no camera reservation. Control bridge was inactive
and disabled. No service, stream or robot state was changed by that inspection.

The broker uses UID 1000 and `/run/robot-scope-slam/broker.sock`, sharing the existing
camera lock, managed scope, source and data mounts. Operational dashboard DDS stays
domain 0/CycloneDDS; isolated broker environment remains domain 71/localhost/FastDDS.

Existing configuration requests IR1/IR2 mono8, 640×480 at 30 Hz; RGB, depth and IMU
are disabled by the camera launcher. The previous actual launch record explicitly
labels these as **requested parameters, not runtime verification**. No camera is
currently running, so a current effective `enable_depth` readback and delivered FPS
are **not observed**. Earlier real snapshots demonstrate actual timestamp-matched
stereo pairs with zero skew; the readiness pair matcher uses bounded histories and
a 5 ms gate (the feature-overlay alignment gate is a separate 20 ms). This is not
continuous present-time stream verification.

The retained same-device contract records D435i serial `242322077753`, firmware
`5.17.3.10`, librealsense `2.55.1`, wrapper `4.51.1`, historical USB 2.1/480 Mbps and
common IR profiles 640×480×30, 640×360×30, 480×270×60. These historical observations
are **not a new device/profile probe**, and do not prove a depth profile is supported.
Start checks exact current serial, inventory and both requested profiles before
opening the one pipeline, then validates the effective profiles after start.

Existing ROS inputs are `/vslam_lab/camera/infra1/image_rect_raw` and
`infra2/image_rect_raw` with their `camera_info` topics. The retained CameraInfo
convention places right projection in the left optical frame; it must not be
rewritten. This new collector uses native SDK frames and factory intrinsics, not
those ROS topic names. Its `camera_info.json` is explicitly SDK-derived, not a
fabricated ROS CameraInfo observation; original SDK intrinsics are retained.

The preserved container `robot-scope-stereo-ffa1b218f68e` has native SDK libraries
2.55.1 and `pyrsutils`, but its `pyrealsense2` namespace lacks `pipeline`, `context`
and `config`. Collection correctly reports `REALSENSE_SDK_UNAVAILABLE` until the
matching Python binding is provisioned. No binding/SDK/image upgrade or installation
was performed in this task. New actual depth samples have **not been collected**.

## Collection and return to Stereo

1. Finish and explicitly stop the current SLAM mode. Resolve unsaved-map choices
   in that mode; the depth panel never discards a map or switches mode automatically.
2. In Mapping, use **정지 Depth 캡처**. The operator seats and
   fixes the robot, sets camera pitch, then confirms robot seated, robot stationary
   and camera stationary. Start uses existing session/broker/camera ownership.
3. After input readiness, confirm those conditions again and capture one sample.
   The collector waits for a new SDK frameset after receiving the confirmation;
   it never saves the pre-confirmation cached frame. Physical exposure after the
   confirmation is not independently calibrated; receipt/source times stay distinct.
4. Download the raw ZIP, the lossless IR image and, only if qualified, compatibility
   JSON. For another angle, manually adjust the camera, let it stop, and reconfirm.
   Keep the same wall, robot position, nominal height and yaw. No angle algorithm or
   point-selection UI is included here.
5. Stop the collection session and wait for IDLE and `camera.reserved=false`.
   Failed cleanup retains ownership and blocks a second producer; do not remove locks.
   The default 120-second session limit stops acquisition automatically (maximum
   configurable 300 seconds), but explicit Stop still reconciles/releases ownership.
6. Select the original Stereo mode and start explicitly when desired. Existing
   Stereo configuration has not been edited. The bridge stays OFF unless separately
   requested; collection does not restore control or authorize motion.

The API requires the normal same-origin/manual-mode gates. Start:

```json
POST /api/v1/slam/depth/sessions
{"request_id":"angle-session-001","robot_seated":true,"robot_stationary":true,"camera_stationary":true}
```

Poll `/api/v1/slam/session` for the returned session/generation and depth readiness.
Capture uses fresh operator confirmations and an idempotency key:

```json
POST /api/v1/slam/sessions/<session_id>/depth-samples
{"generation":1,"request_id":"angle-sample-001","robot_seated":true,"robot_stationary":true,"camera_stationary":true,"body_attitude":null}
```

Optional independently known `body_attitude` has `quaternion_xyzw`, `frame_id`,
`source`, `source_timestamp_ns` (string) and `clock_domain`. It is recorded as
supplied evidence, not measured or applied by this collector. No attitude is
invented when it is absent. Reuse the exact request ID/body to reconcile a lost
response; do not blindly recapture using a different ID. The UI does not auto-retry
uncertain mutations; inspect the saved-sample list and exact session first.

List `/api/v1/slam/depth/samples`; download
`/api/v1/slam/depth/samples/<sample_id>/{export,compatibility,image}`. Standard
`/api/v1/slam/sessions/<session_id>/stop` takes generation, request_id and
`discard_unsaved:false`. Camera release is after successful owned pipeline cleanup.

## Pixel and depth contract

Only IR1 Y8 + depth Z16 are requested, in one SDK pipeline, in a separate mode.
There is no second RealSense process, RGB correspondence assumption, SDK alignment,
resampling or depth filter. Original frames retain their stride, endian, frame
numbers, timestamps/domains, effective profiles, intrinsics, inter-stream extrinsics,
scale, device identity and observed options. Logical SDK optical frame IDs are
labelled `sdk_logical_optical_not_ros_tf` and are not operational frames.

A compatibility file requires all of:

- Actual stream/profile/dimensions/FPS and SDK frameset membership verified.
- Equal recognized timestamp domains and source skew ≤1 ms, independently of the
  unchanged VSLAM thresholds.
- Both factory models are pinhole (`none`, or Brown-Conrady with all zero
  coefficients), matching intrinsics, and identity depth-to-IR1 extrinsics.
- Valid original Y8/Z16 layouts, positive measured depth scale and device serial.

Only then is the unchanged IR1 image a verified rectified pinhole click image with
same-pixel depth interpreted as optical Z. `rectified:true` describes that checked
mathematical model, not a renamed distorted image. Original model/coefficients
remain in the artifact. Nonzero/unsupported distortion or nonidentity alignment
preserves originals and withholds compatibility; this version does not rectify it.

Raw zero depth becomes JSON `null`; nonzero values are scaled to metres without
invented confidence or range filtering. Valid-depth ratio means nonzero Z16 pixels,
not geometrically correct pixels. Browser CSS may resize the PNG visually but
native PNG dimensions and intrinsics remain unchanged. External selection tools
must convert displayed coordinates back to native image pixels.

Illustrative JSON shape only (not a captured measurement):

```json
{"id":"<sample_id>","width":2,"height":1,
 "intrinsics":{"fx":100.0,"fy":100.0,"cx":0.5,"cy":0.0},
 "depth_m":[1.25,null],"points":[],
 "metadata":{"serial":"<actual serial>","frame_id":"realsense_ir1_optical",
 "profile_id":"<profile hash>","rectified":true,"synthetic":false,
 "depth_semantics":"optical_z","click_image_file":"click.png",
 "source_timestamps_ms":{"ir1":1234.0,"depth":1234.0},
 "timestamp_domain":"timestamp_domain.hardware_clock",
 "alignment":{"frameset_verified":true,"source_skew_ms":0.0}}}
```

`depth_m` is a single row-major array of exactly width×height entries. The actual
artifact also records frame numbers and the exact alignment/intrinsics proof.
The original archive remains separate from this convenience JSON.

## Storage and enabling

The installation chooses `<multi-slam-root>/depth-samples/<sample_id>/`; no HTTP
caller can select a filesystem path. In the inspected deployment this resolves to:

`/home/unitree/robot-scope-data/runtime/state/navigation/multi-slam/depth-samples/`

This is the **configured destination**, not an existing real sample. Each atomic
private sample contains `manifest.json`, `metadata.json`, SDK-derived
`camera_info.json`, original `ir1.y8`, original `depth.z16` when present, lossless
`click.png`/`depth.png` when layout-valid, and conditionally `compatibility.json`.
The manifest records hashes and sizes. Defaults limit collection to 64 samples,
1 GiB total, 64 MiB/sample, and 64 MiB free-space reserve. Existing samples are never
pruned automatically. Sample directories/files are 0700/0600.

The broker's new optional `--depth-config` defaults to `depth-capture.json` beside
its existing `--config`. Creating this separate private configuration is explicit
administrator enablement; an absent file leaves depth disabled. Example profile
must first be supported by the live selected device:

```json
{"schema_version":1,"serial":"242322077753","width":640,"height":480,"fps":30,
 "managed_scope":"/home/unitree/.config/robot-scope/stereo-observation/scope.json",
 "max_session_s":120}
```

Runtime imports the native Python binding only in the isolated broker. Dashboard
uses its existing `ROBOT_SCOPE_SLAM_BROKER_SOCKET`, same UID and shared store path.
A missing/unsafe depth store disables this optional feature without disabling
existing Stereo startup. Do not loosen path permissions or remove ownership locks.

## Validation and remaining hardware work

Software fixture validation covers normal sample+export, missing depth, effective
and per-frame profile mismatch, source-time/domain mismatch, disconnect/no-frame,
post-confirmation freshness, storage failure, exact session retry, mode exclusion,
stop failure/retained lock and explicit return to Stereo. Fixtures are not real
sensor captures. Final local Python run: 2,219 tests, 2,217 passed and two existing skips.
Ruff, configured mypy and Python 3.10 AST checks passed. JavaScript/browser
E2E: 127 passed, including four synthetic depth DOM scenarios. Full JS unit
results are recorded in DEPTH_CAPTURE_VALIDATION.json. Browser tests verify
rendering, exact requests, native image dimensions and download URLs/mock GETs;
ASGI tests separately verify actual archive/JSON/PNG bytes. A native browser file
save on the robot dashboard remains unverified.

No actual depth session, present-time device/firmware/profile/CameraInfo readback,
USB bandwidth/resource benchmark or same-device concurrent VSLAM test is claimed.
Concurrent VSLAM+depth is deliberately unsupported by this first version: the
shared session and camera owner reject it. Existing IR FPS/timestamp/tracking and
CPU/GPU/memory/USB impact after a depth→Stereo transition still need a bounded
stationary hardware check; software regressions alone do not qualify that behavior.

Before deployment, bundle approval for the exact candidate, matching SDK Python
binding provision (no Isaac/SDK version change), separate config, dashboard/broker
restart, and stationary capture→export→stop→camera-free verification. The operator
must currently confirm the seated fixed posture, stopped camera and immediate
physical recovery. A subsequent Stereo check is a separate explicit mode transition
inside that same agreed window. Do not send sit/stand/move, initialpose or goals.
Depth collection is not a fix for duplicated walls or native SLAM trajectory jumps.
