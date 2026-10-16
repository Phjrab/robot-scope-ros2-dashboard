"""Fixed managed stereo SLAM launch using preserved, observed lab contracts.

No systemd, Docker, map/odom TF authority, IMU enablement, or device option
changes are performed here. Camera reservation is held by the application.
"""

import json
import os
from pathlib import Path
import runpy

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode


PROJECT = Path(__file__).resolve().parents[2]
CONTRACT = runpy.run_path(str(PROJECT / "experiments/isaac_vslam/config/launch_contract.py"))


def setup(context):
    CONTRACT["isolated_environment"](os.environ)
    def value(name):
        return LaunchConfiguration(name).perform(context)
    input_path, camera_path = value("input_contract"), value("camera_contract")
    mode = value("mode")
    parameters, remaps = CONTRACT["validate_input"](json.loads(Path(input_path).read_text()), mode, False)
    parameters.update(enable_slam_visualization=True, enable_landmarks_view=True,
                      enable_observations_view=True, path_max_size=1024,
                      publish_map_to_odom_tf=False, publish_odom_to_base_tf=False)
    scope_path, proof_path = value("managed_scope"), value("reservation_proof")
    if scope_path or proof_path:
        if not scope_path or not proof_path:
            raise ValueError("managed scope and live reservation proof must be supplied together")
        from robot_dashboard.slam_managed_scope import load_managed_scope, private_json, validate_reservation_proof
        scope = load_managed_scope(Path(scope_path), domain_id=int(os.environ["ROS_DOMAIN_ID"]),
            operational_domain_id=int(os.environ["VSLAM_LAB_OPERATIONAL_DOMAIN_ID"]))
        proof = private_json(Path(proof_path))
        validate_reservation_proof(proof, scope)
        camera = CONTRACT["validate_camera_profile"](json.loads(Path(camera_path).read_text()), value("stereo_profile"))
    else:
        camera = CONTRACT["validate_camera"](json.loads(Path(camera_path).read_text()), value("stereo_profile"))
    CONTRACT["record_launch"](value("run_dir"), "managed_slam_launch.json", input_path, parameters,
                             mode=mode, namespace="/vslam_lab", remappings=remaps)
    CONTRACT["record_launch"](value("run_dir"), "managed_camera_launch.json", camera_path, camera)
    node = ComposableNode(name="visual_slam_node", namespace="/vslam_lab",
        package="isaac_ros_visual_slam", plugin="nvidia::isaac_ros::visual_slam::VisualSlamNode",
        parameters=[parameters], remappings=remaps)
    return [Node(name="driver", namespace="/vslam_lab/camera", package="realsense2_camera",
                 executable="realsense2_camera_node", parameters=[camera],
                 remappings=[("/tf", "/vslam_lab/tf"), ("/tf_static", "/vslam_lab/tf_static"),
                             ("/diagnostics", "/vslam_lab/camera/diagnostics")], output="screen"),
            ComposableNodeContainer(name="robot_scope_managed_stereo", namespace="/vslam_lab",
                package="rclcpp_components", executable="component_container_mt",
                composable_node_descriptions=[node],
                remappings=[("/tf", "/vslam_lab/tf"), ("/tf_static", "/vslam_lab/tf_static")], output="screen")]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("input_contract"), DeclareLaunchArgument("camera_contract"),
        DeclareLaunchArgument("stereo_profile"), DeclareLaunchArgument("run_dir"),
        DeclareLaunchArgument("managed_scope", default_value=""),
        DeclareLaunchArgument("reservation_proof", default_value=""),
        DeclareLaunchArgument("mode", choices=["vo", "slam_vo"]),
        OpaqueFunction(function=setup)])
