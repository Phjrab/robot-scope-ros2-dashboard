#!/usr/bin/env python3
"""Build Robot Scope's lightweight Go2 model from Unitree's official URDF/DAE.

The output is a dependency-free JSON asset intended for the Canvas renderer in
``go2_official_model.js``.  DAE scene transforms and URDF link/joint transforms
are preserved.  Meshes are simplified with deterministic vertex clustering so
the browser does not need to download the roughly 26 MB source model.

This script uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET


COLLADA_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
SOURCE_REPOSITORY = "https://github.com/unitreerobotics/unitree_ros"
SOURCE_COMMIT = "f3772ce54c56ef2d34c6aee8100bc768896c7d19"
QUANTIZATION_METERS = 0.00001

# Targets are per unique source mesh.  Mirrored meshes remain separate because
# their official geometry differs.  A complete assembled robot is about 7,000
# triangles after instancing the leg parts four times.
DEFAULT_TARGETS = {
    "base": 1800,
    "hip": 450,
    "thigh": 450,
    "thigh_mirror": 450,
    "calf": 300,
    "calf_mirror": 300,
    "foot": 120,
}


def floats(text: str | None) -> list[float]:
    return [float(value) for value in (text or "").split()]


def ints(text: str | None) -> list[int]:
    return [int(value) for value in (text or "").split()]


def hex_color(values: list[float]) -> str:
    rgb = [max(0, min(255, round(value * 255))) for value in values[:3]]
    return "#" + "".join(f"{value:02x}" for value in rgb)


def transform_point(matrix: list[float], point: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    return (
        matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3],
        matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7],
        matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11],
    )


def collada_material_colors(root: ET.Element) -> dict[str, str]:
    effect_colors: dict[str, str] = {}
    for effect in root.findall(".//c:library_effects/c:effect", COLLADA_NS):
        color = effect.find(".//c:diffuse/c:color", COLLADA_NS)
        rgba = floats(color.text if color is not None else None)
        effect_colors[effect.get("id", "")] = hex_color(rgba or [0.65, 0.68, 0.75])

    result: dict[str, str] = {}
    for material in root.findall(".//c:library_materials/c:material", COLLADA_NS):
        effect = material.find("c:instance_effect", COLLADA_NS)
        effect_id = (effect.get("url", "") if effect is not None else "").lstrip("#")
        result[material.get("id", "")] = effect_colors.get(effect_id, "#aab0c5")
    return result


def collada_positions(mesh: ET.Element) -> dict[str, list[tuple[float, float, float]]]:
    result: dict[str, list[tuple[float, float, float]]] = {}
    for source in mesh.findall("c:source", COLLADA_NS):
        source_id = source.get("id", "")
        array = source.find("c:float_array", COLLADA_NS)
        accessor = source.find("c:technique_common/c:accessor", COLLADA_NS)
        if array is None or accessor is None:
            continue
        values = floats(array.text)
        stride = int(accessor.get("stride", "1"))
        offset = int(accessor.get("offset", "0"))
        count = int(accessor.get("count", str(len(values) // max(stride, 1))))
        params = [param.get("name", "") for param in accessor.findall("c:param", COLLADA_NS)]
        if not {"X", "Y", "Z"}.issubset(params):
            continue
        coordinates = [params.index("X"), params.index("Y"), params.index("Z")]
        result[source_id] = [
            tuple(values[offset + index * stride + coordinate] for coordinate in coordinates)
            for index in range(count)
        ]
    return result


def parse_collada(path: Path) -> tuple[list[tuple[float, float, float]], list[dict[str, object]]]:
    root = ET.parse(path).getroot()
    colors = collada_material_colors(root)
    geometry = root.find(".//c:library_geometries/c:geometry", COLLADA_NS)
    if geometry is None:
        raise ValueError(f"No geometry in {path}")
    mesh = geometry.find("c:mesh", COLLADA_NS)
    if mesh is None:
        raise ValueError(f"No mesh in {path}")

    sources = collada_positions(mesh)
    vertices_sources: dict[str, str] = {}
    for vertices in mesh.findall("c:vertices", COLLADA_NS):
        position = next(
            (item for item in vertices.findall("c:input", COLLADA_NS) if item.get("semantic") == "POSITION"),
            None,
        )
        if position is not None:
            vertices_sources[vertices.get("id", "")] = position.get("source", "").lstrip("#")

    node = root.find(".//c:visual_scene//c:node[c:instance_geometry]", COLLADA_NS)
    matrix_values = floats(node.findtext("c:matrix", default="", namespaces=COLLADA_NS) if node is not None else "")
    matrix = matrix_values if len(matrix_values) == 16 else [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1,
    ]

    canonical_positions: list[tuple[float, float, float]] | None = None
    groups: list[dict[str, object]] = []
    for triangles in mesh.findall("c:triangles", COLLADA_NS):
        inputs = triangles.findall("c:input", COLLADA_NS)
        vertex_input = next((item for item in inputs if item.get("semantic") == "VERTEX"), None)
        if vertex_input is None:
            continue
        vertex_source = vertex_input.get("source", "").lstrip("#")
        position_source = vertices_sources.get(vertex_source)
        positions = sources.get(position_source or "")
        if positions is None:
            raise ValueError(f"Missing POSITION source for {path.name}")
        transformed = [transform_point(matrix, point) for point in positions]
        if canonical_positions is None:
            canonical_positions = transformed
        elif len(canonical_positions) != len(transformed):
            raise ValueError(f"Multiple incompatible position sources in {path.name}")

        stride = max(int(item.get("offset", "0")) for item in inputs) + 1
        vertex_offset = int(vertex_input.get("offset", "0"))
        packed = ints(triangles.findtext("c:p", default="", namespaces=COLLADA_NS))
        position_indices = packed[vertex_offset::stride]
        if len(position_indices) % 3:
            raise ValueError(f"Non-triangular index data in {path.name}")
        material = triangles.get("material", "material")
        groups.append({
            "material": material,
            "color": colors.get(material, "#aab0c5"),
            "triangles": [tuple(position_indices[index:index + 3]) for index in range(0, len(position_indices), 3)],
        })

    if canonical_positions is None:
        raise ValueError(f"No triangles in {path}")
    return canonical_positions, groups


def cluster_mesh(
    positions: list[tuple[float, float, float]],
    groups: list[dict[str, object]],
    cell_size: float,
) -> tuple[list[tuple[float, float, float]], list[dict[str, object]]]:
    minimum = [min(point[axis] for point in positions) for axis in range(3)]
    cluster_lookup: dict[tuple[int, int, int], int] = {}
    sums: list[list[float]] = []
    source_to_cluster = [0] * len(positions)

    for source_index, point in enumerate(positions):
        if cell_size <= 0:
            key = (source_index, 0, 0)
        else:
            key = tuple(round((point[axis] - minimum[axis]) / cell_size) for axis in range(3))
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

    clustered_positions = [
        (value[0] / value[3], value[1] / value[3], value[2] / value[3]) for value in sums
    ]
    simplified_groups: list[dict[str, object]] = []
    used_clusters: set[int] = set()
    for group in groups:
        seen: set[tuple[int, int, int]] = set()
        triangles: list[tuple[int, int, int]] = []
        for source_face in group["triangles"]:  # type: ignore[index]
            face = tuple(source_to_cluster[index] for index in source_face)
            if len(set(face)) < 3:
                continue
            identity = tuple(sorted(face))
            if identity in seen:
                continue
            seen.add(identity)
            triangles.append(face)
            used_clusters.update(face)
        if triangles:
            simplified_groups.append({
                "material": group["material"],
                "color": group["color"],
                "triangles": triangles,
            })

    compact_map = {old: new for new, old in enumerate(sorted(used_clusters))}
    compact_positions = [clustered_positions[old] for old in sorted(used_clusters)]
    for group in simplified_groups:
        group["triangles"] = [
            tuple(compact_map[index] for index in face) for face in group["triangles"]  # type: ignore[index]
        ]
    return compact_positions, simplified_groups


def triangle_count(groups: list[dict[str, object]]) -> int:
    return sum(len(group["triangles"]) for group in groups)  # type: ignore[arg-type]


def simplify_mesh(
    positions: list[tuple[float, float, float]],
    groups: list[dict[str, object]],
    target: int,
) -> tuple[list[tuple[float, float, float]], list[dict[str, object]], float]:
    original_count = triangle_count(groups)
    if original_count <= target:
        compact_positions, compact_groups = cluster_mesh(positions, groups, 0)
        return compact_positions, compact_groups, 0

    bounds = [max(point[axis] for point in positions) - min(point[axis] for point in positions) for axis in range(3)]
    diagonal = math.hypot(*bounds)
    low = 0.0
    high = max(diagonal / 1000, 1e-7)
    high_result = cluster_mesh(positions, groups, high)
    while triangle_count(high_result[1]) > target:
        high *= 1.6
        high_result = cluster_mesh(positions, groups, high)

    best_positions, best_groups = high_result
    best_size = high
    for _ in range(22):
        middle = (low + high) / 2
        candidate_positions, candidate_groups = cluster_mesh(positions, groups, middle)
        count = triangle_count(candidate_groups)
        if count > target:
            low = middle
        else:
            high = middle
            if count >= triangle_count(best_groups):
                best_positions, best_groups, best_size = candidate_positions, candidate_groups, middle
    return best_positions, best_groups, best_size


def origin(element: ET.Element | None) -> dict[str, list[float]]:
    if element is None:
        return {"xyz": [0.0, 0.0, 0.0], "rpy": [0.0, 0.0, 0.0]}
    xyz = floats(element.get("xyz")) or [0.0, 0.0, 0.0]
    rpy = floats(element.get("rpy")) or [0.0, 0.0, 0.0]
    return {"xyz": xyz[:3], "rpy": rpy[:3]}


def parse_urdf(path: Path) -> dict[str, object]:
    robot = ET.parse(path).getroot()
    links: list[dict[str, object]] = []
    visual_link_names: set[str] = set()
    for link in robot.findall("link"):
        visual = link.find("visual")
        mesh = visual.find("geometry/mesh") if visual is not None else None
        if mesh is None:
            continue
        mesh_name = Path(mesh.get("filename", "")).stem
        name = link.get("name", "")
        visual_link_names.add(name)
        links.append({
            "name": name,
            "mesh": mesh_name,
            "visual_origin": origin(visual.find("origin") if visual is not None else None),
        })

    all_joints: list[dict[str, object]] = []
    parent_joint_by_child: dict[str, dict[str, object]] = {}
    for joint in robot.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is None or child is None:
            continue
        limit = joint.find("limit")
        item: dict[str, object] = {
            "name": joint.get("name", ""),
            "type": joint.get("type", "fixed"),
            "parent": parent.get("link", ""),
            "child": child.get("link", ""),
            "origin": origin(joint.find("origin")),
            "axis": floats((joint.find("axis").get("xyz") if joint.find("axis") is not None else None)) or [0.0, 0.0, 0.0],
        }
        if limit is not None:
            item["limit"] = {
                "lower": float(limit.get("lower", "0")),
                "upper": float(limit.get("upper", "0")),
            }
        all_joints.append(item)
        parent_joint_by_child[item["child"]] = item  # type: ignore[index]

    needed_links = set(visual_link_names)
    for visual_name in list(visual_link_names):
        cursor = visual_name
        while cursor in parent_joint_by_child:
            joint = parent_joint_by_child[cursor]
            needed_links.add(joint["parent"])  # type: ignore[arg-type]
            cursor = joint["parent"]  # type: ignore[assignment]

    pending = [joint for joint in all_joints if joint["child"] in needed_links]
    ordered_joints: list[dict[str, object]] = []
    resolved = {"base"}
    while pending:
        ready = [joint for joint in pending if joint["parent"] in resolved]
        if not ready:
            raise ValueError("URDF joint graph is not rooted at base")
        for joint in ready:
            ordered_joints.append(joint)
            resolved.add(joint["child"])  # type: ignore[arg-type]
            pending.remove(joint)

    standard_order = [
        f"{leg}_{joint}_joint"
        for leg in ("FR", "FL", "RR", "RL")
        for joint in ("hip", "thigh", "calf")
    ]
    available = {joint["name"] for joint in ordered_joints if joint["type"] == "revolute"}
    joint_order = [name for name in standard_order if name in available]
    default_positions = {
        name: (0.75 if "thigh" in name else -1.50 if "calf" in name else 0.0)
        for name in joint_order
    }
    return {
        "root": "base",
        "links": links,
        "joints": ordered_joints,
        "joint_order": joint_order,
        "default_joint_positions": default_positions,
    }


def encoded_mesh(
    name: str,
    source_positions: list[tuple[float, float, float]],
    source_groups: list[dict[str, object]],
    target: int,
) -> dict[str, object]:
    positions, groups, cell_size = simplify_mesh(source_positions, source_groups, target)
    flat_vertices = [round(value / QUANTIZATION_METERS) for point in positions for value in point]
    encoded_groups = []
    for group in groups:
        encoded_groups.append({
            "material": group["material"],
            "color": group["color"],
            "indices": [index for face in group["triangles"] for index in face],  # type: ignore[index]
        })
    source_count = triangle_count(source_groups)
    output_count = triangle_count(groups)
    return {
        "name": name,
        "quantization_m": QUANTIZATION_METERS,
        "vertices_q": flat_vertices,
        "groups": encoded_groups,
        "statistics": {
            "source_vertices": len(source_positions),
            "source_triangles": source_count,
            "vertices": len(positions),
            "triangles": output_count,
            "reduction_percent": round((1 - output_count / source_count) * 100, 2),
            "cluster_cell_m": round(cell_size, 8),
        },
    }


def build(source: Path, output: Path, targets: dict[str, int]) -> dict[str, object]:
    urdf_path = source / "urdf" / "go2_description.urdf"
    dae_dir = source / "dae"
    if not urdf_path.is_file() or not dae_dir.is_dir():
        raise FileNotFoundError("Source must contain urdf/go2_description.urdf and dae/*.dae")

    meshes: dict[str, object] = {}
    for name, target in targets.items():
        dae_path = dae_dir / f"{name}.dae"
        positions, groups = parse_collada(dae_path)
        meshes[name] = encoded_mesh(name, positions, groups, target)
        stats = meshes[name]["statistics"]  # type: ignore[index]
        print(
            f"{name:13s} {stats['source_triangles']:7d} -> {stats['triangles']:5d} triangles, "
            f"{stats['vertices']:5d} vertices"
        )

    skeleton = parse_urdf(urdf_path)
    source_triangles = sum(mesh["statistics"]["source_triangles"] for mesh in meshes.values())  # type: ignore[index]
    asset_triangles = sum(mesh["statistics"]["triangles"] for mesh in meshes.values())  # type: ignore[index]
    link_meshes = {link["mesh"] for link in skeleton["links"]}  # type: ignore[index]
    assembled_triangles = sum(
        meshes[link["mesh"]]["statistics"]["triangles"]  # type: ignore[index]
        for link in skeleton["links"]  # type: ignore[index]
        if link["mesh"] in link_meshes  # type: ignore[index]
    )
    source_assembled_triangles = sum(
        meshes[link["mesh"]]["statistics"]["source_triangles"]  # type: ignore[index]
        for link in skeleton["links"]  # type: ignore[index]
        if link["mesh"] in link_meshes  # type: ignore[index]
    )
    asset = {
        "schema": "robot-scope.go2-official-lite",
        "version": 1,
        "units": "meter",
        "up_axis": "Z",
        "source": {
            "project": "Unitree Robotics unitree_ros / go2_description",
            "repository": SOURCE_REPOSITORY,
            "commit": SOURCE_COMMIT,
            "package": "go2_description",
            "license": "BSD-3-Clause",
            "license_file": "/static/assets/go2/LICENSE.txt",
            "files": ["urdf/go2_description.urdf"] + [f"dae/{name}.dae" for name in targets],
            "modifications": "DAE transforms applied; meshes simplified by deterministic vertex clustering; positions quantized to 0.01 mm; textures omitted.",
        },
        "model": {
            "name": "Unitree Go2",
            "base_height_m": 0.32,
            "approximate_size_m": [0.80, 0.40, 0.55],
            "source_unique_triangles": source_triangles,
            "source_assembled_triangles": source_assembled_triangles,
            "asset_unique_triangles": asset_triangles,
            "assembled_triangles": assembled_triangles,
        },
        "skeleton": skeleton,
        "meshes": meshes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asset, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return asset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Directory containing dae/ and urdf/")
    parser.add_argument("output", type=Path, help="Output JSON asset")
    args = parser.parse_args()
    asset = build(args.source, args.output, DEFAULT_TARGETS)
    print(
        f"wrote {args.output} ({args.output.stat().st_size:,} bytes, "
        f"{asset['model']['assembled_triangles']:,} assembled triangles)"
    )


if __name__ == "__main__":
    main()
