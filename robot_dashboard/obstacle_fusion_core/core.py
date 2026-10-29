"""Bounded offline geometry. No acquisition, model loading, ROS or publishers.

All points already share the stamped continuous local frame. Ground plane and
self boxes are caller-provided observations, not silently estimated robot facts.
"""

from __future__ import annotations
import copy
import itertools
import hashlib
import re
from dataclasses import dataclass
import numpy as np
from robot_dashboard.relocalization.experimental_se3 import validate_transform


@dataclass(frozen=True)
class Limits:
    max_points: int = 30000
    max_objects: int = 64
    voxel_m: float = 0.06
    range_m: float = 30.0
    ground_band_m: float = 0.025
    track_ttl_ns: int = 1_000_000_000
    max_delay_ns: int = 150_000_000

    def __post_init__(self):
        if not (
            1 <= self.max_points <= 100000
            and 1 <= self.max_objects <= 64
            and 0.01 <= self.voxel_m <= 0.5
            and 1 <= self.range_m <= 100
            and 0 < self.ground_band_m <= 0.05
            and 0 < self.track_ttl_ns <= 10**10
            and 0 <= self.max_delay_ns <= 10**9
        ):
            raise ValueError("INVALID_LIMITS")


def _stamp(meta):
    stamp = meta["stamp_ns"]
    if not isinstance(stamp, str) or not stamp.isdigit():
        raise ValueError("DECIMAL_STAMP_REQUIRED")
    if meta["evidence_kind"] not in ("SYNTHETIC", "REPLAY"):
        raise ValueError("OFFLINE_EVIDENCE_REQUIRED")
    if meta["frame_key"]["source_epoch"] != meta["source_epoch"]:
        raise ValueError("EPOCH_MISMATCH")
    return int(stamp)


def _same(a, b, limit):
    return (
        a["clock_domain"] not in ("UNKNOWN", "unknown", "")
        and a["frame_key"] == b["frame_key"]
        and a["clock_domain"] == b["clock_domain"]
        and a["source_epoch"] == b["source_epoch"]
        and a.get("map_binding") == b.get("map_binding")
        and abs(_stamp(a) - _stamp(b)) <= limit
    )


def _geometry(points, sigma):
    lo, hi = points.min(axis=0), points.max(axis=0)
    return {
        "center": ((lo + hi) / 2).tolist(),
        "extent": (hi - lo + 2 * sigma).tolist(),
        "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "observed_bounds": [lo.tolist(), hi.tolist()],
    }


def _object(points, support, sigma, provenance):
    return {
        "track_id": "untracked",
        "class_name": "unknown",
        "class_score": None,
        "geometry": _geometry(points, sigma),
        "uncertainty": {"bound_m": sigma, "kind": "configured_bound_not_covariance"},
        "sensor_support": support,
        "state": "OBSERVED",
        "novelty": "UNRESOLVED",
        "provenance": provenance,
        "first_seen_ns": None,
        "last_seen_ns": None,
    }


