# Stationary RealSense depth collection

This additive mode collects evidence for a separate pitch-calibration UI. It does
not estimate an angle, assume a level seated body, change factory calibration,
write camera flash, publish TF, change the VSLAM base frame, or send robot commands.
Existing stereo VSLAM and Isaac versions remain unchanged.

## Initial read-only baseline (superseded by the approved trial below)

Source baseline: `c6fedc05e5086fa755cc92b1a2cf2daa56ffc41a`; the working tree was clean
before this task and `origin/main` matched. During publication, the independently
developed pitch prototype `98ef9e1` arrived on main and was merged without modifying
its implementation; export metadata was then checked against its input validator. Read-only inspection on 2026-10-17 found
robot source `91f9006de6162d9e48f635f5f79a76e014950fd8`, clean; `robot-scope.service`
PID 19437 and the user `robot-scope-slam-broker.service` PID 19266 active. The last
Stereo session was IDLE with no camera reservation. Control bridge was inactive
and disabled. No service, stream or robot state was changed by that inspection.

The broker uses UID 1000 and `/run/robot-scope-slam/broker.sock`, sharing the existing
camera lock, managed scope, source and data mounts. Operational dashboard DDS stays
domain 0/CycloneDDS; isolated broker environment remains domain 71/localhost/FastDDS.

Existing configuration requests IR1/IR2 mono8, 640×480 at 30 Hz; RGB, depth and IMU
are disabled by the camera launcher. The previous actual launch record explicitly
labels these as **requested parameters, not runtime verification**. At that initial
inspection no camera was running, so effective `enable_depth` and delivered FPS
were **not observed then**. Earlier real snapshots demonstrate timestamp-matched
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

The initial inspection found native SDK 2.55.1 libraries and `pyrsutils` in
`robot-scope-stereo-ffa1b218f68e`, but no usable Python `pipeline/context/config`
binding. The software correctly failed closed. That prerequisite was resolved
within the later approved window below; this initial inspection is historical.

## Approved deployment and actual collection — 2026-10-17

The user approved the exact candidate and confirmed seated fixed posture, a stopped
camera and onsite physical recovery. Source `78e23ce9edb59790a665055dfd23f230be018b43`
passed [exact-candidate CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/39021392502)
and was deployed by clean fast-forward; 1,335 source-file hashes matched. Only the
existing dashboard and broker services restarted. Original environment, Stereo
configuration and protected map/state inventory remained unchanged.

The matching CPython 3.10/aarch64 binding was extracted from the already-preserved
SDK source image, with no build, pip install, SDK/Isaac upgrade or camera flash
write. Only the broker entry received a private `PYTHONPATH` hook:
`/home/unitree/.config/robot-scope/stereo-observation/python-sdk-2.55.1/`.
The extension SHA256 is `8399161c0a44d6c83f7139278158062ff1236690b75e93d0fc9feb76cf3bcf31`;
it loads the original `/usr/local/lib/librealsense2.so.2.55.1`, whose SHA256 remains
`29a4a449467099d760f60792bace16becebace674af3c0885a5ef930e8d22d26`.
The camera image remains `sha256:f9d47c621390b34544de684fea8d62c9bba82f834daa6696733277773f85fdb5`.
Operational DDS remains domain 0/CycloneDDS; the broker remains isolated as before.
The separate private `depth-capture.json` selects the approved 640×480×30 profile
and 120-second maximum. Full runtime/config/binding hashes are in the validation JSON.

One real sample, `a58f3549f327424f8b6241d89783974f`, was captured at
`2026-10-17T09:52:23.508534+00:00` in session `d81a694df06d4237a40d8e67554f584c`.
The device reported D435I serial `242322077753`, firmware `5.17.3.10`, USB 2.1 and
107 supported profiles. Actual active streams were IR1 Y8 and depth Z16, both
640×480 at nominal 30 FPS. Both source timestamps were `1792230743487.6013` ms in
`timestamp_domain.global_time`, with zero skew. Frame counters were IR1=55/depth=56;
these distinct counters are preserved, not relabelled as equal. Sustained delivered
FPS was not measured. Body attitude is null; seated body level is not inferred.

