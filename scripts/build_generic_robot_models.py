#!/usr/bin/env python3
"""Build dependency-free dashboard meshes from Robot Scope primitive URDFs.

The generic TurtleBot-class and SO-101-class models in ``static/assets`` are
authored in this repository using only URDF box, cylinder, and sphere
primitives.  This builder converts those primitives into the same compact
triangle/skeleton layout used by the Canvas robot renderer.  It deliberately
does not fetch or consume third-party meshes.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
STATIC_ASSETS = ROOT / "robot_dashboard" / "static" / "assets"
QUANTIZATION_METERS = 0.00001
SCHEMA = "robot-scope.robot-model-lite"
ORIGIN = {"xyz": [0.0, 0.0, 0.0], "rpy": [0.0, 0.0, 0.0]}
DEFAULT_MODELS = (
    (
        STATIC_ASSETS / "turtlebot" / "generic-turtlebot.urdf",
        STATIC_ASSETS / "turtlebot" / "generic-turtlebot-lite.json",
    ),
    (
        STATIC_ASSETS / "so101" / "generic-so101.urdf",
        STATIC_ASSETS / "so101" / "generic-so101-lite.json",
    ),
)


def floats(text: str | None) -> list[float]:
    return [float(value) for value in (text or "").split()]


def vector(text: str | None, default: list[float]) -> list[float]:
    values = floats(text)
    return values[:3] if len(values) >= 3 else list(default)


def origin(element: ET.Element | None) -> dict[str, list[float]]:
    if element is None:
        return {key: list(value) for key, value in ORIGIN.items()}
    return {
        "xyz": vector(element.get("xyz"), ORIGIN["xyz"]),
        "rpy": vector(element.get("rpy"), ORIGIN["rpy"]),
    }


def box_mesh(size: list[float]) -> tuple[list[tuple[float, float, float]], list[int]]:
    x, y, z = (value / 2 for value in size)
    vertices = [
        (-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
        (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z),
    ]
    indices = [
        0, 2, 1, 0, 3, 2,
        4, 5, 6, 4, 6, 7,
        0, 1, 5, 0, 5, 4,
        1, 2, 6, 1, 6, 5,
        2, 3, 7, 2, 7, 6,
        3, 0, 4, 3, 4, 7,
    ]
    return vertices, indices


def cylinder_mesh(
    radius: float,
    length: float,
    segments: int = 24,
) -> tuple[list[tuple[float, float, float]], list[int]]:
    half = length / 2
    vertices: list[tuple[float, float, float]] = []
    for z in (-half, half):
        vertices.extend(
            (radius * math.cos(2 * math.pi * index / segments),
             radius * math.sin(2 * math.pi * index / segments), z)
            for index in range(segments)
        )
    bottom_center = len(vertices)
    vertices.append((0.0, 0.0, -half))
    top_center = len(vertices)
    vertices.append((0.0, 0.0, half))
    indices: list[int] = []
    for index in range(segments):
        following = (index + 1) % segments
        bottom, bottom_next = index, following
        top, top_next = index + segments, following + segments
        indices.extend((bottom, bottom_next, top_next, bottom, top_next, top))
        indices.extend((bottom_center, bottom_next, bottom))
        indices.extend((top_center, top, top_next))
    return vertices, indices


def sphere_mesh(
    radius: float,
    rings: int = 8,
    segments: int = 16,
) -> tuple[list[tuple[float, float, float]], list[int]]:
    vertices = [(0.0, 0.0, radius)]
    for ring in range(1, rings):
        polar = math.pi * ring / rings
        vertices.extend(
            (radius * math.sin(polar) * math.cos(2 * math.pi * index / segments),
             radius * math.sin(polar) * math.sin(2 * math.pi * index / segments),
             radius * math.cos(polar))
            for index in range(segments)
        )
    bottom = len(vertices)
    vertices.append((0.0, 0.0, -radius))
    indices: list[int] = []
    for index in range(segments):
        following = (index + 1) % segments
        indices.extend((0, 1 + index, 1 + following))
        for ring in range(rings - 2):
            current = 1 + ring * segments
            following_ring = current + segments
            indices.extend((current + index, following_ring + index, following_ring + following))
            indices.extend((current + index, following_ring + following, current + following))
        final_ring = 1 + (rings - 2) * segments
        indices.extend((bottom, final_ring + following, final_ring + index))
    return vertices, indices


def material_color(visual: ET.Element) -> tuple[str, str]:
    material = visual.find("material")
    name = material.get("name", "material") if material is not None else "material"
    color = material.find("color") if material is not None else None
    rgba = floats(color.get("rgba") if color is not None else None)
    rgb = rgba[:3] if len(rgba) >= 3 else [0.67, 0.69, 0.77]
    packed = "#" + "".join(f"{max(0, min(255, round(value * 255))):02x}" for value in rgb)
    return name, packed


def primitive_mesh(geometry: ET.Element) -> tuple[list[tuple[float, float, float]], list[int]]:
    box = geometry.find("box")
    if box is not None:
        size = floats(box.get("size"))
        if len(size) != 3 or any(value <= 0 for value in size):
            raise ValueError("URDF box requires three positive size values")
        return box_mesh(size)
    cylinder = geometry.find("cylinder")
    if cylinder is not None:
        radius = float(cylinder.get("radius", "0"))
        length = float(cylinder.get("length", "0"))
        if radius <= 0 or length <= 0:
            raise ValueError("URDF cylinder requires positive radius and length")
        return cylinder_mesh(radius, length)
    sphere = geometry.find("sphere")
    if sphere is not None:
        radius = float(sphere.get("radius", "0"))
        if radius <= 0:
            raise ValueError("URDF sphere requires a positive radius")
        return sphere_mesh(radius)
    if geometry.find("mesh") is not None:
        raise ValueError("Generic dashboard models must not reference external meshes")
    raise ValueError("Only URDF box, cylinder, and sphere geometry is supported")


def encoded_mesh(name: str, visual: ET.Element) -> dict[str, object]:
    geometry = visual.find("geometry")
    if geometry is None:
        raise ValueError(f"Visual {name!r} has no geometry")
    vertices, indices = primitive_mesh(geometry)
    material, color = material_color(visual)
    return {
        "name": name,
        "quantization_m": QUANTIZATION_METERS,
        "vertices_q": [round(value / QUANTIZATION_METERS) for point in vertices for value in point],
        "groups": [{"material": material, "color": color, "indices": indices}],
        "statistics": {
            "source_vertices": len(vertices),
            "source_triangles": len(indices) // 3,
            "vertices": len(vertices),
            "triangles": len(indices) // 3,
            "reduction_percent": 0.0,
            "cluster_cell_m": 0.0,
        },
    }


def joint_item(joint: ET.Element) -> dict[str, object]:
    parent = joint.find("parent")
    child = joint.find("child")
    if parent is None or child is None:
        raise ValueError(f"Joint {joint.get('name', '')!r} is missing parent or child")
    item: dict[str, object] = {
        "name": joint.get("name", ""),
        "type": joint.get("type", "fixed"),
        "parent": parent.get("link", ""),
        "child": child.get("link", ""),
        "origin": origin(joint.find("origin")),
        "axis": vector(joint.find("axis").get("xyz") if joint.find("axis") is not None else None, [0.0, 0.0, 0.0]),
    }
    limit = joint.find("limit")
    if limit is not None and item["type"] == "revolute":
        item["limit"] = {
            "lower": float(limit.get("lower", "0")),
            "upper": float(limit.get("upper", "0")),
        }
    return item


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


def parse_metadata(robot: ET.Element) -> dict[str, object]:
    metadata = robot.find("robot_scope")
    if metadata is None:
        raise ValueError("Generic URDF requires a robot_scope metadata element")
    size = floats(metadata.get("approximate_size_m"))
    if len(size) != 3 or any(value <= 0 for value in size):
        raise ValueError("robot_scope approximate_size_m requires three positive values")
    fidelity = metadata.get("fidelity", "")
    if fidelity != "generic-approximation":
        raise ValueError("Repository-authored primitive models must declare generic-approximation fidelity")
    return {
        "robot_type": metadata.get("robot_type", "generic"),
        "name": metadata.get("name", robot.get("name", "Generic robot")),
        "display_name": metadata.get("display_name", metadata.get("name", "Generic robot")),
        "base_height_m": float(metadata.get("base_height_m", "0")),
        "approximate_size_m": size,
        "fidelity": fidelity,
        "notice": metadata.get("notice", "Generic dashboard visualization; not a dimensional model."),
    }


def build(urdf_path: Path, output: Path) -> dict[str, object]:
    robot = ET.parse(urdf_path).getroot()
    if robot.tag != "robot":
        raise ValueError(f"{urdf_path} is not a URDF robot document")
    metadata = parse_metadata(robot)
    link_elements = robot.findall("link")
    link_names = {link.get("name", "") for link in link_elements}
    raw_joints = [joint_item(joint) for joint in robot.findall("joint")]
    child_names = {str(joint["child"]) for joint in raw_joints}
    roots = sorted(link_names - child_names)
    if len(roots) != 1:
        raise ValueError(f"URDF must contain exactly one root link, found {roots}")
    root_name = roots[0]
    joints = ordered_joints(root_name, raw_joints)

    meshes: dict[str, object] = {}
    links: list[dict[str, object]] = []
    for link in link_elements:
        name = link.get("name", "")
        visuals = link.findall("visual")
        if len(visuals) > 1:
            raise ValueError(f"Generic link {name!r} must use at most one visual")
        if not visuals:
            continue
        mesh_name = name
        meshes[mesh_name] = encoded_mesh(mesh_name, visuals[0])
        links.append({
            "name": name,
            "mesh": mesh_name,
            "visual_origin": origin(visuals[0].find("origin")),
        })

    movable_names = [
        str(joint["name"])
        for joint in joints
        if joint["type"] in {"revolute", "continuous"}
    ]
    default_positions = {name: 0.0 for name in movable_names}
    defaults = robot.find("robot_scope_defaults")
    if defaults is not None:
        for item in defaults.findall("joint"):
            name = item.get("name", "")
            if name in default_positions:
                default_positions[name] = float(item.get("position", "0"))

    asset_triangles = sum(
        mesh["statistics"]["triangles"]  # type: ignore[index]
        for mesh in meshes.values()
    )
    assembled_triangles = sum(
        meshes[link["mesh"]]["statistics"]["triangles"]  # type: ignore[index]
        for link in links
    )
    model = {
        **metadata,
        "asset_unique_triangles": asset_triangles,
        "assembled_triangles": assembled_triangles,
    }
    relative_urdf = urdf_path.relative_to(ROOT / "robot_dashboard" / "static")
    asset = {
        "schema": SCHEMA,
        "version": 1,
        "units": "meter",
        "up_axis": "Z",
        "source": {
            "project": "Robot Scope generic dashboard models",
            "repository": "https://github.com/Phjrab/robot-scope-ros2-dashboard",
            "license": "MIT",
            "license_file": "/static/assets/LICENSE.txt",
            "fidelity": "generic-approximation",
            "urdf_path": f"/static/{relative_urdf.as_posix()}",
            "files": [relative_urdf.as_posix()],
            "generated_by": "scripts/build_generic_robot_models.py",
            "modifications": "Repository-authored URDF primitives triangulated and positions quantized to 0.01 mm; no third-party meshes or textures.",
        },
        "model": model,
        "skeleton": {
            "root": root_name,
            "links": links,
            "joints": joints,
            "joint_order": movable_names,
            "default_joint_positions": default_positions,
        },
        "meshes": meshes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asset, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return asset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urdf", nargs="?", type=Path, help="Primitive-only source URDF")
    parser.add_argument("output", nargs="?", type=Path, help="Output compact JSON")
    args = parser.parse_args()
    pairs = [(args.urdf, args.output)] if args.urdf or args.output else list(DEFAULT_MODELS)
    if any(source is None or output is None for source, output in pairs):
        parser.error("urdf and output must be provided together")
    for source, output in pairs:
        assert source is not None and output is not None
        asset = build(source.resolve(), output.resolve())
        print(
            f"wrote {output} ({output.stat().st_size:,} bytes, "
            f"{asset['model']['assembled_triangles']:,} assembled triangles)"
        )


if __name__ == "__main__":
    main()