def process_lidar(
    points, meta, *, ground=None, self_boxes=(), reference=None, limits=Limits()
):
    """Voxel-connected components, preserving bounds of every retained point.

    ground: normal,d,uncertainty_m,gravity_up in current frame. Only a narrow
    certified plane band is suppressed; uncertain/unknown ground stays marked.
    self_boxes: stamped current geometry with min/max in this frame. Never infer
    self removal from a generic near-origin radius. Reference requires coverage
    and localization uncertainty; novelty never removes occupied geometry.
    """
    _stamp(meta)
    p = np.asarray(points, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError("XYZ_REQUIRED")
    if len(p) > limits.max_points:
        raise ValueError("POINT_BUDGET_EXCEEDED")
    finite = np.isfinite(p).all(axis=1)
    valid = finite & (
        np.linalg.norm(np.where(np.isfinite(p), p, 0), axis=1) <= limits.range_m
    )
    drops = {
        "invalid_or_range": int((~valid).sum()),
        "ground": 0,
        "self": 0,
        "object_budget": 0,
    }
    p = p[valid]
    reasons = []
    if not self_boxes:
        reasons.append("SELF_GEOMETRY_UNKNOWN")
    if len(self_boxes) > 64:
        raise ValueError("SELF_GEOMETRY_BUDGET")
    for box in self_boxes:
        if not _same(meta, box["meta"], 0):
            reasons.append("SELF_POSE_STALE")
            continue
        lo, hi = np.asarray(box["min"]), np.asarray(box["max"])
        if (
            lo.shape != (3,)
            or hi.shape != (3,)
            or not np.isfinite([lo, hi]).all()
            or np.any(lo >= hi)
        ):
            raise ValueError("INVALID_SELF_BOX")
        keep = ~np.all((p >= lo) & (p <= hi), axis=1)
        drops["self"] += int((~keep).sum())
        p = p[keep]
    if ground is None:
        reasons.append("GROUND_UNKNOWN")
    else:
        n = np.asarray(ground["normal"], float)
        up = np.asarray(ground["gravity_up"], float)
        sigma = float(ground["uncertainty_m"])
        d = float(ground["d"])
        if (
            n.shape != (3,)
            or up.shape != (3,)
            or not np.isfinite([*n, *up, sigma, d]).all()
            or abs(np.linalg.norm(n) - 1) > 1e-6
            or abs(np.linalg.norm(up) - 1) > 1e-6
            or sigma < 0
        ):
            raise ValueError("INVALID_GROUND")
        if ground.get("meta") is not None and not _same(meta, ground["meta"], 0):
            reasons.append("GROUND_STALE")
        elif np.dot(n, up) < 0.7 or sigma >= limits.ground_band_m:
            reasons.append("GROUND_UNCERTAIN")
        else:
            keep = np.abs(p @ n + d) > limits.ground_band_m - sigma
            drops["ground"] = int((~keep).sum())
            p = p[keep]
    cells = {}
    for i, key in enumerate(map(tuple, np.floor(p / limits.voxel_m).astype(np.int64))):
        cells.setdefault(key, []).append(i)
    remaining = set(cells)
    groups = []
    neighbors = list(itertools.product((-1, 0, 1), repeat=3))
    for seed in sorted(cells):
        if seed not in remaining:
            continue
        remaining.remove(seed)
        todo = [seed]
        ids = []
        while todo:
            key = todo.pop()
            ids.extend(cells[key])
            for off in neighbors:
                nxt = tuple(key[j] + off[j] for j in range(3))
                if nxt in remaining:
                    remaining.remove(nxt)
                    todo.append(nxt)
        groups.append(ids)
    objects = []
    for ids in groups[: limits.max_objects]:
        obj = _object(
            p[ids],
            "LIDAR",
            limits.voxel_m / 2,
            {
                "source": copy.deepcopy(meta),
                "point_count": len(ids),
                "field_layout": meta.get("field_layout"),
                "motion_compensated": False,
            },
        )
        if (
            reference is not None
            and reference.get("coverage_verified")
            and reference.get("localization_uncertainty_m", 1) <= 0.05
        ):
            q = np.asarray(reference["points"], float).reshape(-1, 3)
            if len(q) > limits.max_points:
                raise ValueError("REFERENCE_BUDGET_EXCEEDED")
            # Bounded chunks, no all-cloud pairwise matrix.
            near = any(
                np.any(
                    np.linalg.norm(
                        q[j : j + 256] - np.asarray(obj["geometry"]["center"]), axis=1
                    )
                    <= max(obj["geometry"]["extent"]) / 2 + 0.1
                )
                for j in range(0, len(q), 256)
            )
            obj["novelty"] = "KNOWN" if near else "NEW_TO_REFERENCE"
        objects.append(obj)
    drops["object_budget"] = max(0, len(groups) - limits.max_objects)
    return {
        "meta": copy.deepcopy(meta),
        "obstacles": objects,
        "health": {
            "reasons": reasons,
            "coverage": "PARTIAL",
            "motion_compensated": False,
            "source_age_ns": meta.get("source_age_ns"),
            "age_status": "UNKNOWN"
            if meta.get("source_age_ns") is None
            else "CALLER_MAPPED",
        },
        "dropped_counts": drops,
    }


def detector_adapter(records, *, manifest, model_path, native_shape):
    """Verify a local model artifact hash, without deserializing or executing it.

    Caller supplies actual inference outputs in original pixel coordinates. This
    verifies identity/preprocessing declarations, not model accuracy or trust.
    """
    expected = manifest.get("sha256", "")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected)
        or manifest.get("preprocess") != "native_xyxy_no_resize"
    ):
        raise ValueError("MODEL_MANIFEST_UNSUPPORTED")
    h = hashlib.sha256()
    with open(model_path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    if h.hexdigest() != expected:
        raise ValueError("MODEL_HASH_MISMATCH")
    if len(records) > 64:
        raise ValueError("DETECTION_BUDGET_EXCEEDED")
    out = copy.deepcopy(records)
    for record in out:
        if (
            record.get("native_shape") != list(native_shape)
            or manifest.get("class_names", {}).get(str(record["class_id"]))
            != record["class_name"]
        ):
            raise ValueError("MODEL_CLASS_OR_NATIVE_SHAPE_MISMATCH")
    return out


def _intrinsics(k):
    vals = np.array([k[x] for x in ("fx", "fy", "ppx", "ppy")], float)
    if (
        not np.isfinite(vals).all()
        or min(vals[:2]) <= 0
        or k["model"] not in ("none", "brown_conrady")
    ):
        raise ValueError("INTRINSICS_OR_DISTORTION_UNSUPPORTED")
    c = np.asarray(k.get("coeffs", [0] * 5), float)
    if c.shape != (5,) or not np.isfinite(c).all():
        raise ValueError("INVALID_DISTORTION")
    return vals, c


def _distort(x, y, c):
    k1, k2, p1, p2, k3 = c
    r2 = x * x + y * y
    radial = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
    return x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x), y * radial + p1 * (
        r2 + 2 * y * y
    ) + 2 * p2 * x * y


