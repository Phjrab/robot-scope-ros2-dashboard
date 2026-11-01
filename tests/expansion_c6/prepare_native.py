"""Extract four fixed JSON members per scenario from the exact reviewed D3 artifact."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

HASH = "0f09cf101555dbef3368fc6913acd9cdd61e380ad45c51472ea5e6b1b3cdc6aa"
SHA = "fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d"
CASES = (
    "empty",
    "diagnostic_single_obstacle",
    "fully_blocked",
    "diagnostic_appearing_obstacle",
    "sensor_stale",
)


def prepare(archive, output):
    if (
        archive.stat().st_size > 16 * 1024 * 1024
        or hashlib.sha256(archive.read_bytes()).hexdigest() != HASH
    ):
        raise ValueError("NATIVE_ARTIFACT_HASH")
    output.mkdir(mode=0o700)
    with zipfile.ZipFile(archive) as z:
        if z.read("source-sha.txt", pwd=None).decode().strip() != SHA:
            raise ValueError("NATIVE_SOURCE_SHA")
        for case in CASES:
            folder = output / case
            folder.mkdir(mode=0o700)
            for name in (
                "result.json",
                "trace.jsonl",
                "observations.jsonl",
                "fixture.json",
            ):
                member = f"{case}/run/{name}"
                if z.getinfo(member).file_size > 16 * 1024 * 1024:
                    raise ValueError("NATIVE_MEMBER_LIMIT")
                with z.open(member) as source, (folder / name).open("xb") as target:
                    while chunk := source.read(64 * 1024):
                        target.write(chunk)
                (folder / name).chmod(0o600)
            result = json.loads((folder / "result.json").read_text())
            fixture = json.loads((folder / "fixture.json").read_text())
            for name in ("trace.jsonl", "observations.jsonl", "fixture.json"):
                if (
                    hashlib.sha256((folder / name).read_bytes()).hexdigest()
                    != result["artifact_hashes"][name]
                ):
                    raise ValueError("NATIVE_MEMBER_HASH")
            goal = dict(zip(("x", "y", "yaw"), fixture["goal"]))
            manifest = dict(
                schema="robot-scope.run-review-manifest.v1",
                format="d3-native-v1",
                result_file=f"{case}/result.json",
                trace_file=f"{case}/trace.jsonl",
                observations_file=f"{case}/observations.jsonl",
                code_sha=SHA,
                parameters_revision=result["config_sha256"],
                map_id=result["fixture_sha256"][:24],
                map_revision=result["fixture_sha256"],
                goal_id=bytes(result["action"]["goal_uuid"]).hex(),
                goal=goal,
                data_kind="SIMULATION",
                source_id="D3-artifact-12882393645",
                clock_domain="native-sim",
                source_epoch=case,
            )
            (output / f"{case}.manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("archive", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    prepare(a.archive, a.output)
