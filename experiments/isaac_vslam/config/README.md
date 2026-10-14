# Launch configuration and evidence

These launch files target `isaac_ros_visual_slam` release-3.2 commit
`e31f4cc1d41a329a01946e5fe63669f8b15da677`, package 3.2.6. Camera parameters
target NVIDIA `realsense-ros` `release/4.51.1-isaac`, commit
`c04f43308c00a6f495f14a47cc84cc293047cdff`. They do not use the newer
`isaac_ros_cuvslam` interface.

Run the launch files by absolute filename inside the isolated container; no
installation into the host ROS workspace is needed. The wrapper must set a
checked unused `ROS_DOMAIN_ID` and `ROS_LOCALHOST_ONLY=1`, remove inherited DDS
profiles, and set the run's ROS log directory. If the operational domain is known,
also set `VSLAM_LAB_OPERATIONAL_DOMAIN_ID`; equality is rejected.

```sh
ros2 launch /lab/code/launch/vslam.launch.py \
  input_contract:=/lab/run/input-contract.json run_dir:=/lab/run \
  mode:=vo use_sim_time:=true
```

The modes are `vo`, `vio`, `slam_vo`, and `slam_vio`. VO and VIO disable mapping.
SLAM must follow a passing VO/VIO stage. All modes disable both output TFs and
both ground-plane constraints. Output world frames are `vslam_lab_map` and
`vslam_lab_odom`. The observed camera base frame is preserved. No transform to
the robot body is invented. Set the actual camera reference frame in the contract
and report trajectories with that reference point.

`/tf` and `/tf_static` are remapped to `/vslam_lab/tf` and
`/vslam_lab/tf_static` in both launches. VSLAM outputs appear under
`/vslam_lab/visual_slam/`; diagnostics are remapped to `/vslam_lab/diagnostics`.
Remap only selected original bag images, CameraInfo, IMU (when needed), and
sensor static TF into these experiment topics. Replay with `--clock`; do not
replay old estimator outputs or dynamic TF. All bag consumers use
`use_sim_time=true`. Live inputs use `false`. Domain separation and localhost
discovery do not isolate GPU or USB resources.

## Input observation contract

Copy `input_contract.example.json` to the runtime run directory and fill it only
from observations. Its initial `NOT_OBSERVED` state intentionally fails launch.
The contract is a record of checks, not a replacement for actual sensor
measurement. `evidence_path` must identify the retained observations (CameraInfo
values, message samples, timestamp statistics, and TF inspection). The launcher
does not claim a contract alone proves the live input still matches it.

Before setting `calibration_verified` and `static_transforms_verified`:

- Check both images' encoding and matching Image/CameraInfo `frame_id`; the
  live starter expects real, distinct `mono8` IR streams. Bag input also accepts
  `rgb8`, explicitly supported by 3.2 `TocuVSLAMImageEncoding`; the official raw
  sample must use its observed `rectified_images=false`. Other formats need an
  explicit verified conversion before this input contract.
- Retain each camera's actual dimensions, K/D/R/P and distortion model. Check
  finite valid focal lengths, matching dimensions and raw/rectified semantics.
  Do not copy one camera's calibration to the other.
- Retain the real static transform chain from `base_frame` to each optical frame,
  compute its physical baseline and record the positive distance in `baseline_m`.
  Distinct frame names alone do not prove two independent cameras.
- Verify image stamp order and left/right timestamp differences. Record whether
  timestamps share host ROS time or bag ROS time; unknown clocks cannot yield a
  claimed end-to-end latency. The 34 ms image jitter warning and 5 ms matching
  threshold are version defaults, not sensor quality acceptance thresholds.
- For a bag record its SHA-256 in `source.sha256` and `clock_domain=bag_ros`.
  For live use camera serial/segment as `source.id` and verify
  `clock_domain=host_ros`. Clock uncertainty must be investigated before launch.

VIO additionally needs the D435i IMU's actual frame, units, axes, timestamp/rate,
and camera-IMU TF checks. `imu.measured_rate_hz` supplies `calibration_frequency`;
neither 200 Hz nor matching gyro/accel rates are assumed. The four noise values
must be supplied with their source. `imu_official_example.json` preserves the
official uncalibrated example values for an explicitly labeled baseline; it is
not automatically applied and is not a device calibration. Go2 body IMU is not
connected by these launch files.

