"""Bounded read-only actual costmap/path port for C1/C3 and D3's harness.

Publication, native ingestion and command enforcement are separate evidence.
No costmap simulation or synthetic detour is calculated by this module.
"""
from copy import deepcopy
import hashlib
import json


class ObservationEvidence:
    def __init__(self, *, binding, native=False):
        self.binding, self.native = tuple(binding), native
        self.publication = None
        self.costmaps = {}
        self.paths = {}
        self.plan_changed = False
        self.ingestion = False

    def published(self, identity, *, topic):
        if identity.binding != self.binding:
            raise ValueError("PUBLICATION_BINDING_MISMATCH")
        self.publication = {**identity.packet(), "topic": topic}
        self.ingestion = False
        self.plan_changed = False

    def _check(self, identity, kind):
        if identity.binding != self.binding:
            raise ValueError("SNAPSHOT_BINDING_MISMATCH")
        previous = self.costmaps.get(kind) if kind in {"global", "local"} else self.paths.get(kind)
        if previous and (identity.source_epoch != previous["source_epoch"]
                or identity.sequence <= previous["sequence"]
                or int(identity.stamp_ns) < int(previous["stamp_ns"])):
            raise ValueError("REORDERED_SNAPSHOT")

    def costmap(self, message, identity, *, scope, expected_lethal_indices=(), source="FIXTURE"):
        """Full nav_msgs/OccupancyGrid snapshot. Native harness names expected cells.

        A timestamp alone is never ingestion proof: require observed occupied
        cells and a post-publication snapshot on the same clock/frame binding.
        This is observation correlation, not proof of causal controller use.
        """
        from .messages import get, header_matches, finite
        header_matches(message, identity)
        if scope not in {"global", "local"}:
            raise ValueError("COSTMAP_SCOPE_INVALID")
        self._check(identity, scope)
        info = get(message, "info")
        w, h = get(info, "width"), get(info, "height")
        data = tuple(get(message, "data"))
        if (type(w) is not int or type(h) is not int or not 0 < w*h <= 65_536
                or w <= 0 or h <= 0 or len(data) != w*h
                or any(type(v) is not int or not -1 <= v <= 100 for v in data)):
            raise ValueError("COSTMAP_LAYOUT_INVALID")
        resolution, = finite((get(info, "resolution"),))
        if resolution <= 0:
            raise ValueError("COSTMAP_RESOLUTION_INVALID")
        origin = get(info, "origin")
        position, orientation = get(origin, "position"), get(origin, "orientation")
        origin_wire = {"position_m": finite(get(position, k) for k in ("x", "y", "z")),
                       "orientation_xyzw": finite(get(orientation, k) for k in ("x", "y", "z", "w"))}
        snapshot = {**identity.packet(), "scope": scope, "width": w, "height": h,
            "resolution": resolution, "origin": origin_wire, "data": data,
            "snapshot_source": source, "source_topic": f"/robot_scope_review_x/{scope}_costmap/costmap"}
        snapshot["data_sha256"] = hashlib.sha256(json.dumps(data).encode()).hexdigest()
        self.costmaps[scope] = snapshot
        pub = self.publication
        observed = (self.native and source == "NATIVE_NAV2_SIM" and pub is not None
            and identity.clock_domain != "unknown" and identity.clock_domain == pub["clock_domain"]
            and int(identity.stamp_ns) >= int(pub["stamp_ns"])
            and bool(expected_lethal_indices)
            and all(type(i) is int and 0 <= i < len(data) and data[i] == 100 for i in expected_lethal_indices))
        self.ingestion |= bool(observed)
        snapshot["post_publication_occupied_observed"] = bool(observed)
        return deepcopy(snapshot)

    def path(self, message, identity, *, source="FIXTURE", replan_reason=None):
        from .messages import get, header_matches, pose
        header_matches(message, identity)
        self._check(identity, "global_path")
        poses = get(message, "poses")
        if len(poses) > 8192:
            raise ValueError("PATH_LIMIT")
        # Per-pose stamps may differ; retain them explicitly, never invent z.
        values = []
        for p in poses:
            from dataclasses import replace
            from .messages import stamp_ns
            pi = replace(identity, stamp_ns=stamp_ns(p), frame_id=get(get(p, "header"), "frame_id"))
            if pi.frame_id != identity.frame_id:
                raise ValueError("PATH_POSE_FRAME_MISMATCH")
            values.append({**pose(p, pi).payload, "stamp_ns": pi.stamp_ns, "frame_id": pi.frame_id})
        previous = self.paths.get("global_path")
        digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        changed_geometry = previous is not None and [p["position_m"] for p in previous["poses"]] != [p["position_m"] for p in values]
        after_costmap = any(c.get("post_publication_occupied_observed") and c["clock_domain"] == identity.clock_domain != "unknown"
            and int(c["stamp_ns"]) <= int(identity.stamp_ns) for c in self.costmaps.values())
        self.plan_changed = bool(self.native and source == "NATIVE_NAV2_SIM" and self.ingestion
                                 and changed_geometry and after_costmap)
        self.paths["global_path"] = {**identity.packet(), "poses": values, "sha256": digest,
            "snapshot_source": source, "replan_reason": replan_reason}
        return deepcopy(self.paths["global_path"])

    def snapshot(self):
        return deepcopy({"published_to_nav2": self.publication is not None,
            "costmap_ingestion_observed": self.ingestion,
            "actual_plan_change_observed": self.plan_changed,
            "controller_consumption_observed": False,
            "publication": self.publication, "costmaps": self.costmaps,
            "global_path": self.paths.get("global_path"), "local_trajectory": None})


def scene_with_observations(packet, evidence):
    """Join actual read-only snapshots into the C1/C3 port with a context fence."""
    binding = (packet["map_id"], packet["revision"], packet["tf_epoch"], packet["map_generation"])
    if binding != evidence.binding:
        raise ValueError("SCENE_NATIVE_BINDING_MISMATCH")
    result, native = deepcopy(packet), evidence.snapshot()
    result["global_path"] = native["global_path"]
    result["costmap_snapshot"] = native["costmaps"] or None
    result["nav2_observation"] = native
    # Do not promote the observation-only D2 frame or claim controller use.
    return result
