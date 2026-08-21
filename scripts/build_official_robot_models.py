#!/usr/bin/env python3
"""Build browser-ready models from a pinned official TurtleBot3 URDF.

The source URDF and every STL referenced by its visual geometry are committed
under ``robot_dashboard/static/assets`` unchanged.  This builder converts those
large assets into the compact triangle/skeleton JSON consumed by Robot Scope's
dependency-free Canvas renderer.  It uses only the Python standard library and
produces deterministic output.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "robot_dashboard" / "static"
ASSET_ROOT = STATIC_ROOT / "assets"
QUANTIZATION_METERS = 0.00001
SCHEMA = "robot-scope.robot-model-lite"
IDENTITY_ORIGIN = {"xyz": [0.0, 0.0, 0.0], "rpy": [0.0, 0.0, 0.0]}


@dataclass(frozen=True)
class ModelSpec:
    robot_type: str
    name: str
    display_name: str
    source_project: str
    repository: str
    commit: str
    license_file: str
    manifest: Path
    urdf: Path
    package_root: Path
    output: Path
    approximate_size_m: tuple[float, float, float]
    base_height_m: float
    targets: dict[str, int]
    default_joint_positions: dict[str, float]


MODEL_SPECS = {
    "turtlebot": ModelSpec(
        robot_type="turtlebot",
        name="ROBOTIS TurtleBot3 Burger",
        display_name="TurtleBot3 Burger",
        source_project="ROBOTIS turtlebot3 / turtlebot3_description",
        repository="https://github.com/ROBOTIS-GIT/turtlebot3",
        commit="90a68bd2e3c61c12966779da89d8eeaec82730e9",
        license_file="/static/assets/turtlebot/LICENSE.txt",
        manifest=ASSET_ROOT / "turtlebot/upstream-manifest.json",
        urdf=ASSET_ROOT / "turtlebot/source/turtlebot3_description/urdf/turtlebot3_burger.urdf",
        package_root=ASSET_ROOT / "turtlebot/source/turtlebot3_description",
        output=ASSET_ROOT / "turtlebot/turtlebot3-burger-official-lite.json",
        approximate_size_m=(0.178, 0.178, 0.192),
        base_height_m=0.0,
        targets={
            "burger_base": 1_800,
            "left_tire": 450,
            "right_tire": 450,
            "lds": 700,
        },
        default_joint_positions={},
    ),
}


def floats(text: str | None) -> list[float]:
    return [float(value) for value in (text or "").split()]


def vector(text: str | None, default: tuple[float, float, float]) -> list[float]:
    values = floats(text)
    return values[:3] if len(values) >= 3 else list(default)


def clean_name(value: str | None) -> str:
    """Expand the empty namespace used by ROBOTIS' xacro-compatible URDF."""

    return str(value or "").replace("${namespace}", "")


def origin(element: ET.Element | None) -> dict[str, list[float]]:
    if element is None:
        return {key: list(value) for key, value in IDENTITY_ORIGIN.items()}
    return {
        "xyz": vector(element.get("xyz"), (0.0, 0.0, 0.0)),
        "rpy": vector(element.get("rpy"), (0.0, 0.0, 0.0)),
    }


def material_colors(robot: ET.Element) -> dict[str, str]:
    colors: dict[str, str] = {}
    for material in robot.findall("material"):
        color = material.find("color")
        rgba = floats(color.get("rgba") if color is not None else None)
        if len(rgba) < 3:
            continue
        colors[material.get("name", "material")] = "#" + "".join(
            f"{max(0, min(255, round(channel * 255))):02x}" for channel in rgba[:3]
        )
    return colors


def visual_material(visual: ET.Element, colors: dict[str, str]) -> tuple[str, str]:
    material = visual.find("material")
    name = material.get("name", "material") if material is not None else "material"
    direct = material.find("color") if material is not None else None
    rgba = floats(direct.get("rgba") if direct is not None else None)
    if len(rgba) >= 3:
        color = "#" + "".join(
            f"{max(0, min(255, round(channel * 255))):02x}" for channel in rgba[:3]
        )
    else:
        color = colors.get(name, "#aab0c5")
    return name, color


