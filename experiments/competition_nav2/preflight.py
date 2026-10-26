"""Read-only host probe; fail closed before importing ROS or starting a graph."""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def probe():
    return dict(
        os_release=Path("/etc/os-release").read_text(),
        architecture=platform.machine(),
        container_runtimes={
            n: shutil.which(n) for n in ("docker", "podman", "nerdctl")
        },
        ros_distributions=[p.name for p in Path("/opt/ros").glob("*")],
        network_interfaces=sorted(p.name for p in Path("/sys/class/net").iterdir()),
        current_network_namespace=os.readlink("/proc/self/ns/net"),
        native_launch_attempted=False,
    )


def isolated_errors(evidence, env=None, container_marker=None):
    env = os.environ if env is None else env
    container_marker = (
        Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()
        if container_marker is None
        else container_marker
    )
    errors = []
    if not container_marker:
        errors.append("require a network-none container")
    if evidence["network_interfaces"] != ["lo"]:
        errors.append("non-loopback interface exists")
    if env.get("ROS_DISTRO") != "humble":
        errors.append("ROS_DISTRO must be humble")
    if env.get("ROS_LOCALHOST_ONLY") != "1" or env.get("ROS_DOMAIN_ID") != "193":
        errors.append("require ROS_LOCALHOST_ONLY=1 and ROS_DOMAIN_ID=193")
    if env.get("RMW_IMPLEMENTATION") != "rmw_fastrtps_cpp":
        errors.append("require pinned Fast DDS middleware")
    for key in (
        "ROS_DISCOVERY_SERVER",
        "FASTRTPS_DEFAULT_PROFILES_FILE",
        "FASTDDS_DEFAULT_PROFILES_FILE",
        "CYCLONEDDS_URI",
    ):
        if env.get(key):
            errors.append("external DDS discovery/profile override: " + key)
    if (
        'VERSION_ID="22.04"' not in evidence["os_release"]
        or "ID=ubuntu" not in evidence["os_release"]
    ):
        errors.append("require Ubuntu 22.04 container")
    return errors


def require_isolated():
    evidence = probe()
    evidence["errors"] = isolated_errors(evidence)
    routes = Path("/proc/net/route").read_text().splitlines()[1:]
    if any(line.split()[0] != "lo" for line in routes if line.strip()):
        evidence["errors"].append("non-loopback IPv4 route")
    if evidence["errors"]:
        raise RuntimeError(json.dumps(evidence, indent=2))
    return evidence


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--inside", action="store_true")
    args = p.parse_args()
    evidence = probe()
    evidence["errors"] = isolated_errors(evidence) if args.inside else []
    available = any(evidence["container_runtimes"].values())
    evidence["status"] = "READY_FOR_CONTAINER_BUILD" if available else "NOT_RUN"
    evidence["blockers"] = (
        []
        if available
        else [
            "No installed container CLI; Humble absent on host; no host changes authorized by C3 scope."
        ]
    )
    evidence["namespace_probe"] = (
        subprocess.run(
            ["unshare", "-Urn", "true"], capture_output=True, text=True
        ).__dict__
        if shutil.which("unshare")
        else None
    )
    # CompletedProcess.__dict__ contains only args, returncode, stdout, stderr.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 2 if evidence["status"] == "NOT_RUN" or evidence["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
