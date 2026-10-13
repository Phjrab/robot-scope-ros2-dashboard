"""ROS-independent launch guards; observation assertions are not runtime proof.

Reference: isaac_ros_visual_slam e31f4cc1d41a329a01946e5fe63669f8b15da677.
The launch files intentionally do not create sensor transforms or calibration.
"""

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re


def observed(value, label):
    if not isinstance(value, str) or not value.strip() or value in {
        "NOT_OBSERVED", "NOT_RUN", "N/A", "UNKNOWN"
    }:
        raise ValueError(f"{label} needs an observed value")
    return value


def positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} needs a positive finite number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} needs a positive finite number")
    return value


def lab_topic(value, label):
    value = observed(value, label)
    if not re.fullmatch(r"/vslam_lab/(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"{label} must be an absolute /vslam_lab/... topic")
    return value


def frame(value, label):
    value = observed(value, label)
    if value.startswith("/") or any(c.isspace() for c in value):
        raise ValueError(f"{label} must be an observed TF frame without leading slash/spaces")
    if value in {"map", "odom", "vslam_lab_map", "vslam_lab_odom"}:
        raise ValueError(f"{label} must refer to a sensor, not an estimated world frame")
    return value


def require_observation(contract):
    if contract.get("schema_version") != 1 or contract.get("observation_state") != "OBSERVED":
        raise ValueError("An OBSERVED schema_version=1 contract is required; examples are not evidence")
    observed(contract.get("evidence_path"), "evidence_path")


def validate_input(contract, mode, use_sim_time):
    require_observation(contract)
    modes = json.loads(Path(__file__).with_name("modes.json").read_text())
    if mode not in modes:
        raise ValueError("mode must be vo, vio, slam_vo, or slam_vio")
    source = contract.get("source", {})
    if source.get("kind") not in {"live", "bag"}:
        raise ValueError("source.kind must be live or bag")
    observed(source.get("id"), "source.id (serial or bag identifier)")
    if (source["kind"] == "bag") != use_sim_time:
        raise ValueError("Bag replay requires use_sim_time=true; live requires false")
    if source["kind"] == "bag" and not re.fullmatch(r"[a-fA-F0-9]{64}", source.get("sha256") or ""):
        raise ValueError("Bag input requires its SHA-256")
    expected_clock = "bag_ros" if use_sim_time else "host_ros"
    if contract.get("clock_domain") != expected_clock:
        raise ValueError(f"Input timestamps must be verified in {expected_clock}; do not subtract unrelated clocks")
    for flag in ("calibration_verified", "static_transforms_verified"):
        if contract.get(flag) is not True:
            raise ValueError(f"{flag} must be observed; no synthetic identity transforms are supplied")
    positive(contract.get("baseline_m"), "observed stereo baseline_m")
    if not isinstance(contract.get("rectified_images"), bool):
        raise ValueError("rectified_images must be observed as true or false")

    frames, remaps = [], []
    for index, side in enumerate(("left", "right")):
        camera = contract.get(side, {})
        image_frame = frame(camera.get("image_frame"), f"{side}.image_frame")
        if camera.get("camera_info_frame") != image_frame:
            # Pinned wrapper updateExtrinsicsCalibData deliberately expresses
            # right P in left optical coordinates. 3.2 uses the explicit
            # camera_optical_frames override for TF; retain actual metadata.
            convention = (side == "right" and contract.get("rectified_images") is True and
                          contract.get("camera_info_frame_semantics") == "realsense_4_51_1_right_projection_in_left_frame" and
                          camera.get("camera_info_frame") == contract.get("left", {}).get("image_frame") and
                          isinstance(contract.get("camera_info_convention_evidence"), str) and
                          contract["camera_info_convention_evidence"].strip())
            if not convention:
                raise ValueError(f"{side}: Image and CameraInfo frame_id must agree or have the verified pinned RealSense projection convention")
        # 3.2 TocuVSLAMImageEncoding explicitly supports MONO8 and RGB8. The
        # official raw sample may be RGB8; live D435i experiments use IR mono8.
        allowed_encodings = {"mono8", "rgb8"} if source["kind"] == "bag" else {"mono8"}
        if camera.get("encoding") not in allowed_encodings:
            raise ValueError(f"{side}: encoding must be one of {sorted(allowed_encodings)}; use a verified converter for other formats")
        frames.append(image_frame)
        remaps.extend([
            (f"visual_slam/image_{index}", lab_topic(camera.get("image_topic"), f"{side}.image_topic")),
            (f"visual_slam/camera_info_{index}", lab_topic(camera.get("camera_info_topic"), f"{side}.camera_info_topic")),
        ])
    if frames[0] == frames[1] or remaps[0][1] == remaps[2][1] or remaps[1][1] == remaps[3][1]:
        raise ValueError("Stereo inputs require distinct cameras, topics, and optical frames")

    params = {
        **modes[mode],
        "num_cameras": 2,
        "min_num_images": 2,
        "base_frame": frame(contract.get("base_frame"), "base_frame"),
        "camera_optical_frames": frames,
        "map_frame": "vslam_lab_map",
        "odom_frame": "vslam_lab_odom",
        "rectified_images": contract["rectified_images"],
        "enable_image_denoising": False,
        "enable_ground_constraint_in_odometry": False,
        "enable_ground_constraint_in_slam": False,
        "publish_map_to_odom_tf": False,
        "publish_odom_to_base_tf": False,
        "enable_landmarks_view": False,
        "enable_observations_view": False,
        "enable_debug_mode": False,
        "enable_request_hint": False,
        "localize_on_startup": False,
        "override_publishing_stamp": False,
        "image_jitter_threshold_ms": 34.0,
        "sync_matching_threshold_ms": 5.0,
        "use_sim_time": use_sim_time,
    }
    if params["enable_imu_fusion"]:
        imu = contract.get("imu", {})
        if imu.get("verified") is not True or imu.get("units_axes_timestamps_and_transform_verified") is not True:
            raise ValueError("VIO requires observed IMU units, axes, timestamps, rate, and sensor transform")
        observed(imu.get("noise_source"), "imu.noise_source (calibration or named uncalibrated example)")
        params["imu_frame"] = frame(imu.get("frame"), "imu.frame")
        params["calibration_frequency"] = float(positive(imu.get("measured_rate_hz"), "imu.measured_rate_hz"))
        for name in ("gyro_noise_density", "gyro_random_walk", "accel_noise_density", "accel_random_walk"):
            params[name] = float(positive(imu.get(name), f"imu.{name}"))
        remaps.append(("visual_slam/imu", lab_topic(imu.get("topic"), "imu.topic")))
    remaps.extend([
        ("/tf", "/vslam_lab/tf"),
        ("/tf_static", "/vslam_lab/tf_static"),
        ("/diagnostics", "/vslam_lab/diagnostics"),
    ])
    return params, remaps


def validate_camera(contract, stereo_profile, enable_imu=False, gyro_fps=0, accel_fps=0,
                    emitter="preserve", now=None):
    require_observation(contract)
    if contract.get("owner_status") != "FREE" or contract.get("camera_time_slot_confirmed") is not True:
        raise ValueError("Camera ownership must be FREE and its time slot coordinated before starting a driver")
    try:
        checked = dt.datetime.fromisoformat(contract["checked_at_utc"].replace("Z", "+00:00"))
        if checked.tzinfo is None:
            raise ValueError("timezone required")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("checked_at_utc must contain a recent timezone-aware observation") from error
    now = now or dt.datetime.now(dt.timezone.utc)
    age = (now - checked).total_seconds()
    if age < -5 or age > 300:
        raise ValueError("Recheck camera owners/profiles immediately before launch (observation older than 5 minutes)")
    for name in ("serial", "model", "firmware", "usb_speed", "sdk_version", "wrapper_version"):
        observed(contract.get(name), name)
    if "D435I" not in contract["model"].upper():
        raise ValueError("This experiment camera launcher requires an observed D435i")
    if not re.fullmatch(r"[1-9][0-9]*x[1-9][0-9]*x[1-9][0-9]*", stereo_profile):
        raise ValueError("stereo_profile must be WIDTHxHEIGHTxFPS")
    if stereo_profile not in contract.get("supported_stereo_profiles", []):
        raise ValueError("Requested stereo profile was not observed on BOTH IR streams")
    params = {
        "camera_name": "vslam_lab_camera",
        "serial_no": contract["serial"],
        "enable_infra1": True,
        "enable_infra2": True,
        "enable_color": False,
        "enable_depth": False,
        "depth_module.profile": stereo_profile,
        "enable_gyro": enable_imu,
        "enable_accel": enable_imu,
        "unite_imu_method": 2 if enable_imu else 0,
        "publish_tf": True,
        "tf_publish_rate": 0.0,
        "publish_odom_tf": False,
        "use_sim_time": False,
    }
    for name, fps, supported in (
        ("gyro_fps", gyro_fps, "supported_gyro_rates"),
        ("accel_fps", accel_fps, "supported_accel_rates"),
    ):
        if fps < 0 or (fps and (not enable_imu or fps not in contract.get(supported, []))):
            raise ValueError(f"{name} must be omitted/0 or an observed supported rate with IMU enabled")
        if fps:
            params[name] = fps
    if emitter not in {"preserve", "0"}:
        raise ValueError("emitter accepts preserve or 0; no firmware or other device option changes")
    if emitter == "0":
        if contract.get("emitter_before") not in (0, 1, 2, 3):
            raise ValueError("Record the previous emitter option before changing it")
        observed(contract.get("emitter_restore_command"), "emitter_restore_command")
        params["depth_module.emitter_enabled"] = 0
    return params


def isolated_environment(environ):
    domain = environ.get("ROS_DOMAIN_ID", "")
    if not domain.isdigit() or not 1 <= int(domain) <= 232:
        raise ValueError("Wrapper must explicitly select a checked, unused ROS_DOMAIN_ID (1..232)")
    if environ.get("ROS_LOCALHOST_ONLY") != "1":
        raise ValueError("Wrapper must set ROS_LOCALHOST_ONLY=1")
    operational = environ.get("VSLAM_LAB_OPERATIONAL_DOMAIN_ID")
    if operational is not None and domain == operational:
        raise ValueError("Experiment and operational ROS_DOMAIN_ID must differ")
    lab_profile = (environ.get("VSLAM_LAB_DDS_PROFILE") == "local-shm-v1" and
                   environ.get("FASTRTPS_DEFAULT_PROFILES_FILE") == "/lab/code/config/fastdds-local.xml")
    if (environ.get("CYCLONEDDS_URI") or environ.get("FASTDDS_DEFAULT_PROFILES_FILE") or
            (environ.get("FASTRTPS_DEFAULT_PROFILES_FILE") and not lab_profile)):
        raise ValueError("Do not inherit operational DDS profiles; use the isolated wrapper")


def record_launch(run_dir, filename, contract_path, parameters, **extra):
    directory = Path(run_dir)
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError("run_dir must be an existing absolute directory for this experiment run")
    content = Path(contract_path).read_bytes()
    record = {
        "status": "LAUNCH_REQUESTED_NOT_RUNTIME_VERIFIED",
        "contract_sha256": hashlib.sha256(content).hexdigest(),
        "contract": json.loads(content),
        "requested_parameters": parameters,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        **extra,
    }
    # Refuse to overwrite a previous run's launch evidence.
    with (directory / filename).open("x") as output:
        json.dump(record, output, indent=2, sort_keys=True)
        output.write("\n")
