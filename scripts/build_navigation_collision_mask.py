#!/usr/bin/env python3
"""Export an exact-pinned geometry-only collision mask to a new private directory."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot_dashboard.navigation_collision_mask import (
    CollisionMaskError,
    FAMILY_KEYS,
    build_collision_mask,
    write_collision_mask,
)
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapError


def export_mask(root: Path, destination: Path, family: dict[str, str], annotation_revision: str) -> str:
    if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
        raise CollisionMaskError("source root must be a real absolute directory")
    if destination == root or root in destination.parents or destination in root.parents:
        raise CollisionMaskError("artifact destination must be separate from the source map root")
    # The catalog requires managed_roots for these read APIs. No catalog mutation
    # method is called; re-read pins and geometry before publishing the derivative.
    catalog = SavedMapCatalog([root], managed_roots=[root])
    map_id, revision = family["occupancy_map_id"], family["occupancy_revision"]
    source = catalog.resolve_navigation_map(map_id, revision)
    geometry = catalog.route_geometry(map_id, revision)
    annotations = catalog.annotations(map_id)
    lineage = source.family
    if lineage is None:
        raise CollisionMaskError("source map family is unavailable")
    pcd = catalog.metadata(family["pcd_map_id"])
    if pcd["kind"] != "pointcloud3d" or pcd["revision"] != family["pcd_revision"]:
        raise CollisionMaskError("source PCD pin mismatch")
    occupancy = lineage["occupancy"]
    if (occupancy["width"], occupancy["height"], occupancy["resolution"],
            tuple(occupancy["origin"]), occupancy["frame_id"]) != (
            geometry.width, geometry.height, geometry.resolution, geometry.origin, geometry.frame_id):
        raise CollisionMaskError("family geometry differs from the source grid")
    bound_geometry = replace(
        geometry, family_id=lineage["family_id"], family_revision=lineage["family_revision"],
        source_pcd_id=lineage["source"]["pcd_map_id"],
        source_pcd_revision=lineage["source"]["pcd_revision"],
        occupancy_map_id=occupancy["map_id"], occupancy_map_revision=occupancy["map_revision"],
    )
    artifact = build_collision_mask(bound_geometry, annotations, expected_family=family,
                                    expected_annotation_revision=annotation_revision)
    if (catalog.resolve_navigation_map(map_id, revision) != source
            or catalog.route_geometry(map_id, revision) != geometry
            or catalog.annotations(map_id)["annotation_revision"] != annotation_revision
            or catalog.metadata(family["pcd_map_id"])["revision"] != family["pcd_revision"]):
        raise CollisionMaskError("source changed while building the artifact")
    write_collision_mask(artifact, destination)
    return artifact.digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    for key in sorted(FAMILY_KEYS):
        parser.add_argument("--" + key.replace("_", "-"), required=True)
    parser.add_argument("--annotation-revision", required=True)
    args = parser.parse_args(argv)
    family = {key: getattr(args, key) for key in FAMILY_KEYS}
    try:
        digest = export_mask(args.maps_root, args.output, family, args.annotation_revision)
    except (CollisionMaskError, SavedMapError, OSError) as exc:
        print(json.dumps({"status": "FAIL", "reason": type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "EXPORTED", "artifact_digest": digest,
                      "runtime_policy_enforced": False, "footprint_expansion": "none"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
