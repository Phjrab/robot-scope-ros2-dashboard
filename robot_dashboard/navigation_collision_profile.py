"""Verified immutable mask inputs and an explicit opt-in Humble profile.

This supplies native consumers; publication/configuration never attest ingestion
or enforcement. The installed default navigation configuration is not changed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path

from .navigation_collision_mask import (
    CollisionMaskArtifact, CollisionMaskError, FAMILY_KEYS, MAX_CELLS,
    build_collision_mask,
)
from .saved_maps import NavigationMapSnapshot

PROFILE = "robot-scope.humble-solid-mask-circle.v1"
BINDING_SCHEMA = "robot-scope.collision-mask-source.v1"
MASK_TOPIC = "/robot_scope/navigation/collision_mask"
BINDING_TOPIC = "/robot_scope/navigation/collision_mask_binding"
PUBLISHER_NAME = "robot_scope_collision_mask"
MAX_BINDING_BYTES = 4096
MASK_TTL_S = 0.75
PAYLOAD_NAMES = ("source.occupancy.bin", "mask.occupancy.bin", "mask.pgm",
                 "mask.yaml", "annotations.json", "manifest.json")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CollisionMaskError("duplicate JSON key")
        result[key] = value
    return result


def _json(payload):
    return json.loads(payload, object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(CollisionMaskError("nonfinite JSON")))


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def load_collision_mask(directory: Path, *, expected_digest: str) -> CollisionMaskArtifact:
    """Read bounded regular files without symlinks and rebuild their semantics.

    An expected digest is mandatory. File permissions alone are not trusted.
    Validation uses the exact bytes read, not a later reopening of mutable paths.
    """
    try:
        directory = Path(directory)
        if (not _hash(expected_digest) or not directory.is_absolute()
                or directory.resolve(strict=True) != directory):
            raise CollisionMaskError("real artifact directory and exact digest required")
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            payloads = {}
            for name in PAYLOAD_NAMES:
                limit = 65536 if name == "manifest.json" else 4 * MAX_CELLS
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                with os.fdopen(fd, "rb") as source:
                    info = os.fstat(source.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                        raise CollisionMaskError("artifact file is not bounded regular data")
                    value = source.read(limit + 1)
                    if len(value) > limit:
                        raise CollisionMaskError("artifact payload exceeds bound")
                    payloads[name] = value
        finally:
            os.close(descriptor)
        manifest = _json(payloads["manifest.json"])
        if not isinstance(manifest, dict) or manifest.get("artifact_digest") != expected_digest:
            raise CollisionMaskError("artifact digest pin mismatch")
        geometry, family = manifest["geometry"], manifest["map_family"]
        width, height = geometry["width"], geometry["height"]
        resolution, origin = geometry["resolution"], geometry["origin"]
        if (type(width) is not int or type(height) is not int or min(width, height) < 1
                or width * height > MAX_CELLS
                or type(resolution) not in (int, float) or not math.isfinite(resolution) or resolution <= 0
                or not isinstance(origin, list) or len(origin) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in origin)
                or len(payloads["source.occupancy.bin"]) != width * height):
            raise CollisionMaskError("artifact geometry is invalid")
        grid = NavigationMapSnapshot(
            map_id=family["occupancy_map_id"], revision=family["occupancy_revision"],
            name="collision artifact", frame_id=geometry["frame_id"],
            yaml_path=Path("mask.yaml"), image_path=Path("mask.pgm"),
            width=width, height=height, resolution=resolution, origin=tuple(origin),
            occupancy=payloads["source.occupancy.bin"],
            family_id=family["family_id"], family_revision=family["family_revision"],
            source_pcd_id=family["pcd_map_id"], source_pcd_revision=family["pcd_revision"],
            occupancy_map_id=family["occupancy_map_id"], occupancy_map_revision=family["occupancy_revision"],
        )
        artifact = build_collision_mask(grid, _json(payloads["annotations.json"]),
            expected_family=family, expected_annotation_revision=manifest["annotation_revision"])
        if artifact.digest != expected_digest or any(payloads[name] != data for name, data in artifact.files()):
            raise CollisionMaskError("artifact bytes or reconstructed semantics differ")
        return artifact
    except CollisionMaskError:
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        raise CollisionMaskError("collision artifact validation failed") from exc


def mask_binding(artifact: CollisionMaskArtifact, *, incarnation: str, sequence: int) -> dict:
    manifest = _json(artifact.manifest)
    return {
        "schema": BINDING_SCHEMA, "artifact_digest": artifact.digest,
        "map_family": manifest["map_family"], "annotation_revision": manifest["annotation_revision"],
        "mask_sha256": hashlib.sha256(artifact.mask).hexdigest(),
        "frame_id": manifest["geometry"]["frame_id"], "topic": MASK_TOPIC,
        "incarnation": incarnation, "sequence": sequence,
        "evidence_kind": "publication_only", "runtime_policy_enforced": False,
    }


def parse_mask_binding(payload: str) -> dict:
    """Strict bounded publication identity. No remote enforcement claim survives."""
    try:
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_BINDING_BYTES:
            raise CollisionMaskError("mask binding exceeds bound")
        value = _json(payload)
        keys = {"schema", "artifact_digest", "map_family", "annotation_revision", "mask_sha256",
                "frame_id", "topic", "incarnation", "sequence", "evidence_kind", "runtime_policy_enforced"}
        if (not isinstance(value, dict) or set(value) != keys or value["schema"] != BINDING_SCHEMA
                or value["topic"] != MASK_TOPIC or value["evidence_kind"] != "publication_only"
                or value["runtime_policy_enforced"] is not False
                or not all(_hash(value[key]) for key in ("artifact_digest", "annotation_revision", "mask_sha256"))
                or not isinstance(value["incarnation"], str)
                or re.fullmatch(r"[0-9a-f]{32}", value["incarnation"]) is None
                or type(value["sequence"]) is not int or not 1 <= value["sequence"] <= 2**63 - 1
                or not isinstance(value["frame_id"], str) or not value["frame_id"]
                or len(value["frame_id"]) > 128 or any(ord(c) < 32 for c in value["frame_id"])):
            raise CollisionMaskError("mask binding is invalid")
        family = value["map_family"]
        if not isinstance(family, dict) or set(family) != FAMILY_KEYS:
            raise CollisionMaskError("mask family is incomplete")
        for key, pin in family.items():
            size = 24 if key.endswith("_id") else 64
            if not isinstance(pin, str) or re.fullmatch(r"[0-9a-f]{%d}" % size, pin) is None:
                raise CollisionMaskError("mask family pin is invalid")
        return value
    except CollisionMaskError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise CollisionMaskError("mask binding is invalid") from exc


def make_collision_profile(base: dict, artifact: CollisionMaskArtifact, *, robot_radius_m: float,
                           footprint_padding_m: float, bt_xml_path: Path) -> dict:
    """Return a separate profile, requiring explicit effective circle dimensions.

    Native StaticLayer uses an axis-aligned costmap. Rotated source grids remain
    valid offline artifacts but cannot silently enter this native profile.
    """
    if (type(robot_radius_m) not in (int, float) or not 0 < robot_radius_m <= 2
            or not math.isfinite(robot_radius_m) or type(footprint_padding_m) not in (int, float)
            or not 0 <= footprint_padding_m <= 1 or not math.isfinite(footprint_padding_m)):
        raise CollisionMaskError("explicit circle radius and padding required")
    manifest = _json(artifact.manifest)
    geometry = manifest["geometry"]
    if geometry["origin"][2] != 0 or geometry["frame_id"] != "map":
        raise CollisionMaskError("native profile requires an axis-aligned map frame")
    expected_bt = Path(__file__).resolve().parents[1] / "config" / "robot_scope_collision_replan.xml"
    if Path(bt_xml_path).resolve(strict=True) != expected_bt:
        raise CollisionMaskError("only the shipped collision replanning tree is supported")
    bt = expected_bt.read_bytes()
    result = copy.deepcopy(base)
    try:
        planner = result["planner_server"]["ros__parameters"]
        if planner.get("planner_plugins") != ["GridBased"] or planner["GridBased"]["plugin"] != "nav2_navfn_planner/NavfnPlanner":
            raise CollisionMaskError("unsupported planner profile")
        planner["GridBased"].update(allow_unknown=False, tolerance=0.0)
        controller = result["controller_server"]["ros__parameters"]
        if controller.get("controller_plugins") != ["FollowPath"]:
            raise CollisionMaskError("unsupported controller profile")
        follow = controller["FollowPath"]
        for name in ("primary_controller", "angular_dist_threshold", "forward_sampling_distance",
                     "rotate_to_heading_angular_vel", "max_angular_accel", "simulate_ahead_time",
                     "rotate_to_goal_heading", "closed_loop"):
            follow.pop(name, None)
        follow.update(plugin="nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController",
                      use_collision_detection=True, max_allowed_time_to_collision_up_to_carrot=1.0)
        for name, frame in (("global_costmap", "map"), ("local_costmap", "odom")):
            params = result[name][name]["ros__parameters"]
            if params.get("global_frame") != frame or params.get("robot_base_frame") != "base_link":
                raise CollisionMaskError("unsupported native costmap frames")
            if params.get("footprint", "[]") not in ("", "[]"):
                raise CollisionMaskError("polygon footprint requires another qualified profile")
            plugins = params["plugins"]
            if plugins not in (["static_layer", "obstacle_layer", "inflation_layer"],
                               ["obstacle_layer", "inflation_layer"]):
                raise CollisionMaskError("unsupported native costmap plugins")
            if params.get("filters", []) or any(params[layer].get("plugin") != expected for layer, expected in (
                    ("obstacle_layer", "nav2_costmap_2d::ObstacleLayer"),
                    ("inflation_layer", "nav2_costmap_2d::InflationLayer"))):
                raise CollisionMaskError("unsupported native collision layers")
            params.update(robot_radius=float(robot_radius_m), footprint_padding=float(footprint_padding_m),
                          footprint="[]", track_unknown_space=True, always_send_full_costmap=True,
                          use_maximum=True, unknown_cost_value=255, lethal_cost_threshold=100,
                          trinary_costmap=True)
            params["plugins"] = plugins[:-1] + ["policy_layer", "inflation_layer"]
            params["policy_layer"] = {
                "plugin": "nav2_costmap_2d::StaticLayer", "enabled": True,
                "map_topic": MASK_TOPIC, "map_subscribe_transient_local": True,
                "subscribe_to_updates": False, "footprint_clearing_enabled": False,
            }
            params["inflation_layer"]["inflation_radius"] = max(
                float(params["inflation_layer"]["inflation_radius"]),
                float(robot_radius_m + footprint_padding_m) + float(params["resolution"]),
            )
        bt_params = result["bt_navigator"]["ros__parameters"]
        if bt_params.get("global_frame") != "map" or bt_params.get("robot_base_frame") != "base_link":
            raise CollisionMaskError("unsupported navigator frames")
        bt_params["default_nav_to_pose_bt_xml"] = str(expected_bt)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, CollisionMaskError):
            raise
        raise CollisionMaskError("unsupported base navigation parameters") from exc
    binding = {"schema": PROFILE, "artifact_digest": artifact.digest,
               "map_family": manifest["map_family"], "annotation_revision": manifest["annotation_revision"],
               "mask_topic": MASK_TOPIC, "robot_radius_m": float(robot_radius_m),
               "footprint_padding_m": float(footprint_padding_m),
               "bt_sha256": hashlib.sha256(bt).hexdigest(),
               "parameters_sha256": hashlib.sha256(_canonical(result)).hexdigest(),
               "runtime_policy_enforced": False, "native_ingestion_evidence": "not_provided"}
    binding["profile_digest"] = hashlib.sha256(_canonical(binding)).hexdigest()
    return {"parameters": result, "manifest": binding}
