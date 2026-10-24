"""Actual Humble servers. This launch refuses a non-isolated environment."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def generate_launch_description():
    from preflight import require_isolated

    require_isolated()
    from launch import LaunchDescription
    from launch.actions import DeclareLaunchArgument, OpaqueFunction
    from launch.substitutions import LaunchConfiguration
    from launch_ros.actions import Node
    from nav2_common.launch import RewrittenYaml

    def setup(context):
        run_dir = Path(LaunchConfiguration("run_dir").perform(context)).resolve()
        params = RewrittenYaml(
            source_file=str(run_dir / "params.yaml"),
            root_key="c3_nav2",
            param_rewrites={},
            convert_types=True,
        )
        specs = [
            ("nav2_map_server", "map_server"),
            ("nav2_planner", "planner_server"),
            ("nav2_controller", "controller_server"),
            ("nav2_behaviors", "behavior_server"),
            ("nav2_bt_navigator", "bt_navigator"),
        ]
        nodes = []
        for package, name in specs:
            remaps = [
                ("/tf", "tf"),
                ("/tf_static", "tf_static"),
                ("/diagnostics", "/c3_nav2/diagnostics"),
            ]
            if name in ("controller_server", "behavior_server"):
                remaps += [("cmd_vel", "raw/" + name)]
            nodes.append(
                Node(
                    package=package,
                    executable=name,
                    name=name,
                    namespace="c3_nav2",
                    output="screen",
                    parameters=[params],
                    remappings=remaps,
                )
            )
        nodes.append(
            Node(
                package="nav2_lifecycle_manager",
                executable="lifecycle_manager",
                name="lifecycle_manager_navigation",
                namespace="c3_nav2",
                parameters=[params],
                remappings=[("/diagnostics", "/c3_nav2/diagnostics")],
                output="screen",
            )
        )
        return nodes

    return LaunchDescription(
        [DeclareLaunchArgument("run_dir"), OpaqueFunction(function=setup)]
    )