The actual intrinsics match between IR1 and depth: fx=fy=`386.559326171875`,
cx=`324.52630615234375`, cy=`240.6450653076172`. Both report Brown-Conrady with
all zero coefficients, and depth→IR1 extrinsics are identity, so the existing
strict compatibility gate produced same-pixel rectified optical-Z JSON without
resampling. Measured scale is `0.0010000000474974513` m/raw unit. All 307,200 pixels
were checked: 293,270 nonzero pixels (95.4655%); 13,930 raw zeros match JSON nulls;
every other value equals raw×scale exactly. Both lossless PNGs equal their raw
pixels, all seven archive member hashes match, and separately fetched image/JSON
match the archive. `points` is empty and `synthetic=false`. This verifies data
correspondence, not depth accuracy or pitch.

The real Mapping panel selected this saved sample and displayed its actual image.
ZIP, JSON and image were successfully reread through their HTTP endpoints. The
native browser download wait timed out, so browser file-save completion is not
claimed. The depth session reached cleanup in 10.56 s, with camera ownership released.

An explicit sequential Stereo tracking-only session then opened the original
IR1/IR2 Y8 640×480×30 profiles. Live ROS parameter readback confirms
`enable_depth=false`, `enable_color=false`, `enable_infra1=true`, `enable_infra2=true`
and `enable_sync=false`; driver sync is off and the existing backend timestamp
matcher retains its 5 ms readiness limit. Six retained pair snapshots had zero skew.
Current SDK calibration and WebSocket intrinsics were retained; complete current
ROS CameraInfo matrices/static-TF equality were not recorded. Historical
CameraInfo contracts do not substitute for that missing current check.

During the Stereo window 159 active WebSocket observations reported tracking,
image, camera pose, current observations and trajectory; 157 also had overlay.
Global map was unavailable in this tracking-only session. There was one WebSocket
connection error and two connections. Stop was requested at 60.22 s; cleanup
completed at 65.59 s. Final session state was IDLE, camera reservation false/known,
and the bridge remained OFF and disabled. Final inspection at
`2026-10-17T10:03:00.834449+00:00` also confirmed that the observation-created
domain 71 CLI daemon was stopped; only the existing broker Python process remained
in the camera container. Deployed source remained clean; original config hashes
and map-package revisions matched. No posture/movement commands, operational TF application, initialpose
or goal were issued.

After the completed observation window, the dashboard showed Go2 direct ROS
**disconnected** at 19:01 KST. The dashboard/API and saved real sample remained
available, as shown in private `deployed-depth-sample.png`. The disconnect cause
was not established; successful sample retrieval does not qualify the current
robot ROS connection as healthy.

This demonstrates mode transition and observation recovery, **not unchanged
performance**. Native logs contain 93 interframe-gap warnings (87 above 60 ms,
maximum 166.50 ms) and 25 libusb temporary-resource warnings on the USB 2.1 link.
The last 16 cached timestamps span grew from roughly 0.5 s to 1.5 s. This is evidence
of observer/delivery/processing slowdown, not a sustained sensor-FPS measurement
or a proven effect of depth collection. No matched pre/post Stereo baseline exists.

Whole-Jetson tegrastats sampling (179 samples, approximately 1 s intervals) recorded:

| Phase | Samples | Mean per-core CPU | Mean RAM | Sampled mean GR3D |
| --- | ---: | ---: | ---: | ---: |
| Before depth | 14 | 25.63% | 1502.29 MB | 0% |
| Depth including start/stop | 10 | 35.69% | 1541.40 MB | 0% |
| Between sessions | 94 | 28.76% | 1522.63 MB | 0% |
| Stereo including startup | 60 | 43.68% | 1810.30 MB | 7.6% |

One additional sample belongs to partial Stereo stopping. These are whole-system,
unequal windows, including instrumentation and lifecycle overhead, not per-process
cost or a causal regression benchmark. Sparse GPU samples do not prove no GPU use;
cuVSLAM reports `use_gpu=true`. USB throughput and calibrated sensor-to-screen
latency were not measured.

## Concurrent main publication

