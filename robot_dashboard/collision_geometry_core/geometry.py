"""Metric primitive geometry. No ROS, processes, mesh loading or network side effects.

Box/box separation is a conservative metric lower bound (SAT), not Euclidean
penetration depth. Cylinders are explicitly enclosed by capsules. Meshes fail
closed; display meshes are never substituted. Touching counts as overlap.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np


UPSTREAM = "unitreerobotics/unitree_ros@f3772ce54c56ef2d34c6aee8100bc768896c7d19"


def vector(value, size=3):
    out = np.asarray(value, dtype=float)
    if out.shape != (size,) or not np.isfinite(out).all():
        raise ValueError("finite vector required")
    return out


def rigid(value):
    t = np.asarray(value, dtype=float)
    if (
        t.shape != (4, 4)
        or not np.isfinite(t).all()
        or not np.allclose(t[3], [0, 0, 0, 1], atol=1e-9, rtol=0)
        or not np.allclose(t[:3, :3].T @ t[:3, :3], np.eye(3), atol=1e-8, rtol=0)
        or abs(np.linalg.det(t[:3, :3]) - 1) > 1e-8
    ):
        raise ValueError("metric SE3 required; scale/shear/reflection forbidden")
    return t.copy()


def rotation(axis, angle):
    a = vector(axis)
    n = np.linalg.norm(a)
    if n < 1e-12 or not math.isfinite(angle):
        raise ValueError("rotation axis/angle invalid")
    x, y, z = a / n
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * k @ k


def transform(xyz=(0, 0, 0), rpy=(0, 0, 0)):
    r, p, y = vector(rpy)
    t = np.eye(4)
    t[:3, :3] = rotation((0, 0, 1), y) @ rotation((0, 1, 0), p) @ rotation((1, 0, 0), r)
    t[:3, 3] = vector(xyz)
    return t


@dataclass
class Primitive:
    name: str
    kind: str
    pose: np.ndarray
    size: tuple
    support_eligible: bool = False

    def __post_init__(self):
        self.pose = rigid(self.pose)
        sizes = vector(
            self.size, 3 if self.kind == "box" else 2 if self.kind == "capsule" else 1
        )
        if self.kind not in ("box", "sphere", "capsule") or np.any(sizes <= 0):
            raise ValueError("positive primitive dimensions required")
        self.size = tuple(float(x) for x in sizes)

    @property
    def radius(self):
        if self.kind == "box":
            return float(np.linalg.norm(self.size) / 2)
        return self.size[0] + (self.size[1] / 2 if self.kind == "capsule" else 0)

    def segment(self):
        c = self.pose[:3, 3]
        h = self.pose[:3, 2] * (self.size[1] / 2 if self.kind == "capsule" else 0)
        return c - h, c + h


def _point_box(p, box):
    q = box.pose[:3, :3].T @ (p - box.pose[:3, 3])
    d = np.abs(q) - np.asarray(box.size) / 2
    return float(np.linalg.norm(np.maximum(d, 0)) + min(float(max(d)), 0))


def _segment_box(a, b, box):
    # Distance to the solid box is convex along a segment. Ternary search gives
    # a bounded approximation; subtract the residual segment-length error.
    lo, hi = 0.0, 1.0
    for _ in range(60):
        u, v = (2 * lo + hi) / 3, (lo + 2 * hi) / 3
        if max(0, _point_box(a + u * (b - a), box)) < max(
            0, _point_box(a + v * (b - a), box)
        ):
            hi = v
        else:
            lo = u
    return min(
        max(0, _point_box(a, box)),
        max(0, _point_box(b, box)),
        max(0, _point_box(a + (lo + hi) / 2 * (b - a), box)),
    ) - np.linalg.norm(b - a) * (hi - lo)


def _segment_distance(p, q, a, b):
    # Convex segment pair: interior stationary point plus all boundary minima.
    u, v, w = q - p, b - a, p - a
    aa, bb, cc = float(u @ u), float(u @ v), float(v @ v)
    dd, ee = float(u @ w), float(v @ w)
    candidates = []
    for s in (0.0, 1.0):
        t = float(np.clip((ee + s * bb) / cc, 0, 1)) if cc else 0.0
        candidates.append(np.linalg.norm(p + s * u - a - t * v))
    for t in (0.0, 1.0):
        s = float(np.clip((t * bb - dd) / aa, 0, 1)) if aa else 0.0
        candidates.append(np.linalg.norm(p + s * u - a - t * v))
    den = aa * cc - bb * bb
    if den > 1e-15:
        s, t = (bb * ee - cc * dd) / den, (aa * ee - bb * dd) / den
        if 0 <= s <= 1 and 0 <= t <= 1:
            candidates.append(np.linalg.norm(p + s * u - a - t * v))
    return float(min(candidates))


def clearance(a, b):
    """Signed conservative separation in metres. Nonpositive => model overlap."""
    if a.kind != "box" and b.kind != "box":
        return _segment_distance(*a.segment(), *b.segment()) - a.size[0] - b.size[0]
    if a.kind != "box":
        a, b = b, a
    if b.kind == "sphere":
        return _point_box(b.pose[:3, 3], a) - b.size[0]
    if b.kind == "capsule":
        return float(_segment_box(*b.segment(), a) - b.size[0])
    axes = [*a.pose[:3, :3].T, *b.pose[:3, :3].T]
    axes += [np.cross(x, y) for x in a.pose[:3, :3].T for y in b.pose[:3, :3].T]
    delta = b.pose[:3, 3] - a.pose[:3, 3]
    gaps = []
    for axis in axes:
        n = np.linalg.norm(axis)
        if n < 1e-10:
            continue
        axis = axis / n
        ra = np.abs(a.pose[:3, :3].T @ axis) @ (np.asarray(a.size) / 2)
        rb = np.abs(b.pose[:3, :3].T @ axis) @ (np.asarray(b.size) / 2)
        gaps.append(abs(float(delta @ axis)) - ra - rb)
    return float(max(gaps))


def plane_clearance(p, normal, offset):
    n = vector(normal)
    if abs(np.linalg.norm(n) - 1) > 1e-8 or not math.isfinite(offset):
        raise ValueError("unit support normal required")
    if p.kind == "box":
        radius = np.abs(p.pose[:3, :3].T @ n) @ (np.asarray(p.size) / 2)
    else:
        radius = p.size[0]
        if p.kind == "capsule":
            radius += abs(float(p.pose[:3, 2] @ n)) * p.size[1] / 2
    return float(p.pose[:3, 3] @ n - offset - radius)


def _origin(element):
    if element is None:
        return np.eye(4)
    return transform(
        [float(x) for x in element.get("xyz", "0 0 0").split()],
        [float(x) for x in element.get("rpy", "0 0 0").split()],
    )


class RobotGeometry:
    """Trusted in-memory URDF collision parser, no URI or mesh resolution.

    Positive mesh scale does not turn a mesh into a supported primitive: reject.
    Joint and collision origins are composed in URDF order. Fixed and revolute/
    prismatic joints supported; missing states, limits and graph errors reject.
    """

    def __init__(self, xml, *, provenance, mounts=(), unmodeled=(), gait_margin=0.0):
        root = ET.fromstring(xml)
        self.source_hash = hashlib.sha256(xml.encode()).hexdigest()
        self.provenance = provenance
        self.unmodeled = tuple(unmodeled)
        self.gait_margin = float(gait_margin)
        if not math.isfinite(self.gait_margin) or self.gait_margin < 0:
            raise ValueError("gait margin invalid")
        self.links = {}
        for link in root.findall("link"):
            name = link.attrib["name"]
            if name in self.links:
                raise ValueError("duplicate link")
            self.links[name] = []
            for i, c in enumerate(link.findall("collision")):
                g = c.find("geometry")
                if g is None or len(g) != 1:
                    raise ValueError("one primitive required")
                shape = g[0]
                kind = shape.tag
                if kind == "box":
                    dims = tuple(map(float, shape.attrib["size"].split()))
                elif kind == "sphere":
                    dims = (float(shape.attrib["radius"]),)
                elif kind == "cylinder":
                    kind = "capsule"  # conservative enclosing cylinder, not exact mesh
                    dims = (
                        float(shape.attrib["radius"]),
                        float(shape.attrib["length"]),
                    )
                else:
                    raise ValueError("unsupported collision geometry: " + kind)
                self.links[name].append(
                    Primitive(
                        f"{name}/{i}",
                        kind,
                        _origin(c.find("origin")),
                        dims,
                        name.endswith("_foot"),
                    )
                )
        self.joints = []
        children = set()
        joint_names = set()
        for j in root.findall("joint"):
            if j.attrib["name"] in joint_names or j.find("mimic") is not None:
                raise ValueError("duplicate or mimic joint unsupported")
            joint_names.add(j.attrib["name"])
            parent, child = (
                j.find("parent").attrib["link"],
                j.find("child").attrib["link"],
            )
            if parent not in self.links or child not in self.links or child in children:
                raise ValueError("invalid joint tree")
            children.add(child)
            kind = j.attrib["type"]
            if kind not in ("fixed", "revolute", "continuous", "prismatic"):
                raise ValueError("unsupported joint")
            axis = j.find("axis")
            limit = j.find("limit")
            self.joints.append(
                dict(
                    name=j.attrib["name"],
                    parent=parent,
                    child=child,
                    kind=kind,
                    origin=_origin(j.find("origin")),
                    axis=vector(list(map(float, axis.get("xyz").split())))
                    if axis is not None
                    else np.array([1.0, 0, 0]),
                    limits=(float(limit.get("lower")), float(limit.get("upper")))
                    if limit is not None and kind != "continuous"
                    else None,
                )
            )
        roots = set(self.links) - children
        if len(roots) != 1:
            raise ValueError("single root required")
        self.root = roots.pop()
        self.mounts = tuple(mounts)
        if any(not isinstance(p, Primitive) for p in self.mounts):
            raise ValueError("explicit root-frame mounts required")

    @property
    def geometry_hash(self):
        """Hash actual runtime model too: caller mutation cannot retain old identity."""

        def primitive(p):
            return (p.name, p.kind, p.pose.tolist(), p.size, p.support_eligible)

        payload = dict(
            source=self.source_hash,
            provenance=self.provenance,
            unmodeled=self.unmodeled,
            gait_margin=self.gait_margin,
            root=self.root,
            links={name: [primitive(p) for p in ps] for name, ps in self.links.items()},
            joints=[
                {
                    k: (v.tolist() if isinstance(v, np.ndarray) else v)
                    for k, v in j.items()
                }
                for j in self.joints
            ],
            mounts=[primitive(p) for p in self.mounts],
        )
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()

    def fk(self, root_pose, joints):
        poses = {self.root: rigid(root_pose)}
        pending = self.joints.copy()
        while pending:
            ready = [j for j in pending if j["parent"] in poses]
            if not ready:
                raise ValueError("cyclic/disconnected joint tree")
            for j in ready:
                motion = np.eye(4)
                if j["kind"] != "fixed":
                    q = float(joints[j["name"]])
                    if not math.isfinite(q) or (
                        j["limits"] and not j["limits"][0] <= q <= j["limits"][1]
                    ):
                        raise ValueError("joint outside model limits")
                    if j["kind"] == "prismatic":
                        axis = j["axis"] / np.linalg.norm(j["axis"])
                        motion[:3, 3] = axis * q
                    else:
                        motion[:3, :3] = rotation(j["axis"], q)
                poses[j["child"]] = poses[j["parent"]] @ j["origin"] @ motion
                pending.remove(j)
        out = [
            Primitive(p.name, p.kind, poses[name] @ p.pose, p.size, p.support_eligible)
            for name, primitives in self.links.items()
            for p in primitives
        ]
        out += [
            Primitive(p.name, p.kind, poses[self.root] @ p.pose, p.size)
            for p in self.mounts
        ]
        return out


def official_go2(*, mounts=(), gait_margin=0.0):
    return RobotGeometry(
        Path(__file__).with_name("go2_collision_source.urdf").read_text(),
        provenance=UPSTREAM,
        mounts=mounts,
        gait_margin=gait_margin,
        unmodeled=(
            "actual camera bracket",
            "external LiDAR mount",
            "Jetson and cables",
            "measured walking envelope and stopping distance",
        ),
    )
