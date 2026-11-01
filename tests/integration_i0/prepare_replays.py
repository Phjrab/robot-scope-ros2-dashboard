"""Generate private replay inputs with installed real producers and parsers."""
import argparse
import json
from pathlib import Path

from tests.expansion_c6.fixtures import goal_fixture, scene_fixture
from robot_dashboard.expansion_contracts import ScenePacket
from robot_dashboard.run_review.io import write_new
from robot_dashboard.run_review.review import load_run


def prepare(root):
    root.mkdir(mode=0o700)
    manifests = [goal_fixture(root), goal_fixture(root, "heading", yaw=0.5),
                 goal_fixture(root, "cancel", state="canceled"),
                 scene_fixture(root, ScenePacket.from_dict)]
    lock = json.loads((Path(__file__).parents[2] / "docs/integration/i0/SOURCE_LOCK.json").read_text())
    for i, manifest in enumerate(manifests):
        manifest["code_sha"] = lock["baseline"]["sha"] if i < 3 else lock["roles"]["C1"]["sha"]
        write_new(root / f"manifest-{i}.json", manifest)
        write_new(root / f"review-{i}.json", load_run(root, manifest, validator=ScenePacket.from_dict))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    prepare(parser.parse_args().output)