def _deproject(u, v, z, k):
    (fx, fy, cx, cy), c = _intrinsics(k)
    xd, yd = (u - cx) / fx, (v - cy) / fy
    x, y = xd.copy(), yd.copy()
    if k["model"] == "brown_conrady":
        for _ in range(12):
            dx, dy = _distort(x, y, c)
            x += xd - dx
            y += yd - dy
        dx, dy = _distort(x, y, c)
        if np.max(np.abs(dx - xd) + np.abs(dy - yd), initial=0) > 1e-5:
            raise ValueError("DISTORTION_INVERSION_FAILED")
    return np.column_stack((x * z, y * z, z))


def lift_detections(
    detections, depth, meta, *, calibration=None, model_manifest=None, limits=Limits()
):
    """Reproject depth optical pixels to color; no same-pixel aligned shortcut.

    Conservative foreground evidence: eroded ROI must have nearer depth than
    its surrounding ring. A flat wall/background-only bbox remains image-only.
    This deliberately loses detections without foreground/background contrast.
    """
    _stamp(meta)
    if len(detections) > limits.max_objects:
        raise ValueError("DETECTION_BUDGET_EXCEEDED")
    result = {
        "meta": copy.deepcopy(meta),
        "obstacles": [],
        "image_only": [],
        "health": {"reasons": []},
    }

    def reject(reason):
        result["image_only"] = [
            {"detection": copy.deepcopy(d), "reason": reason} for d in detections
        ]
        return result

    if calibration is None:
        return reject("CALIBRATION_UNKNOWN")
    if not _same(meta, calibration["meta"], 0):
        return reject("CAPTURE_TRANSFORM_OR_CLOCK_MISMATCH")
    if not calibration.get("verified") or not calibration.get(
        "clock_correspondence_verified"
    ):
        return reject("CALIBRATION_OR_CLOCK_UNVERIFIED")
    if (
        model_manifest is None
        or not re.fullmatch(r"[0-9a-f]{64}", model_manifest.get("sha256", ""))
        or not model_manifest.get("preprocess")
    ):
        return reject("SEMANTIC_MODEL_INPUT_REQUIRED")
    arr = np.asarray(depth, float)
    if arr.ndim != 2 or arr.size > 640 * 480:
        raise ValueError("DEPTH_SHAPE_OR_BUDGET")
    dk, ck = calibration["depth_intrinsics"], calibration["color_intrinsics"]
    if arr.shape != (dk["height"], dk["width"]):
        raise ValueError("DEPTH_INTRINSICS_SHAPE")
    scale = float(calibration["depth_scale_m"])
    sigma = float(calibration["uncertainty_m"])
    if (
        not np.isfinite([scale, sigma]).all()
        or not 0 < scale <= 1
        or not 0 <= sigma <= 0.5
    ):
        raise ValueError("CALIBRATION_SCALE_OR_UNCERTAINTY")
    td = validate_transform(calibration["T_color_depth"])
    tl = validate_transform(calibration["T_local_depth"])
    v, u = np.indices(arr.shape)
    z = arr.ravel() * scale
    good = np.isfinite(z) & (z > 0.1) & (z <= limits.range_m)
    xyz = _deproject(u.ravel()[good], v.ravel()[good], z[good], dk)
    pc = xyz @ td[:3, :3].T + td[:3, 3]
    valid = pc[:, 2] > 0.1
    xyz, pc = xyz[valid], pc[valid]
    (fx, fy, cx, cy), coeff = _intrinsics(ck)
    x, y = pc[:, 0] / pc[:, 2], pc[:, 1] / pc[:, 2]
    if ck["model"] == "brown_conrady":
        x, y = _distort(x, y, coeff)
    uv = np.column_stack((x * fx + cx, y * fy + cy))
    for det in detections:
        reason = None
        bbox = np.asarray(det["bbox_xyxy"], float)
        if (
            bbox.shape != (4,)
            or not np.isfinite(bbox).all()
            or not 0 <= det["score"] <= 1
            or det["native_shape"] != [ck["height"], ck["width"]]
            or bbox[2] <= bbox[0]
            or bbox[3] <= bbox[1]
        ):
            raise ValueError("INVALID_NATIVE_DETECTION")
        if (
            model_manifest.get("class_names", {}).get(str(det["class_id"]))
            != det["class_name"]
        ):
            reason = "MODEL_CLASS_MISMATCH"
        a, b, c, d = bbox
        margin = 0.15 * min(c - a, d - b)
        inside = (
            (uv[:, 0] >= a + margin)
            & (uv[:, 0] <= c - margin)
            & (uv[:, 1] >= b + margin)
            & (uv[:, 1] <= d - margin)
        )
        outer = (
            (uv[:, 0] >= a - margin)
            & (uv[:, 0] <= c + margin)
            & (uv[:, 1] >= b - margin)
            & (uv[:, 1] <= d + margin)
        )
        full = (uv[:, 0] >= a) & (uv[:, 0] <= c) & (uv[:, 1] >= b) & (uv[:, 1] <= d)
        ring = pc[outer & ~full, 2]
        roi = pc[inside, 2]
        if len(roi) < 5 or len(ring) < 5:
            reason = reason or "INSUFFICIENT_VALID_DEPTH"
        else:
            # nearest coherent depth mode, rejecting mixed/occluded broad ROIs
            front = np.quantile(roi, 0.2)
            selected = inside & (np.abs(pc[:, 2] - front) <= 0.08 + sigma)
            if (
                selected.sum() < max(5, 0.35 * len(roi))
                or np.median(ring) - front <= 0.12 + 2 * sigma
            ):
                reason = reason or "BACKGROUND_OR_OCCLUSION_UNRESOLVED"
        if reason:
            result["image_only"].append(
                {"detection": copy.deepcopy(det), "reason": reason}
            )
            continue
        local = xyz[selected] @ tl[:3, :3].T + tl[:3, 3]
        obj = _object(
            local,
            "RGBD",
            sigma + 0.03,
            {
                "source": copy.deepcopy(meta),
                "detection": copy.deepcopy(det),
                "model_manifest": copy.deepcopy(model_manifest),
                "calibration_id": calibration["id"],
                "depth_measurement": "optical_Z",
                "motion_compensated": False,
            },
        )
        obj.update(class_name=det["class_name"], class_score=det["score"])
        result["obstacles"].append(obj)
    return result


