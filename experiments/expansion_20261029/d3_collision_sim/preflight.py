"""Read-only availability report. Never installs, starts ROS, or opens sockets."""

import importlib.util
import json
from pathlib import Path
import platform
import shutil


def probe():
    runtimes = {n: shutil.which(n) for n in ("docker", "podman", "nerdctl", "ros2")}
    return dict(
        evidence_kind="NATIVE_NAV2_SIM",
        status="NOT_RUN",
        platform=platform.platform(),
        runtimes=runtimes,
        ros_setups=[str(p) for p in Path("/opt/ros").glob("*/setup.bash")],
        rclpy_available=importlib.util.find_spec("rclpy") is not None,
        launch_attempted=False,
        setup_attempted=False,
        required=dict(
            ros="Humble",
            nav2="1.1.20",
            network="none; loopback only",
            namespace="/robot_scope_review_x",
            domain=194,
            ROS_LOCALHOST_ONLY="1",
            motion_sink="fake_only; native_commands_drive_plant",
        ),
        reason="No certified isolated D3 native environment/C4 adapter; availability is not launch authorization.",
    )


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