def resolve_mesh(spec: ModelSpec, filename: str) -> Path:
    package_prefix = "package://"
    if filename.startswith(package_prefix):
        relative = filename[len(package_prefix):]
        package, separator, remainder = relative.partition("/")
        if not separator or package != spec.package_root.name:
            raise ValueError(f"Unsupported package mesh URI: {filename}")
        path = spec.package_root / remainder
    else:
        path = spec.urdf.parent / filename
    resolved = path.resolve()
    package_root = spec.package_root.resolve()
    if package_root not in resolved.parents:
        raise ValueError(f"Mesh escapes the official source directory: {filename}")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def validate_manifest(spec: ModelSpec) -> dict[str, str]:
    manifest = json.loads(spec.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != "robot-scope.upstream-asset-manifest":
        raise ValueError(f"Unsupported upstream manifest: {spec.manifest}")
    if manifest.get("repository") != spec.repository or manifest.get("commit") != spec.commit:
        raise ValueError(f"Upstream manifest provenance does not match {spec.robot_type}")
    if manifest.get("license") != "Apache-2.0":
        raise ValueError(f"Unexpected upstream license for {spec.robot_type}")

    asset_directory = spec.manifest.parent.resolve()
    verified: dict[str, str] = {}
    for relative, expected in manifest.get("files", {}).items():
        path = (asset_directory / relative).resolve()
        if path != asset_directory and asset_directory not in path.parents:
            raise ValueError(f"Manifest path escapes its asset directory: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Pinned upstream checksum mismatch: {relative}")
        verified[relative] = actual
    if not verified:
        raise ValueError(f"Upstream manifest is empty: {spec.manifest}")
    return verified


def parse_binary_stl(
    path: Path,
    scale: tuple[float, float, float],
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"STL is too short: {path}")
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    if 84 + triangle_count * 50 != len(data):
        raise ValueError(f"Only deterministic binary STL input is supported: {path}")

    positions: list[tuple[float, float, float]] = []
    position_index: dict[tuple[float, float, float], int] = {}
    triangles: list[tuple[int, int, int]] = []
    for triangle in range(triangle_count):
        offset = 84 + triangle * 50 + 12
        values = struct.unpack_from("<9f", data, offset)
        face: list[int] = []
        for vertex in range(3):
            point = tuple(values[vertex * 3 + axis] * scale[axis] for axis in range(3))
            index = position_index.get(point)
            if index is None:
                index = len(positions)
                position_index[point] = index
                positions.append(point)
            face.append(index)
        if len(set(face)) == 3:
            triangles.append((face[0], face[1], face[2]))
    return positions, triangles


def cluster_mesh(
    positions: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
    cell_size: float,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    minimum = [min(point[axis] for point in positions) for axis in range(3)]
    cluster_lookup: dict[tuple[int, int, int], int] = {}
    sums: list[list[float]] = []
    source_to_cluster = [0] * len(positions)
    for source_index, point in enumerate(positions):
        key = (
            (source_index, 0, 0)
            if cell_size <= 0
            else tuple(round((point[axis] - minimum[axis]) / cell_size) for axis in range(3))
        )
        cluster = cluster_lookup.get(key)
        if cluster is None:
            cluster = len(sums)
            cluster_lookup[key] = cluster
            sums.append([point[0], point[1], point[2], 1.0])
        else:
            sums[cluster][0] += point[0]
            sums[cluster][1] += point[1]
            sums[cluster][2] += point[2]
            sums[cluster][3] += 1.0
        source_to_cluster[source_index] = cluster

    clustered = [
        (value[0] / value[3], value[1] / value[3], value[2] / value[3])
        for value in sums
    ]
    faces: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    used: set[int] = set()
    for source_face in triangles:
        face = tuple(source_to_cluster[index] for index in source_face)
        if len(set(face)) < 3:
            continue
        identity = tuple(sorted(face))
        if identity in seen:
            continue
        seen.add(identity)
        faces.append(face)
        used.update(face)

    compact_map = {old: new for new, old in enumerate(sorted(used))}
    compact_positions = [clustered[old] for old in sorted(used)]
    compact_faces = [tuple(compact_map[index] for index in face) for face in faces]
    return compact_positions, compact_faces


def simplify_mesh(
    positions: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
    target: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], float]:
    if len(triangles) <= target:
        compact_positions, compact_faces = cluster_mesh(positions, triangles, 0.0)
        return compact_positions, compact_faces, 0.0

    bounds = [
        max(point[axis] for point in positions) - min(point[axis] for point in positions)
        for axis in range(3)
    ]
    diagonal = math.hypot(*bounds)
    low = 0.0
    high = max(diagonal / 1_000, 1e-7)
    high_result = cluster_mesh(positions, triangles, high)
    while len(high_result[1]) > target:
        high *= 1.6
        high_result = cluster_mesh(positions, triangles, high)

    best_positions, best_faces = high_result
    best_size = high
    for _ in range(22):
        middle = (low + high) / 2
        candidate_positions, candidate_faces = cluster_mesh(positions, triangles, middle)
        if len(candidate_faces) > target:
            low = middle
        else:
            high = middle
            if len(candidate_faces) >= len(best_faces):
                best_positions, best_faces, best_size = (
                    candidate_positions,
                    candidate_faces,
                    middle,
                )
    return best_positions, best_faces, best_size


def encode_mesh(
    name: str,
    source_positions: list[tuple[float, float, float]],
    source_triangles: list[tuple[int, int, int]],
    target: int,
    material: str,
    color: str,
) -> dict[str, object]:
    positions, triangles, cell_size = simplify_mesh(source_positions, source_triangles, target)
    return {
        "name": name,
        "quantization_m": QUANTIZATION_METERS,
        "vertices_q": [
            round(value / QUANTIZATION_METERS) for point in positions for value in point
        ],
        "groups": [{
            "material": material,
            "color": color,
            "indices": [index for face in triangles for index in face],
        }],
        "statistics": {
            "source_vertices": len(source_positions),
            "source_triangles": len(source_triangles),
            "vertices": len(positions),
            "triangles": len(triangles),
            "reduction_percent": round((1 - len(triangles) / len(source_triangles)) * 100, 2),
            "cluster_cell_m": round(cell_size, 8),
        },
    }


def ordered_joints(root_name: str, joints: list[dict[str, object]]) -> list[dict[str, object]]:
    pending = list(joints)
    ordered: list[dict[str, object]] = []
    resolved = {root_name}
    while pending:
        ready = [joint for joint in pending if joint["parent"] in resolved]
        if not ready:
            names = ", ".join(str(joint["name"]) for joint in pending)
            raise ValueError(f"URDF joint graph is disconnected or cyclic: {names}")
        for joint in ready:
            ordered.append(joint)
            resolved.add(str(joint["child"]))
            pending.remove(joint)
    return ordered


def build(spec: ModelSpec) -> dict[str, object]:
    verified_hashes = validate_manifest(spec)
    robot = ET.parse(spec.urdf).getroot()
    if robot.tag != "robot":
        raise ValueError(f"{spec.urdf} is not a URDF robot document")
    colors = material_colors(robot)

    link_names = {clean_name(link.get("name")) for link in robot.findall("link")}
    raw_joints: list[dict[str, object]] = []
    for joint in robot.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is None or child is None:
            raise ValueError(f"Joint {joint.get('name', '')!r} is missing parent or child")
        item: dict[str, object] = {
            "name": clean_name(joint.get("name")),
            "type": joint.get("type", "fixed"),
            "parent": clean_name(parent.get("link")),
            "child": clean_name(child.get("link")),
            "origin": origin(joint.find("origin")),
            "axis": vector(
                joint.find("axis").get("xyz") if joint.find("axis") is not None else None,
                (0.0, 0.0, 0.0),
            ),
        }
        limit = joint.find("limit")
        if limit is not None and item["type"] == "revolute":
            item["limit"] = {
                "lower": float(limit.get("lower", "0")),
                "upper": float(limit.get("upper", "0")),
            }
        raw_joints.append(item)

    child_names = {str(joint["child"]) for joint in raw_joints}
    roots = sorted(link_names - child_names)
    if len(roots) != 1:
        raise ValueError(f"URDF must contain exactly one root link, found {roots}")
    root_name = roots[0]
    joints = ordered_joints(root_name, raw_joints)

    mesh_specs: dict[
        tuple[Path, tuple[float, float, float], str, str],
        str,
    ] = {}
    links: list[dict[str, object]] = []
    for link in robot.findall("link"):
        link_name = clean_name(link.get("name"))
        for visual in link.findall("visual"):
            mesh = visual.find("geometry/mesh")
            if mesh is None:
                continue
            filename = mesh.get("filename", "")
            path = resolve_mesh(spec, filename)
            scale_values = vector(mesh.get("scale"), (1.0, 1.0, 1.0))
            scale = (scale_values[0], scale_values[1], scale_values[2])
            material, color = visual_material(visual, colors)
            signature = (path, scale, material, color)
            mesh_name = mesh_specs.get(signature)
            if mesh_name is None:
                mesh_name = path.stem
                if mesh_name in mesh_specs.values():
                    raise ValueError(f"Ambiguous official mesh name: {mesh_name}")
                mesh_specs[signature] = mesh_name
            links.append({
                "name": link_name,
                "mesh": mesh_name,
                "visual_origin": origin(visual.find("origin")),
            })

    meshes: dict[str, object] = {}
    source_files = [spec.urdf]
    for (path, scale, material, color), mesh_name in mesh_specs.items():
        positions, triangles = parse_binary_stl(path, scale)
        target = spec.targets.get(mesh_name)
        if target is None:
            raise ValueError(f"No triangle target configured for official mesh {mesh_name}")
        meshes[mesh_name] = encode_mesh(
            mesh_name,
            positions,
            triangles,
            target,
            material,
            color,
        )
        source_files.append(path)
        statistics = meshes[mesh_name]["statistics"]  # type: ignore[index]
        print(
            f"{spec.robot_type:10s} {mesh_name:38s} "
            f"{statistics['source_triangles']:7d} -> {statistics['triangles']:5d} triangles"
        )

    movable_names = [
        str(joint["name"])
        for joint in joints
        if joint["type"] in {"revolute", "continuous"}
    ]
    default_positions = {
        name: float(spec.default_joint_positions.get(name, 0.0)) for name in movable_names
    }
    source_unique_triangles = sum(
        mesh["statistics"]["source_triangles"] for mesh in meshes.values()  # type: ignore[index]
    )
    asset_unique_triangles = sum(
        mesh["statistics"]["triangles"] for mesh in meshes.values()  # type: ignore[index]
    )
    source_assembled_triangles = sum(
        meshes[link["mesh"]]["statistics"]["source_triangles"] for link in links  # type: ignore[index]
    )
    assembled_triangles = sum(
        meshes[link["mesh"]]["statistics"]["triangles"] for link in links  # type: ignore[index]
    )

    manifest_root = spec.manifest.parent.resolve()
    required_manifest_files = {
        path.resolve().relative_to(manifest_root).as_posix() for path in source_files
    }
    unverified = sorted(required_manifest_files - set(verified_hashes))
    if unverified:
        raise ValueError(f"Official visual source is missing from the pinned manifest: {unverified}")

    relative_urdf = spec.urdf.relative_to(STATIC_ROOT)
    relative_files = sorted(
        path.relative_to(STATIC_ROOT).as_posix() for path in set(source_files)
    )
    asset = {
        "schema": SCHEMA,
        "version": 1,
        "units": "meter",
        "up_axis": "Z",
        "source": {
            "project": spec.source_project,
            "repository": spec.repository,
            "commit": spec.commit,
            "license": "Apache-2.0",
            "license_file": spec.license_file,
            "fidelity": "official-derived",
            "urdf_path": f"/static/{relative_urdf.as_posix()}",
            "files": relative_files,
            "sha256": verified_hashes,
            "generated_by": "scripts/build_official_robot_models.py",
            "modifications": (
                "URDF mesh scales applied and xacro-compatible empty namespace tokens expanded "
                "when present; official binary STL meshes simplified by deterministic vertex "
                "clustering; positions quantized to 0.01 mm for browser rendering. The "
                "committed source URDF and visual STL files are byte-for-byte upstream copies."
            ),
        },
        "model": {
            "robot_type": spec.robot_type,
            "name": spec.name,
            "display_name": spec.display_name,
            "base_height_m": spec.base_height_m,
            "approximate_size_m": list(spec.approximate_size_m),
            "fidelity": "official-derived",
            "notice": (
                "Dashboard visualization derived from the pinned official URDF and visual "
                "meshes; the lightweight derivative is not for collision checking, motion "
                "planning, control, simulation validation, or fabrication."
            ),
            "source_unique_triangles": source_unique_triangles,
            "source_assembled_triangles": source_assembled_triangles,
            "asset_unique_triangles": asset_unique_triangles,
            "assembled_triangles": assembled_triangles,
        },
        "skeleton": {
            "root": root_name,
            "links": links,
            "joints": joints,
            "joint_order": movable_names,
            "default_joint_positions": default_positions,
        },
        "meshes": meshes,
    }
    spec.output.parent.mkdir(parents=True, exist_ok=True)
    spec.output.write_text(
        json.dumps(asset, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return asset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "models",
        nargs="*",
        choices=tuple(MODEL_SPECS),
        help="Model(s) to build; defaults to every pinned official model",
    )
    args = parser.parse_args()
    selected = args.models or list(MODEL_SPECS)
    for key in selected:
        spec = MODEL_SPECS[key]
        asset = build(spec)
        print(
            f"wrote {spec.output} ({spec.output.stat().st_size:,} bytes, "
            f"{asset['model']['assembled_triangles']:,} assembled triangles)"
        )


if __name__ == "__main__":
    main()