def _overlap(a, b, gate=0.2):
    ga, gb = a["geometry"], b["geometry"]
    distance = np.abs(np.asarray(ga["center"]) - gb["center"])
    extent = (np.asarray(ga["extent"]) + gb["extent"]) / 2
    ea, eb = np.maximum(ga["extent"], 0.05), np.maximum(gb["extent"], 0.05)
    size_ok = np.all(np.maximum(ea / eb, eb / ea) <= 6.0)
    return bool(
        size_ok
        and np.all(distance <= extent + gate)
        and np.linalg.norm(distance) <= 1.0
    )


def associate(lidar, rgbd, *, limits=Limits()):
    """One-to-one unique geometry gates; ambiguous observations stay separate."""
    out = copy.deepcopy(lidar)
    depth = copy.deepcopy(rgbd["obstacles"])
    if not _same(lidar["meta"], rgbd["meta"], limits.max_delay_ns):
        out["health"]["reasons"].append("FUSION_FRAME_CLOCK_OR_TIME_UNKNOWN")
        # Different-frame geometry cannot enter this frame; retain diagnostic only.
        out["health"]["unmatched_depth_count"] = len(depth)
        return out
    candidates = [
        [j for j, b in enumerate(depth) if _overlap(a, b)] for a in out["obstacles"]
    ]
    used = set()
    for i, choices in enumerate(candidates):
        if len(choices) != 1 or sum(choices[0] in c for c in candidates) != 1:
            if choices:
                out["health"]["reasons"].append("AMBIGUOUS_ASSOCIATION")
            continue
        j = choices[0]
        used.add(j)
        a, b = out["obstacles"][i], depth[j]
        bounds = []
        for o in (a, b):
            g = o["geometry"]
            c = np.asarray(g["center"])
            e = np.asarray(g["extent"]) / 2
            bounds.extend([c - e, c + e])
        a["geometry"] = _geometry(np.asarray(bounds), 0)
        a.update(
            sensor_support="FUSED",
            class_name=b["class_name"],
            class_score=b["class_score"],
        )
        a["provenance"]["rgbd"] = b["provenance"]
        a["provenance"]["sample_delay_ns"] = abs(
            _stamp(lidar["meta"]) - _stamp(rgbd["meta"])
        )
    out["obstacles"].extend(b for j, b in enumerate(depth) if j not in used)
    out["dropped_counts"]["object_budget"] += max(
        0, len(out["obstacles"]) - limits.max_objects
    )
    out["obstacles"] = out["obstacles"][: limits.max_objects]
    return out


