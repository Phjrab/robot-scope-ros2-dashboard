# Isaac ROS VSLAM 3.2 official reference verification

Observed 2026-10-13 UTC. This document describes official source/document observations; it is not a claim of Jetson installation, GPU execution, camera compatibility, or motion performance. The [`versions.reference.json`](../../../experiments/isaac_vslam/versions.reference.json) contains exact observed revisions, apt versions and expected asset hash. All downloaded code is from official NVIDIA GitHub, except the explicitly referenced IntelRealSense SDK.

## Supported platform and version boundary

- [Official VSLAM 3.2 repository page](https://nvidia-isaac-ros.github.io/v/release-3.2/repositories_and_packages/isaac_ros_visual_slam/index.html) specifies Jetson Orin, JetPack **6.1 and 6.2**, ROS 2 **Humble**. It does not certify every possible L4T 36.5.2 / mixed CUDA package combination.
- [Official JetPack archive](https://developer.nvidia.com/embedded/jetpack-archive) maps JetPack **6.2.3** to **L4T 36.5.2**. This does not establish the actual installed CUDA userspace.
- [Official RealSense setup](https://nvidia-isaac-ros.github.io/v/release-3.2/getting_started/hardware_setup/sensors/realsense_setup.html) lists D435i/D455 supported; D415 unsupported. It states the required combination is firmware **5.13.0.50**, librealsense **2.55.1**, realsense-ros **4.51.1-isaac** and warns that deviations break examples. Preserve current firmware; report mismatches rather than flash it.

## Exact source pins (all observed remotely)

| Repository | Commit SHA | Actual observed ref |
| --- | --- | --- |
| isaac_ros_visual_slam | e31f4cc1d41a329a01946e5fe63669f8b15da677 | release-3.2; v3.2-15 |
| isaac_ros_common | fcf4d9e17f8f0a7f47f1d22d6a18421ce3768c01 | release-3.2; v3.2-15 |
| isaac_ros_nitros | e3a29804b6de38fefbf7040864124d983bfceb6a | release-3.2; v3.2-15 |
| isaac_ros_examples | 98066652d1ab19a0dd3d9fc4df8ff5321607d46e | release-3.2; v3.2-15 |
| isaac_ros_image_pipeline | d931cce3d0bb4532a0a047f17a15705fc6ac2e1b | release-3.2; v3.2-15 |
| IntelRealSense/librealsense | e196cefa896e312d79c2df400c7623aa1e9c62ac | v2.55.1 |
| NVIDIA-ISAAC-ROS/realsense-ros | c04f43308c00a6f495f14a47cc84cc293047cdff | release/4.51.1-isaac |

`isaac_ros_realsense` is a package in `isaac_ros_examples`, not a separately accessible repository under that name. The VSLAM package is 3.2.6; its node explicitly requires cuVSLAM major 12 / minor 6.

The official arm64 apt index observed VSLAM **3.2.6-0jammy**, and interfaces/examples/nitros/common/realsense **3.2.5-0jammy**. Per-package hashes are in the JSON. These are reference versions, not installed versions; record `dpkg-query` inside the actual image after install and preserve its final image ID/digest.

## Docker review

[run_dev.sh at pinned SHA](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_common/blob/fcf4d9e17f8f0a7f47f1d22d6a18421ce3768c01/scripts/run_dev.sh):

- Reads script config, then user-home config overriding it; reads optional user-home Docker args before script-local args.
- Default name `isaac_ros_dev-aarch64-container`. `CONFIG_CONTAINER_NAME_SUFFIX` affects image/container name.
- Deletes an exited container of its target name and attaches to a running one. Name filtering uses Docker name substring filtering and there is no ownership label verification.
- Uses `--privileged --network host --ipc=host --runtime nvidia`; aarch64 adds `--pid=host`.
- Mounts selected workspace RW, host `/tmp` RW, tegra libraries, VPI, multimedia API, `/dev/input`, X11, `.Xauthority` RW. May forward SSH agent. Mounts `/etc/localtime` RO. Does not explicitly mount Docker socket or whole home by default, but optional config can add mounts.
- Forwards `ROS_DOMAIN_ID` from host; does not establish experimental isolation or prevent arbitrary inherited Docker arguments.
- Therefore use the official build path/image but a reviewed experiment wrapper. No host PID/IPC/network required for initial single-container headless bag replay. Explicit domain, localhost discovery, experiment mounts/logs/labels and no automatic existing-container attachment are appropriate.

[build_image_layers.sh at pinned SHA](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_common/blob/fcf4d9e17f8f0a7f47f1d22d6a18421ce3768c01/scripts/build_image_layers.sh) calculates a Dockerfile MD5 chain to locate prebuilt images, then may build remaining layers. Computed candidates (registry existence/digest NOT_OBSERVED by this reference agent):

- `nvcr.io/nvidia/isaac/ros:aarch64-ros2_humble-realsense_0c5ed46be508cacd00f551276fb6125e`
- `nvcr.io/nvidia/isaac/ros:aarch64-ros2_humble_4c0c55dddd2bbcc3e8d5f9753bee634c`
- `nvcr.io/nvidia/isaac/ros:aarch64_dc1c0c51db74acc2dcbfbc65dbf31d2d`

Inspect registry manifest before selecting. A computed tag is not a verified available image nor a content digest. Dockerfile builds are not fully locked: they use apt updates, moving branch refs and some external sources. Preserve resulting digest, all package versions and exact code SHAs.

## Official sample asset

[Quickstart](https://nvidia-isaac-ros.github.io/v/release-3.2/repositories_and_packages/isaac_ros_visual_slam/isaac_ros_visual_slam/index.html) queries NGC for highest semver major=3, minor<=2. At observation the actual selected asset version is **3.1.0** (there is no 3.2.0 asset); 4.0.0/5.0.0 must not be selected.

- URL: https://api.ngc.nvidia.com/v2/resources/nvidia/isaac/isaac_ros_visual_slam_assets/versions/3.1.0/files/quickstart.tar.gz
- Size: 641870836 bytes
- Official expected SHA256: `32d5b2723b6c6b1998f669f31f1889ebb739e0ada6a5d78c699108e528f15f68`
- Hash source: NGC `/versions/3.1.0/files` response field `sha256_base64` decoded to hex.
- Downloaded hash: NOT_OBSERVED here. Calculate and compare before extraction/use; also inventory bag file hashes.

Official quickstart uses `isaac_ros_examples` visual_slam launch fragment with `rectified_images:=false`, and remaps front/rear raw stereo image/info topics. Review the downloaded `quickstart_interface_specs.json` and bag inventory before choosing number of cameras. Explicit selected input/static TF replay and `/clock` are required for this lab; do not copy the quickstart's broad replay blindly.

## API and measurement semantics

[Official package API](https://nvidia-isaac-ros.github.io/v/release-3.2/repositories_and_packages/isaac_ros_visual_slam/isaac_ros_visual_slam/index.html):

- `enable_imu_fusion=false` / `enable_localization_n_mapping=false`: VO.
- IMU true after verified camera IMU: VIO. Ground constraints default false and should remain false here.
- Mapping true: SLAM. Base frame is the calibrated rig/camera frame, not implicitly robot center.
- `publish_map_to_odom_tf=false`, `publish_odom_to_base_tf=false` disable output transforms.
- `map_frame`, `odom_frame`, `base_frame`, `camera_optical_frames`, `imu_frame` require coherent actual frame IDs; namespace alone cannot rename message fields.
- Input `visual_slam/image_{i}`, `visual_slam/camera_info_{i}`, `visual_slam/imu`; odometry `visual_slam/tracking/odometry`; VO path and SLAM path separate.
- `VisualSlamStatus`: `vo_state` 0 unknown / 1 success / 2 failed. `node_callback_execution_time`, `track_execution_time`, `track_execution_time_mean`, `track_execution_time_max` all seconds. These are algorithm/callback timings, not synchronized sensor-to-subscriber end-to-end latency.
- Node startup logs cuVSLAM version and `CUVSLAM_WarmUpGPU()` duration. Continuous successful output/status is still needed for INSTALL_PASS.

Camera requirements on repository page: >=30 Hz, image period jitter +/-2 ms, stereo offset +/-100 microseconds. Parameters `sync_matching_threshold_ms=5.0` and `image_jitter_threshold_ms=34.0` are matching/drop warning thresholds; they are not the required sensor timing tolerances. Do not widen warnings to claim timing conformity.

Default IMU noise parameters (source and docs) are example/model values, not measured calibration: gyro density 0.000244, gyro walk 0.000019393, accel density 0.001862, accel walk 0.003, calibration_frequency 200.0. D435i supported profiles/rates must be inspected before setting rates.

## Map services: a critical source-level caveat

- `visual_slam/save_map`: `isaac_ros_visual_slam_interfaces/srv/FilePath`, request `string file_path`, response `bool success`.
- `visual_slam/load_map`: same interface. **In this version the callback only stores `load_map_folder_path_ = req->file_path` and returns true. It does not validate reading the map or localization.** `success=true` is not evidence of reuse success.
- `visual_slam/localize_in_map`: `LocalizeInMap`, request `string map_folder_path` plus `geometry_msgs/Pose pose_hint`, response bool success. Pose hint is map_T_robot (base_frame).
- `visual_slam/initial_pose` accepts a PoseWithCovarianceStamped and triggers localization.
- `localize_on_startup=true` uses identity as a pose hint, not global localization. Official documentation explicitly says global localization is not supported and needs an external pose hint.
- Last four map-related services require SLAM enabled. Verify map files plus the actual localize result and corrected pose against the known hint; do not infer automatic global relocalization.

## Validation scope

[Official validation guide](https://nvidia-isaac-ros.github.io/v/release-3.2/concepts/visual_slam/cuvslam/validating_cuvslam_setup.html) gives a measured 1 m straight test (0.95-1.05 m, orientation error <=15 degrees) and approx. 40 m loop test (return translation <=2 m, orientation <=15 degrees). These are example setup validation tolerances and cannot certify autonomous Go2 safety. No movement or physical test was run by this agent.

## Experiment observation reported by the execution agent

The execution agent verified the sensorless official image locally on the Jetson and reported `cuInit(0)` success. The reference image digest is `sha256:dd032d9aa0a4647460ab83dac734a155234a66fabeb80f9c659e7d4542a1ac94`, for `nvcr.io/nvidia/isaac/ros:aarch64-ros2_humble_4c0c55dddd2bbcc3e8d5f9753bee634c`. This verifies CUDA initialization only; the actual bag/status/output evidence must be reported separately in the run manifest. The reference agent did not access the Jetson.

## Scoped apt trust bootstrap inside the experiment container

The official `https://isaac.download.nvidia.com/isaac-ros/repos.key` fetched on 2026-10-13 has 3455 bytes and SHA256 `d45fbd909e89914960a66dba17d4c659adf908ab4d6fe2cf55381e9ffe5ce59d`. It contains two OpenPGP v4 primary keys with fingerprints:

- `428F5D2ACFBC9AA1F8EAC84658F4DA023E691207`
- `9EEB7195A4BD947C572666F9BBE5EA6DE681BCAB`

These fingerprints are observed pins from the official HTTPS endpoint; they are not independent out-of-band authentication. In the experiment container, download using HTTPS with normal certificate verification, compare the exact SHA256, inspect `gpg --show-keys --with-colons`, then dearmor to an experiment-named keyring under `/usr/share/keyrings`. Limit trust with `signed-by` in the container-only source:

```text
deb [arch=arm64 signed-by=/usr/share/keyrings/isaac-ros-lab.gpg] https://isaac.download.nvidia.com/isaac-ros/release-3 jammy release-3.0
```

Use ordinary `apt-get update` signature verification. Do not use `trusted=yes`, `--allow-unauthenticated`, or disabled HTTPS verification. The observed `Release` is dated 2025-11-06, lists arm64/amd64 and the `release-3.0` component, and records SHA256 `7b562d31ba5cbdcbddbfa67c484aa7709019d208fe550feee491c815f32eba54` for the 38277-byte arm64 `Packages.gz`. This document captures repository identity and package pinning, not proof of installation.
