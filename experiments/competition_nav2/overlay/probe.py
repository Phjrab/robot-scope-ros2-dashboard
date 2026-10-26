"""Build/run the native small checker only, on the preserved locked underlay."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def command(*args):
    subprocess.run(list(map(str, args)), check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    lock = json.loads(args.lock.read_text())
    command("docker", "tag", lock["image_id"], "c3-round6-stock:locked")
    iid = args.output / "probe-image-id.txt"
    command("docker", "build", "--build-arg", "STOCK_IMAGE=c3-round6-stock:locked",
            "--iidfile", iid, "-f", ROOT / "Probe.Dockerfile", ROOT)
    image = iid.read_text().strip()
    command("docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--read-only", "--memory", "4g",
            "--cpus", "4", "--pids-limit", "256", "--tmpfs", "/tmp:rw,size=512m",
            "-v", f"{ROOT}:/inputs:ro", "-v", f"{args.output.resolve()}:/results",
            image, "/opt/c3/checker_probe", "/inputs/cases.json", "/results/stock.json", "stock")
    result = json.loads((args.output / "stock.json").read_text())
    libs = sorted({s.split()[-1] for s in result.pop("loaded_maps") if "nav2_smac" in s or "mppi_" in s})
    result["loaded_libraries"] = {}
    for lib in libs:
        raw = subprocess.check_output(["docker", "run", "--rm", "--network", "none", image, "cat", lib])
        result["loaded_libraries"][lib] = hashlib.sha256(raw).hexdigest()
    result["underlay_image_id"] = lock["image_id"]
    result["probe_image_id"] = image
    result["cases_sha256"] = hashlib.sha256((ROOT / "cases.json").read_bytes()).hexdigest()
    (args.output / "stock.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
