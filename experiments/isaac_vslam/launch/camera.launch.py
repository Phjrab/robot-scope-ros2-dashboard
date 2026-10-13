"""D435i driver for an observed free camera in a coordinated experiment slot.

Targets NVIDIA realsense-ros release/4.51.1-isaac, not newer parameter APIs.
Gyro and accel rates are deliberately not forced to the official example's 200.
"""

import json
import os
from pathlib import Path
import runpy

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

CONTRACT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "config" / "launch_contract.py"))


def launch_setup(context):
    CONTRACT["isolated_environment"](os.environ)
    value = lambda name: LaunchConfiguration(name).perform(context)
    input_path = value("camera_contract")
    parameters = CONTRACT["validate_camera"](
        json.loads(Path(input_path).read_text()), value("stereo_profile"),
        enable_imu=value("enable_imu").lower() == "true",
        gyro_fps=int(value("gyro_fps")), accel_fps=int(value("accel_fps")),
        emitter=value("emitter"))
    remappings = [("/tf", "/vslam_lab/tf"), ("/tf_static", "/vslam_lab/tf_static"),
                  ("/diagnostics", "/vslam_lab/camera/diagnostics")]
    CONTRACT["record_launch"](
        value("run_dir"), "camera_launch.json", input_path, parameters,
        namespace="/vslam_lab/camera", remappings=remappings,
        ros_domain_id=os.environ["ROS_DOMAIN_ID"],
        ros_localhost_only=os.environ["ROS_LOCALHOST_ONLY"])
    return [Node(
        name="driver", namespace="/vslam_lab/camera",
        package="realsense2_camera", executable="realsense2_camera_node",
        parameters=[parameters], remappings=remappings, output="screen")]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("camera_contract", description="Recent ownership and supported-profile evidence JSON"),
        DeclareLaunchArgument("run_dir", description="Existing dedicated directory for this run"),
        DeclareLaunchArgument("stereo_profile", description="Observed common left/right IR WIDTHxHEIGHTxFPS; start with supported 30 Hz"),
        DeclareLaunchArgument("enable_imu", default_value="false", choices=["true", "false"]),
        DeclareLaunchArgument("gyro_fps", default_value="0", description="0 omits rate; positive value must be observed supported"),
        DeclareLaunchArgument("accel_fps", default_value="0", description="0 omits rate; positive value must be observed supported"),
        DeclareLaunchArgument("emitter", default_value="preserve", choices=["preserve", "0"], description="0 requires prior value and restoration plan"),
        OpaqueFunction(function=launch_setup),
    ])
