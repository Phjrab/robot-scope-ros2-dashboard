"""Independent Isaac ROS 3.2 stereo VO/VIO/SLAM; no driver or fabricated TF.

Run by absolute path inside the pinned ROS container. An observed input contract
and the isolated wrapper environment are required; see ../config/README.md.
"""

import json
import os
from pathlib import Path
import runpy

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

CONTRACT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "config" / "launch_contract.py"))


def launch_setup(context):
    CONTRACT["isolated_environment"](os.environ)
    value = lambda name: LaunchConfiguration(name).perform(context)
    input_path = value("input_contract")
    mode = value("mode")
    use_sim_time = value("use_sim_time").lower() == "true"
    parameters, remappings = CONTRACT["validate_input"](
        json.loads(Path(input_path).read_text()), mode, use_sim_time)
    parameters["debug_dump_path"] = str(Path(value("run_dir")) / "debug")
    CONTRACT["record_launch"](
        value("run_dir"), "vslam_launch.json", input_path, parameters,
        mode=mode, namespace="/vslam_lab", remappings=remappings,
        executor=value("executor"),
        ros_domain_id=os.environ["ROS_DOMAIN_ID"],
        ros_localhost_only=os.environ["ROS_LOCALHOST_ONLY"])
    node = ComposableNode(
        name="visual_slam_node", namespace="/vslam_lab",
        package="isaac_ros_visual_slam",
        plugin="nvidia::isaac_ros::visual_slam::VisualSlamNode",
        parameters=[parameters], remappings=remappings)
    return [ComposableNodeContainer(
        name="vslam_lab_container", namespace="/vslam_lab",
        package="rclcpp_components", executable=("component_container_mt" if value("executor") == "multi" else "component_container"),
        composable_node_descriptions=[node],
        # release-3.2 VisualSlamImpl constructs TransformListener(*tf_buffer),
        # which creates its own node. It does not inherit the component node's
        # remappings, so set process-global TF remaps on the container as well.
        remappings=[("/tf", "/vslam_lab/tf"), ("/tf_static", "/vslam_lab/tf_static")],
        output="screen")]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("input_contract", description="Observed input evidence JSON; example is intentionally invalid"),
        DeclareLaunchArgument("run_dir", description="Existing dedicated directory for this run; manifest must not already exist"),
        DeclareLaunchArgument("mode", default_value="vo", choices=["vo", "vio", "slam_vo", "slam_vio"]),
        DeclareLaunchArgument("executor", default_value="multi", choices=["single", "multi"],
                              description="Multi-thread executor keeps images processing during blocking localization calls"),
        DeclareLaunchArgument("use_sim_time", choices=["true", "false"], description="true for bag plus /clock, false for live"),
        OpaqueFunction(function=launch_setup),
    ])