During closeout, concurrent commit `eb0a9c67c51b3c2805a42843baafe30ff5deb36e`
added Settings import/point-selection calibration. Its passing CI and code were
preserved in the documentation merge; no duplicate solver/UI was added here.
That newer Settings integration was **not deployed in this camera window**.
The actual device/evidence qualification remains pinned to `78e23ce`; validation
source hashes identify that deployed revision rather than the newer main.
Merged-source validation ran 2,260 Python tests: 2,233 passed, two existing skips,
and 25 temporary Unix-socket cases blocked by the local sandbox. Those exact
25 cases passed when rerun with local socket permission; no product failures
remain. JavaScript: 428 passed. Passing `eb0a9c6` browser CI is reused because
the merged product/test/experiment tree matches it; only evidence docs differ.

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
 "source_timestamp":1.234,"source_timestamp_unit":"seconds",
 "clock_domain":"timestamp_domain.hardware_clock",
 "alignment":{"method":"verified_identity_depth_to_ir1_no_resampling"},
 "synchronization":{"frameset_verified":true,"source_skew_ms":0.0}}}
```

`depth_m` is a single row-major array of exactly width×height entries. The actual
artifact also records frame numbers and the exact alignment/intrinsics proof.
The original archive remains separate from this convenience JSON.

The separate `experiments/realsense_mount_calibration` prototype accepts this
individual object for point selection. For multiple angles, combine unchanged
objects into `{"samples":[sample1,sample2]}` before importing (2–12 samples; that
prototype currently supports at most 640×480). `points` remains empty until the
user selects them there. Its required `source_timestamp` alias uses IR1 SDK time
in seconds in the explicitly named `clock_domain`; original per-stream milliseconds
are also preserved. Static geometric `alignment` is separated from per-capture
`synchronization`, so small valid pairing differences do not masquerade as a
changed calibration. This integration adds no pitch-solving code.

## Storage and enabling

The installation chooses `<multi-slam-root>/depth-samples/<sample_id>/`; no HTTP
caller can select a filesystem path. In the inspected deployment this resolves to:

`/home/unitree/robot-scope-data/runtime/state/navigation/multi-slam/depth-samples/`

The actual sample is stored beneath that directory as
`a58f3549f327424f8b6241d89783974f/`. Its downloaded evidence copy is private under
`robot-scope-hardware-validation-private/depth-capture-20261017/depth-run-1/`
outside Git. Each atomic private sample contains `manifest.json`, `metadata.json`,
SDK-derived
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

## Validation and remaining work

Software fixture validation covers normal sample+export, missing depth, effective
and per-frame profile mismatch, source-time/domain mismatch, disconnect/no-frame,
post-confirmation freshness, storage failure, exact session retry, mode exclusion,
stop failure/retained lock and explicit return to Stereo. Fixtures are not real
sensor captures. Final local Python run: 2,220 tests, 2,218 passed and two existing skips.
Ruff, configured mypy and Python 3.10 AST checks passed. JavaScript/browser
E2E: 127 passed, including four synthetic depth DOM scenarios. Full JS unit
results are recorded in DEPTH_CAPTURE_VALIDATION.json. Browser tests verify
rendering, exact requests, native image dimensions and download URLs/mock GETs;
ASGI tests separately verify actual archive/JSON/PNG bytes. A native browser file
save on the robot dashboard remains unverified.

The approved actual depth session, HTTP export reread and sequential Stereo check
are detailed above, separately from software fixtures. Same-device VSLAM+depth
concurrency remains deliberately unsupported; existing session/camera ownership
excludes it. No additional implementation changed during the hardware window,
so the passing exact-source software/CI evidence is reused rather than presenting
another unchanged full run as new validation.

Remaining collection work is a user-directed multi-angle series on the same wall,
with a fixed robot position/height/yaw and fresh camera/robot-stationary confirmation
at each capture. The separate pitch UI owns point selection and angle calculation.
A future window must match current equipment/onsite conditions; this completed
single-window approval does not start another session automatically. Keep the
bridge OFF; no sit/stand/move, operating TF application, initialpose or goals.
Independent accuracy, camera-to-body extrinsics and native SLAM geometry diagnosis
remain separate work. Depth collection does not fix or qualify duplicated walls
or trajectory jumps. Sustained IR FPS, complete current ROS CameraInfo/static-TF
comparison, USB throughput, calibrated display latency and matched before/after
performance remain unverified; observed warnings must not be hidden by claiming
that the new mode has no effect.

The concurrently published prototype source was preserved. Its standalone full
TestClient suite could not run in the current root environment because httpx2 is
absent; no package was installed. The new export-to-existing-validator contract
test passes within the root suite. This is format interoperability, not an angle
accuracy or camera calibration result.