class Tracker:
    """Local-frame IDs; ambiguous crossing never asserts confident identity.

    No expiration produces clearing. Only caller-supplied fresh rays with matching
    frame, clock and epoch are emitted separately. Caller owns ray calibration.
    """

    def __init__(self, limits=Limits()):
        self.limits = limits
        self.tracks = {}
        self.generation = None
        self.last = None
        self.counter = 0
        self.reset_count = 0
        self.retired = set()

    def step(self, observation, *, clearing_rays=()):
        m = observation["meta"]
        stamp = _stamp(m)
        age = m.get("source_age_ns")
        if age is not None and (
            type(age) is not int or not 0 <= age <= self.limits.max_delay_ns
        ):
            raise ValueError("STALE_SOURCE_FRAME")
        generation = (
            m["source_epoch"],
            m["frame_key"]["frame_id"],
            m["clock_domain"],
            tuple(sorted(m["map_binding"].items())),
        )
        if generation in self.retired:
            raise ValueError("RETIRED_GENERATION")
        if generation != self.generation:
            if self.generation is not None:
                if len(self.retired) >= 64:
                    raise ValueError("GENERATION_BUDGET_RECREATE_TRACKER")
                self.retired.add(self.generation)
            self.tracks = {}
            self.last = None
            self.generation = generation
            self.reset_count += 1
        if self.last is not None and (
            stamp <= self.last[0] or m["sequence"] <= self.last[1]
        ):
            raise ValueError("REORDERED_OR_DUPLICATE_FRAME")
        self.last = (stamp, m["sequence"])
        old = {
            k: v
            for k, v in self.tracks.items()
            if stamp - int(v["last_seen_ns"]) <= self.limits.track_ttl_ns
        }
        objects = copy.deepcopy(observation["obstacles"])
        if len(objects) > self.limits.max_objects:
            raise ValueError("OBJECT_BUDGET_EXCEEDED")
        candidates = [
            [k for k, v in old.items() if _overlap(o, v, 0.15)] for o in objects
        ]
        updated = {}
        for o, choices in zip(objects, candidates):
            if len(choices) == 1 and sum(choices[0] in c for c in candidates) == 1:
                key = choices[0]
                o["first_seen_ns"] = old[key]["first_seen_ns"]
            else:
                self.counter += 1
                key = f"track-{self.reset_count}-{self.counter}"
                o["first_seen_ns"] = m["stamp_ns"]
                if choices:
                    o["provenance"]["identity_reason"] = "AMBIGUOUS_NEW_ID"
            o.update(track_id=key, last_seen_ns=m["stamp_ns"], state="OBSERVED")
            updated[key] = o
        for key, o in old.items():
            if key not in updated and len(updated) < self.limits.max_objects:
                o = copy.deepcopy(o)
                o["state"] = "OCCLUDED"
                updated[key] = o
        self.tracks = updated
        rays = []
        if len(clearing_rays) > self.limits.max_points:
            raise ValueError("RAY_BUDGET_EXCEEDED")
        for ray in clearing_rays:
            if (
                not _same(m, ray["meta"], self.limits.max_delay_ns)
                or _stamp(ray["meta"]) > stamp
            ):
                continue
            ends = np.asarray([ray["origin"], ray["free_endpoint"]], float)
            if (
                ends.shape != (2, 3)
                or not np.isfinite(ends).all()
                or np.linalg.norm(ends[1] - ends[0]) > self.limits.range_m
            ):
                continue
            rays.append(copy.deepcopy(ray))
        frame = {
            k: copy.deepcopy(m[k])
            for k in (
                "frame_key",
                "stamp_ns",
                "clock_domain",
                "source_epoch",
                "sequence",
                "evidence_kind",
                "map_binding",
                "host_clock_id",
                "received_monotonic_ns",
            )
        }
        frame.update(
            schema_version="0.1",
            producer="d2.offline",
            calibration_id=m.get("calibration_id"),
            input_sources=[copy.deepcopy(m)],
            obstacles=list(updated.values()),
            health=copy.deepcopy(observation["health"]),
            dropped_counts=copy.deepcopy(observation["dropped_counts"]),
            observation_only=True,
            published_to_nav2=False,
            costmap_ingestion_observed=False,
            controller_consumption_observed=False,
        )
        return {
            "obstacle_frame": frame,
            "clearing_evidence": rays,
            "expiry_policy": {
                "display_ttl_ns": self.limits.track_ttl_ns,
                "costmap_ttl_ns": None,
                "expiration_is_free": False,
            },
        }
