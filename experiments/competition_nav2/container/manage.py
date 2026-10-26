"""Build with network; run immutable image with --network none. No host changes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
PACKAGES = [
    "ros-humble-navigation2",
    "ros-humble-nav2-bringup",
    "ros-humble-rmw-fastrtps-cpp",
    "python3-numpy",
    "python3-scipy",
    "python3-yaml",
]


def command(runtime, *args, capture=True):
    return subprocess.run(
        [runtime, *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    ).stdout


def build(args):
    lock = json.loads(args.lock.read_text()) if args.lock.exists() else None
    if lock:
        base = lock["base_digest"]
        versions = dict(line.split("\t") for line in lock["packages_tsv"].splitlines())
        specs = " ".join(p + "=" + versions[p] for p in PACKAGES)
    else:
        command(args.runtime, "pull", "ros:humble-ros-base-jammy", capture=False)
        image = json.loads(
            command(args.runtime, "image", "inspect", "ros:humble-ros-base-jammy")
        )[0]
        base = image["RepoDigests"][0]
        specs = " ".join(PACKAGES)
    if not re.fullmatch(r"[a-zA-Z0-9_./:-]+@sha256:[a-f0-9]{64}", base):
        raise ValueError("base image must be digest-pinned")
    iid = args.lock.parent / "c3-image-id.tmp"
    args.lock.parent.mkdir(parents=True, exist_ok=True)
    command(
        args.runtime,
        "build",
        "--build-arg",
        "BASE_IMAGE=" + base,
        "--build-arg",
        "PACKAGE_SPECS=" + specs,
        "--iidfile",
        str(iid),
        "-f",
        str(ROOT / "container/Dockerfile"),
        str(ROOT / "container"),
        capture=False,
    )
    image_id = iid.read_text().strip()
    packages = command(
        args.runtime,
        "run",
        "--rm",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        image_id,
        "cat",
        "/opt/c3-packages.tsv",
    )
    resolved = dict(
        status="RESOLVED_BY_BUILD",
        base_digest=base,
        image_id=image_id,
        packages_tsv=packages,
        packages_sha256=hashlib.sha256(packages.encode()).hexdigest(),
        rebuild_note="Reuse image_id for identical runtime. Rebuilding exact transitive apt graph requires an archive/snapshot; compare full package lock and reject differences.",
    )
    if lock and packages != lock["packages_tsv"]:
        raise RuntimeError(
            "transitive package lock changed; original lock preserved; retain existing image or supply exact apt snapshot"
        )
    args.lock.write_text(json.dumps(resolved, indent=2) + "\n")
    iid.unlink()


def run(args):
    lock = json.loads(args.lock.read_text())
    image = lock["image_id"]
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ValueError("run requires a resolved immutable local image ID")
    inspected = json.loads(command(args.runtime, "image", "inspect", image))[0]
    if inspected["Id"] != image:
        raise ValueError("image ID mismatch")
    args.output.mkdir(parents=True, exist_ok=False)
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    name = "c3-nav2-" + uuid.uuid4().hex[:12]
    container_path = "/repo/experiments/competition_nav2"
    script = container_path + "/execute.py"
    argv = [
        args.runtime,
        "create",
        "--name",
        name,
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--pids-limit",
        "256",
        "--memory",
        "4g",
        "--cpus",
        "4",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m,mode=1777",
        "--mount",
        f"type=bind,src={REPO},dst=/repo,readonly",
        "--mount",
        f"type=bind,src={args.output.resolve()},dst=/results",
        "-e",
        "ROS_LOCALHOST_ONLY=1",
        "-e",
        "ROS_DOMAIN_ID=193",
        "-e",
        "C3_IMAGE_ID=" + image,
        "-e",
        "C3_SOURCE_SHA=" + source_sha,
        image,
        "python3",
        script,
        "--controller",
        args.controller,
        *(
            ["--fixture", "/repo/" + str(args.fixture.resolve().relative_to(REPO))]
            if args.fixture
            else ["--scenario", args.scenario or "empty"]
        ),
        "--variant",
        args.variant,
        "--repeat",
        str(args.repeat),
        "--seed",
        str(args.seed),
        "--output",
        "/results/run",
    ]
    receipt = dict(
        command=argv,
        image_id=image,
        source_sha=source_sha,
        network_mode=None,
        container_name=name,
    )
    created = False
    try:
        subprocess.run(argv, check=True)
        created = True
        inspection = json.loads(command(args.runtime, "inspect", name))[0]
        receipt["network_mode"] = inspection["HostConfig"]["NetworkMode"]
        if receipt["network_mode"] != "none" or inspection["HostConfig"].get(
            "Privileged"
        ):
            raise RuntimeError("container isolation inspection rejected")
        (args.output / "container_receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )
        started = subprocess.run([args.runtime, "start", "-a", name], check=False)
        state = json.loads(command(args.runtime, "inspect", name))[0]["State"]
        receipt["exit_code"] = state["ExitCode"]
        receipt["runtime_return_code"] = started.returncode
        if state.get("OOMKilled"):
            receipt["failure"] = "OOMKilled"
        return state["ExitCode"]
    finally:
        if created:
            command(args.runtime, "rm", "-f", name)
            receipt["container_removed"] = True
        (args.output / "container_receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("operation", choices=["build", "run"])
    p.add_argument("--runtime", choices=["docker", "podman"], default="docker")
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--controller", choices=["rpp", "mppi"], default="rpp")
    p.add_argument("--variant", choices=["baseline", "tuned"], default="baseline")
    selection = p.add_mutually_exclusive_group()
    selection.add_argument("--scenario")
    selection.add_argument("--fixture", type=Path)
    p.add_argument("--seed", type=int, default=20261024)
    p.add_argument("--repeat", type=int, default=0)
    args = p.parse_args()
    if not shutil.which(args.runtime):
        p.error(
            "installed container runtime required; this tool never installs a daemon"
        )
    if args.operation == "run" and args.output is None:
        p.error("--output required for run")
    sys.exit(build(args) if args.operation == "build" else run(args))