Each launch writes an exclusive `vslam_launch.json` or `camera_launch.json` into
`run_dir`, with requested parameters and a SHA-256 of the observation contract.
Use a fresh run directory; existing evidence is never overwritten. The manifest
is labeled `LAUNCH_REQUESTED_NOT_RUNTIME_VERIFIED`; capture `ros2 param dump`
and effective process environment after startup to verify runtime configuration.

## Camera ownership and supported profiles

```sh
ros2 launch /lab/code/launch/camera.launch.py \
  camera_contract:=/lab/run/camera-contract.json run_dir:=/lab/run \
  stereo_profile:=640x480x30 enable_imu:=false emitter:=preserve
```

`640x480x30` is an example candidate, not a claimed observation. There is no
default profile. The exact selected profile must appear in the observed profile
intersection of **both** IR streams. Copy `camera_contract.example.json` and
retain serial, model, USB speed, firmware, SDK and wrapper versions. Set
`owner_status=FREE` and `camera_time_slot_confirmed=true` only after checking
host processes, containers, device opens and competing work with the system
owner. The ownership check must be no more than five minutes old. This is not
an atomic lock or an assurance that other tasks obey the experiment lock.

The driver is pinned to that serial. Its namespace is `/vslam_lab/camera`, and
`camera_name=vslam_lab_camera` supplies actual driver frame prefixes such as
`vslam_lab_camera_infra1_optical_frame`. Still inspect published frame names;
namespace alone never rewrites message frame IDs. Only the driver publishes
its device-calibrated static TF on `/vslam_lab/tf_static`.

Gyro and accel are disabled initially. With `enable_imu=true`, omitted rates
use the driver's supported selection; explicitly supplied rates must appear in
the observed rate lists. Measure the resulting rates before VIO. No camera
firmware operation is performed.

`emitter=preserve` does not request a device option change. NVIDIA's 3.2 VSLAM
example disables the emitter. To test that setting, `emitter=0` requires the
previous value and a concrete `emitter_restore_command` in the contract. Before
stopping this experiment-owned driver, restore and read back that value through
its parameter interface, retaining the result. If restoration fails, report it
and leave that sensor handoff pending. The recorded restoration string is never
automatically executed. Do not stop an operational driver to obtain the camera.

Map paths are not auto-filled. Use the version's explicit save/localize services
with experiment directories after a successful SLAM stage. `localize_on_startup`
and `enable_request_hint` are false; no automatic global localization is implied.

## Observed official quickstart sample

`official_sample.input.json` and `official_sample.replay.json` describe the
actual NGC `isaac_ros_visual_slam_assets` 3.1.0 quickstart inspected on the Jetson.
The retained `official_sample.inspection.json` is small message metadata only.
The original SQLite file SHA-256 is
`f9baa7b80d456aaf89ea69d1cc312775b763f185c073887ad5ac4c3f05e9afca`.
Copy the retained inspection verbatim to `/lab/data/quickstart-inspection.json`;
its exact file hash is checked before publishing sensor transforms.

This sample has 60 front images per side, 59 front CameraInfo messages per side,
1920×1200 `rgb8` raw images, about two seconds of data, and no IMU input. Select
`mode=vo`, `use_sim_time=true`, `rectified_images=false`; VIO is intentionally
rejected. This short sample verifies installation/input handling only and cannot
establish prolonged tracking, motion accuracy, loop closure, or Go2 performance.

The original `/tf_static` contains one message with many robot hardware frames.
Do not replay that entire topic or the recorded `/tf`. `selected_static_tf.py`
selects the four exact ancestor transforms from `front_stereo_camera` to its left
and right optical frames, retaining recorded values and timestamps. It publishes
only `/vslam_lab/tf_static` and adds no robot body/world transform. The recorded
static TF baseline is 0.15 m; the right CameraInfo projection matrix implies
0.14950314164161682 m. Both values remain in the observation record; no calibration
is adjusted to make them equal. The output reference point is the recorded camera
rig frame, not the Go2 body.
