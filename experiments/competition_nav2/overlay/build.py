"""Only two pinned Nav2 packages in a separate overlay; preserve stock lock/install."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args, cwd=None):
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--diagnostic", action="store_true")
    args = p.parse_args()
    lock = json.loads(args.lock.read_text())
    pin = json.loads((ROOT / "source-lock.json").read_text())
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.source, text=True
    ).strip()
    if head != pin["upstream_commit"]:
        raise ValueError("upstream commit mismatch")
    for name, digest in pin["source_sha256"].items():
        if sha(args.source / name) != digest:
            raise ValueError("changed upstream source: " + name)
    args.output.mkdir(parents=True, exist_ok=False)
    command("docker", "tag", lock["image_id"], "c3-round6-stock:locked")
    with tempfile.TemporaryDirectory(prefix="c3-overlay-build-") as tmp:
        context = Path(tmp)
        source = context / "source"
        packages = ("nav2_smac_planner", "nav2_mppi_controller")
        for package in packages:
            shutil.copytree(args.source / package, source / package)
        command("git", "apply", "--check", ROOT / "nav2.patch", cwd=source)
        command("git", "apply", ROOT / "nav2.patch", cwd=source)
        if args.diagnostic:
            command(
                "git", "apply", "--check", ROOT / "atomic-diagnostic.patch", cwd=source
            )
            command("git", "apply", ROOT / "atomic-diagnostic.patch", cwd=source)
            shutil.copyfile(
                ROOT / "c3_atomic_packet.hpp",
                source / "nav2_smac_planner/include/c3_atomic_packet.hpp",
            )
        for package in packages:
            shutil.copyfile(
                ROOT / "c3_exact_footprint.hpp",
                source / package / "include/c3_exact_footprint.hpp",
            )
        shutil.copytree(ROOT / "probe", context / "probe")
        provenance = dict(
            upstream=pin,
            patch_sha256=sha(ROOT / "nav2.patch"),
            exact_checker_sha256=sha(ROOT / "c3_exact_footprint.hpp"),
            overlay_prefix="/opt/c3-overlay",
            underlay_image_id=lock["image_id"],
            original_package_lock_sha256=lock["packages_sha256"],
            modified_sources={n: sha(source / n) for n in pin["source_sha256"]},
            build_tools="Existing locked GCC/CMake/colcon; no apt additions/upgrades",
        )
        if args.diagnostic:
            provenance["atomic_diagnostic"] = {
                "patch_sha256": sha(ROOT / "atomic-diagnostic.patch"),
                "header_sha256": sha(ROOT / "c3_atomic_packet.hpp"),
                "round6_checker_rerun": "NOT_RUN; unchanged 16-case result retained",
            }
        (context / "provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n"
        )
        command(
            "docker",
            "build",
            "--build-arg",
            "STOCK_IMAGE=c3-round6-stock:locked",
            "--iidfile",
            args.output / "image-id.txt",
            "-f",
            ROOT / "Overlay.Dockerfile",
            context,
        )
    image = (args.output / "image-id.txt").read_text().strip()
    packages_tsv = subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            image,
            "dpkg-query",
            "-W",
            "-f=${Package}\t${Version}\n",
        ],
        text=True,
    )
    if packages_tsv != lock["packages_tsv"]:
        raise RuntimeError("overlay runtime apt package lock changed")
    provenance["overlay_image_id"] = image
    provenance["runtime_package_delta"] = []
    (args.output / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    # Distinct runtime lock; never overwrite the original dependency lock.
    lock.update(image_id=image, overlay=provenance)
    (args.output / "overlay-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    if args.diagnostic:
        return
    checker_exit = 0
    try:
        command(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--memory",
            "4g",
            "--cpus",
            "4",
            "--pids-limit",
            "256",
            "--tmpfs",
            "/tmp:rw,size=512m",
            "-v",
            f"{ROOT}:/inputs:ro",
            "-v",
            f"{args.output.resolve()}:/results",
            image,
            "/opt/c3/checker_probe",
            "/inputs/cases.json",
            "/results/fixed.json",
            "overlay",
        )
    except subprocess.CalledProcessError as exc:
        checker_exit = exc.returncode
    result = json.loads((args.output / "fixed.json").read_text())
    libs = sorted(
        {
            s.split()[-1]
            for s in result.pop("loaded_maps")
            if "nav2_smac" in s or "mppi_" in s
        }
    )
    result["loaded_libraries"] = {}
    for lib in libs:
        raw = subprocess.check_output(
            ["docker", "run", "--rm", "--network", "none", image, "cat", lib]
        )
        result["loaded_libraries"][lib] = hashlib.sha256(raw).hexdigest()
    result["cases_sha256"] = sha(ROOT / "cases.json")
    result["returncode"] = checker_exit
    (args.output / "fixed.json").write_text(json.dumps(result, indent=2) + "\n")
    if checker_exit:
        raise SystemExit(checker_exit)


if __name__ == "__main__":
    main()
