"""Default OFF. Local synthetic costmaps + planner only; no command publisher.

Native execution is owned by D3. Set PYTHONPATH to the reviewed C4 source tree.
No ROS import or package lookup occurs when importing this launch module.
"""


def generate_launch_description():
    from launch import LaunchDescription
    from launch.actions import DeclareLaunchArgument, OpaqueFunction
    return LaunchDescription([
        DeclareLaunchArgument("enabled", default_value="false"),
        DeclareLaunchArgument("params_file", default_value=""),
        OpaqueFunction(function=_start),
    ])


def _start(context):
    from launch.substitutions import LaunchConfiguration
    if LaunchConfiguration("enabled").perform(context) != "true":
        return []
    from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig, require_local_ros, NAMESPACE
    config = RuntimeConfig(mode="isolated_ros")
    require_local_ros(config)  # Local /proc only, before any ROS node launches.
    from ament_index_python.packages import get_package_share_directory
    from pathlib import Path
    import xml.etree.ElementTree as ET
    for package in ("nav2_costmap_2d", "nav2_planner", "nav2_navfn_planner"):
        share = Path(get_package_share_directory(package))
        if ET.parse(share/"package.xml").getroot().findtext("version") != "1.1.20":
            raise ValueError("NAV2_1_1_20_REQUIRED")
    # Generated parameters must contain only the scoped review subset. Never
    # pass production controller/behavior/bridge parameters through this launch.
    import yaml
    params_path = Path(LaunchConfiguration("params_file").perform(context))
    if not params_path.is_file():
        raise ValueError("GENERATED_REVIEW_PARAMS_REQUIRED")
    parameters = yaml.safe_load(params_path.read_text())
    if set(parameters) != {NAMESPACE}:
        raise ValueError("REVIEW_NAMESPACE_REQUIRED")
    from robot_dashboard.obstacle_runtime_adapter.nav2 import validate_launch_parameters
    validate_launch_parameters(parameters[NAMESPACE])
    from launch_ros.actions import Node
    common = dict(namespace=NAMESPACE, output="screen")
    nodes = [
        Node(package="nav2_planner", executable="planner_server", name="planner_server",
             parameters=[str(params_path)], remappings=[("plan", "/review/plan")], **common),
        Node(package="nav2_costmap_2d", executable="nav2_costmap_2d", name="local_costmap",
             namespace=NAMESPACE+"/local_costmap", parameters=[str(params_path)], output="screen"),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager", name="review_lifecycle",
             parameters=[{"autostart": True, "node_names": ["planner_server", "local_costmap/local_costmap"]}], **common),
    ]
    # Static transforms belong to this synthetic world only. D3 supplies the
    # reviewed radius and input geometry; no robot TF is queried or replaced.
    for parent, child, xyz in (("map", "odom", (0,0,0)), ("odom", "base_link", (0,0,0)),
                                ("base_link", "review_lidar", (0,0,.3)),
                                ("base_link", "review_depth", (.25,0,.4))):
        nodes.append(Node(package="tf2_ros", executable="static_transform_publisher",
            name="review_tf_"+child, arguments=["--x",str(xyz[0]),"--y",str(xyz[1]),"--z",str(xyz[2]),
                "--roll","0","--pitch","0","--yaw","0","--frame-id",parent,"--child-frame-id",child], **common))
    return nodes
