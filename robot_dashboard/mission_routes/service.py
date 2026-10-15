"""Revisioned authoring/API facade; one existing MissionCoordinator owns runs."""
from __future__ import annotations

import asyncio
import copy
import math
import re
import secrets
import time
from datetime import datetime, timezone

from ..application.mission_coordinator import MissionConflict, MissionNotFound, MissionUnavailable, MissionValidationError
from ..spatial_routes import ROBOT_RADIUS_M, SpatialRouteError, select_execution_waypoints, validate_route, route_length
from .models import DefinitionInput, Pose, digest
from .store import PlanStore


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class MissionRoutes:
    def __init__(self, root, maps, routes, coordinator, context, planner):
        self.maps, self.routes, self.coordinator = maps, routes, coordinator
        self.context, self.planner = context, planner
        self.store = PlanStore(root)
        self.data = self.store.load()
        self._lock = asyncio.Lock()
        self._generation = 0
        self._last_observation = {}
        self._validate_store()
        self._persisted = copy.deepcopy(self.data)
        self._admission = object()
        self.coordinator._managed_admission = self._admission
        self.coordinator._dispatch_preflight = self.preflight_dispatch

    def _validate_store(self):
        for key, entry in self.data["definitions"].items():
            if not re.fullmatch(r"[0-9a-f]{32}", key) or not isinstance(entry, dict):
                raise MissionUnavailable("invalid stored definition identity")
            try:
                body = DefinitionInput.model_validate(entry["definition"]).model_dump()
                if digest(body) != entry["revision"] or entry["id"] != key:
                    raise ValueError()
            except (KeyError, TypeError, ValueError) as exc:
                raise MissionUnavailable("stored definition is invalid; original preserved") from exc
        for key, run in self.data["runs"].items():
            if not re.fullmatch(r"[0-9a-f]{32}", key) or not isinstance(run, dict) or run.get("id") != key:
                raise MissionUnavailable("stored run is invalid")
            try:
                body = DefinitionInput.model_validate(run["definition"]).model_dump()
                if digest(body) != run["definition_revision"]:
                    raise ValueError()
            except (KeyError, ValueError, TypeError) as exc:
                raise MissionUnavailable("stored run definition is invalid") from exc
        for key, entry in self.data["requests"].items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", key) or not isinstance(entry, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("digest", ""))):
                raise MissionUnavailable("stored idempotency ledger is invalid")

    def _save(self):
        try:
            self.store.save(self.data)
        except (OSError, ValueError, MissionUnavailable) as exc:
            # A failed authoring write must not be served as durable state.
            self.data = copy.deepcopy(self._persisted)
            raise MissionUnavailable("MISSION_AUDIT_STORAGE_UNAVAILABLE") from exc
        self._persisted = copy.deepcopy(self.data)

    async def _transaction(self, request_id, payload, operation, *, safety=False):
        async with self._lock:
            fingerprint = digest(payload)
            existing = self.data["requests"].get(request_id)
            if existing:
                if existing["digest"] != fingerprint:
                    raise MissionConflict("REQUEST_ID_PAYLOAD_CONFLICT")
                if existing.get("result") is not None:
                    receipt = existing["result"]
                    if receipt.get("receipt_type") == "run_ref":
                        response = self.run(receipt["run_id"])
                        if receipt.get("audit_warning"):
                            response["audit_warning"] = receipt["audit_warning"]
                        return response
                    return copy.deepcopy(receipt)
                if not safety:
                    raise MissionConflict("REQUEST_OUTCOME_UNCERTAIN: read run state; do not resubmit with a new key")
            ledger_available = len(self.data["requests"]) < 256
            if not ledger_available and not safety:
                raise MissionConflict("REQUEST_LEDGER_FULL: explicit archival required")
            if ledger_available:
                self.data["requests"][request_id] = {"digest": fingerprint, "result": None}
                try:
                    self._save()
                except MissionUnavailable:
                    if not safety:
                        raise
                    ledger_available = False
        # Slow planning never holds the ledger lock: stop requests can queue at
        # the coordinator while the current dispatch is being checked.
        result = await operation()
        if ledger_available:
            async with self._lock:
                # A run contains up to 4096 planned poses. Do not duplicate it
                # into every action receipt; replay reads the same run identity
                # at its current state and never repeats the physical action.
                receipt = {"receipt_type": "run_ref", "run_id": result["run"]["id"], "audit_warning": result.get("audit_warning")} if "run" in result else copy.deepcopy(result)
                self.data["requests"][request_id]["result"] = receipt
                try:
                    self._save()
                except MissionUnavailable:
                    if not safety and "run" not in result:
                        raise
                    ledger_available = False
        if not ledger_available:
            result["audit_warning"] = "STOP_APPLIED_WITHOUT_DURABLE_REQUEST_RECEIPT" if safety else "ACTION_APPLIED_WITHOUT_DURABLE_REQUEST_RECEIPT: read current run; do not submit a new key"
        return result

    def definitions(self):
        return {"definitions": copy.deepcopy(list(self.data["definitions"].values())), "context": self.context.snapshot()}

    def definition(self, identifier, revision=None):
        value = self.data["definitions"].get(identifier)
        if value is None:
            raise MissionNotFound("mission definition was not found")
        if revision is not None and value["revision"] != revision:
            raise MissionConflict("DEFINITION_REVISION_CHANGED")
        return copy.deepcopy(value)

    async def write(self, body, *, identifier=None, copy_from=None):
        payload = body.model_dump()

        async def operation():
            if identifier is not None:
                self.definition(identifier, body.base_revision)
                self._require_definition_idle(identifier)
            elif len(self.data["definitions"]) >= 64:
                raise MissionConflict("DEFINITION_CATALOG_FULL")
            if copy_from is not None:
                self.definition(copy_from)
            definition = DefinitionInput.model_validate({k: v for k, v in payload.items() if k not in {"request_id", "base_revision"}}).model_dump()
            identity = identifier or secrets.token_hex(16)
            entry = {"id": identity, "revision": digest(definition), "definition": definition, "updated_at": utc()}
            self.data["definitions"][identity] = entry
            self._save()
            return {"plan": copy.deepcopy(entry)}

        return await self._transaction(body.request_id, {"write": identifier, "copy": copy_from, **payload}, operation)

    def _require_definition_idle(self, identifier):
        for run in self.data["runs"].values():
            if run["definition_id"] == identifier and self.coordinator.snapshot(run["id"])["mission"]["ownership_active"]:
                raise MissionConflict("DEFINITION_ACTIVE_COPY_REQUIRED")

    async def delete_definition(self, identifier, body):
        async def operation():
            self.definition(identifier, body.revision)
            self._require_definition_idle(identifier)
            del self.data["definitions"][identifier]
            self._save()
            return {"deleted": identifier, "historical_runs_preserved": True}
        return await self._transaction(body.request_id, {"delete": identifier, **body.model_dump()}, operation)

    def _resolved(self, entry):
        definition = entry["definition"]
        family = definition["map_family"]
        try:
            geometry = self.maps.route_geometry(family["occupancy_map_id"], family["occupancy_revision"])
            annotations = self.maps.annotations(family["occupancy_map_id"])
            if getattr(geometry, "frame_id", None) != "map" or not math.isfinite(geometry.resolution) or geometry.resolution <= 0:
                raise MissionConflict("NAVIGATION_MAP_FRAME_OR_RESOLUTION_INVALID")
            if annotations.get("annotation_revision") != definition["annotation_revision"]:
                raise MissionConflict("ANNOTATION_REVISION_CHANGED")
            refs = {p["id"]: p for p in annotations.get("points", []) if p.get("type") in {"HOME", "POI", "DOCK", "INSPECTION_POINT"}}
            poses = []
            for visit in definition["visits"]:
                point = visit["pose"]
                if visit["target"] == "annotation_ref":
                    annotation = refs.get(visit["annotation_id"])
                    if annotation is None:
                        raise MissionConflict("ANNOTATION_REMOVED")
                    point = annotation.get("pose", annotation)
                point = {k: point[k] for k in ("x", "y", "yaw")}
                if visit.get("heading_yaw") is not None:
                    point["yaw"] = visit["heading_yaw"]
                poses.append(Pose.model_validate(point).model_dump())
            route = None
            if definition["route_ref"]:
                ref = definition["route_ref"]
                route = self.routes.detail(ref["route_id"])["route"]
                if route["revision"] != ref["revision"] or route["map_family"] != family:
                    raise MissionConflict("ROUTE_REVISION_CHANGED")
            return geometry, annotations, poses, route
        except MissionConflict:
            raise
        except Exception as exc:
            raise MissionConflict("EXACT_NAVIGATION_MAP_OR_ROUTE_UNAVAILABLE") from exc

    def _path_validation(self, definition, poses, geometry, annotations, radius):
        try:
            result = validate_route({"map_family": definition["map_family"], "poses": poses, "policy": {"mode": definition["mode"]}}, geometry, annotations, robot_radius_m=radius)
        except SpatialRouteError as exc:
            raise MissionConflict("MAP_FAMILY_OR_GEOMETRY_CHANGED") from exc
        # E0 checks polygon centres. Expand KEEP_OUT conservatively by the
        # circular footprint here, including edges and start/goal connectors.
        extra = []
        spacing = min(geometry.resolution, radius / 2)
        polygons = [p for p in annotations.get("polygons", []) if p.get("type") == "KEEP_OUT"]
        samples = poses if len(poses) > 1 else [poses[0], poses[0]]
        for segment, (left, right) in enumerate(zip(samples, samples[1:])):
            steps = max(1, math.ceil(math.hypot(right["x"]-left["x"], right["y"]-left["y"])/spacing))
            for step in range(steps+1):
                t = step/steps
                x, y = left["x"]+(right["x"]-left["x"])*t, left["y"]+(right["y"]-left["y"])*t
                for polygon in polygons:
                    vertices = polygon.get("vertices", [])
                    for a, b in zip(vertices, vertices[1:]+vertices[:1]):
                        dx, dy = b["x"]-a["x"], b["y"]-a["y"]
                        u = max(0, min(1, ((x-a["x"])*dx+(y-a["y"])*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
                        if math.hypot(x-a["x"]-u*dx, y-a["y"]-u*dy) <= radius and len(extra) < 256:
                            extra.append({"kind": "KEEP_OUT_FOOTPRINT", "segment": segment, "x": x, "y": y})
                            break
        revision = digest(definition)
        result["violations"] = [{**v, "violation_code": v["kind"], "severity": "error", "affected_revision": revision, "remedy": "방문점 또는 경로를 알려진 자유 공간과 제한 영역 밖으로 수정하세요."} for v in (result["violations"]+extra)[:256]]
        result["violation_count"] += len(extra)
        result["valid"] = result["valid"] and not extra
        return result

    def validate(self, identifier, revision):
        return self._validate_entry(self.definition(identifier, revision))

    def _validate_entry(self, entry):
        revision = entry["revision"]
        definition = entry["definition"]
        geometry, annotations, poses, route = self._resolved(entry)
        context = self.context.snapshot()
        radius = context.get("robot_radius_m")
        # Preserve E0's conservative 0.25m authoring approximation when no
        # effective model is available. This fallback is never execution proof.
        radius = max(ROBOT_RADIUS_M, radius) if isinstance(radius, (float, int)) and not isinstance(radius, bool) and math.isfinite(radius) and radius > 0 else ROBOT_RADIUS_M
        connectors = self._path_validation(definition, poses, geometry, annotations, radius)
        endpoints = [self._path_validation(definition, [point], geometry, annotations, radius) for point in poses]
        result = dict(connectors)
        result["valid"] = all(check["valid"] for check in endpoints)
        result["connector_validation"] = {"valid": connectors["valid"], "violations": connectors["violations"], "meaning": "visit connecting lines are authoring guides, actual planned connectors are checked separately"}
        result["violations"] = [v for check in endpoints for v in check["violations"]]
        if route:
            route_result = self._path_validation(definition, route["poses"], geometry, annotations, radius)
            result["valid"] = result["valid"] and route_result["valid"] and route_result["execution"]["reason"] != "SIMPLIFIED_ROUTE_INVALID"
            result["violations"] += route_result["violations"]
        unsupported = []
        if definition["mode"] != "FLEXIBLE" or route and route["policy"]["mode"] != "FLEXIBLE":
            unsupported.append("CONSTRAINT_AUTHORING_ONLY")
        for visit in definition["visits"]:
            for blocked, code in ((visit["kind"] == "PASS_THROUGH", "PASS_THROUGH_UNSUPPORTED"), (visit["action"] != "none", "ACTION_UNAVAILABLE"), (visit["speed"] != "DEFAULT", "SPEED_UNSUPPORTED"), (visit["arrival_tolerance"] is not None, "ARRIVAL_TOLERANCE_UNSUPPORTED")):
                if blocked:
                    unsupported.append(f"{code}:{visit['visit_id']}")
        return {
            "status": "PASS" if result["valid"] and not unsupported else "BLOCKED",
            "scope": "authoring", "evidence_type": "synthetic" if getattr(self.maps, "is_fixture", False) else "software",
            "actual_nav2_run": False, "validation": result,
            "blocking_reasons": unsupported + ([] if result["valid"] else ["AUTHORED_GEOMETRY_INVALID"]),
            "warnings": ["FLEXIBLE may replan between required stops", "KEEP_OUT validation alone does not prove runtime costmap enforcement"],
            "snapshot_pins": {"definition_revision": revision, "map_family": definition["map_family"], "annotation_revision": definition["annotation_revision"], "route_ref": definition["route_ref"], "context_revision": context["navigation_context_revision"], "planner_config_digest": context["planner_config_digest"], "footprint_revision": context["footprint_revision"]},
            "requested": {"speed": [v["speed"] for v in definition["visits"]], "tolerance": [v["arrival_tolerance"] for v in definition["visits"]]},
            "effective": {"speed": "DEFAULT", "arrival": "NAV2_DEFAULT", "authoring_radius_m": radius},
            "zone_support": {"KEEP_OUT": {"authoring": "checked", "planning": "checked_on_result", "runtime": "proven" if context["runtime_policy_enforced"] else "unavailable"}, "SLOW_ZONE": {"runtime": "unsupported"}, "WAIT_ZONE": {"runtime": "unsupported"}},
            "execution_readiness": {"status": "BLOCKED" if context["blocking_reasons"] or unsupported or not result["valid"] else "READY", "blocking_reasons": context["blocking_reasons"]+unsupported},
            "resolved_poses": poses,
        }

    async def preview(self, identifier, body):
        # Native planning shares the map/resource window, but claims no motion
        # owner. MS lifecycle cannot replace the planner map during this call.
        async with self.coordinator._coordination_lock:
            context = self.context.snapshot()
            if "SLAM_CONTEXT_BUSY" in context["blocking_reasons"]:
                raise MissionConflict("SLAM_CONTEXT_BUSY")
            entry = self.definition(identifier, body.revision)
            family = entry["definition"]["map_family"]
            if context["navigation_map"] != {"id": family["occupancy_map_id"], "revision": family["occupancy_revision"]}:
                raise MissionConflict("PLANNER_MAP_MISMATCH")
            return await self._preview_locked(identifier, body)

    async def _preview_locked(self, identifier, body):
        entry = self.definition(identifier, body.revision)
        report = await asyncio.to_thread(self.validate, identifier, body.revision)
        context = self.context.snapshot()
        start = body.start.model_dump() if body.start is not None else context["operational_pose"]
        if start is None:
            raise MissionConflict("FRESH_OPERATIONAL_POSE_REQUIRED")
        self._generation += 1
        generation = self._generation
        if report["blocking_reasons"]:
            return {**report, "start_source": body.start_source, "start_pose": start, "snapshot_seq": context.get("snapshot_seq"), "legs": [], "length_m": None, "eta_seconds": None, "plan_generation": generation}
        geometry, annotations, poses, _ = self._resolved(entry)
        legs, actual = [], True
        current = start
        for index, target in enumerate(poses):
            planned = await self.planner.plan(current, target)
            points = self._planned_points(planned)
            if planned.get("frame") != "map" or not 1 <= len(points) <= 4096:
                raise MissionConflict("PLANNER_RESULT_INVALID")
            # Include both connectors; don't trust the planner's tolerance to
            # have reached exactly the requested endpoint.
            full = [current, *points, target]
            checked = self._path_validation(entry["definition"], full, geometry, annotations, report["effective"]["authoring_radius_m"])
            if not checked["valid"]:
                return {**report, "status": "BLOCKED", "scope": "planner", "blocking_reasons": ["PLANNED_PATH_INVALID"], "violations": checked["violations"], "legs": legs, "actual_nav2_run": planned.get("actual_nav2_run") is True, "length_m": None, "eta_seconds": None, "plan_generation": generation}
            actual = actual and planned.get("actual_nav2_run") is True
            legs.append({"visit_id": entry["definition"]["visits"][index]["visit_id"], "poses": full, "length_m": route_length(full), "evidence_type": planned.get("evidence_type")})
            current = target
        if generation != self._generation or self.definition(identifier)["revision"] != body.revision or self.context.snapshot()["navigation_context_revision"] != context["navigation_context_revision"]:
            raise MissionConflict("PREVIEW_CONTEXT_CHANGED")
        return {**report, "status": "PASS", "scope": "planner", "start_source": body.start_source, "start_pose": start, "snapshot_seq": context.get("snapshot_seq"), "actual_nav2_run": actual, "evidence_type": "native_planner" if actual else "synthetic", "legs": legs, "length_m": sum(leg["length_m"] for leg in legs), "eta_seconds": None, "plan_generation": generation, "observed_at": utc(), "notice": "계획 시점 결과 · 실행 중 재계획 가능"}

    async def compile(self, identifier, body):
        async def operation():
            report = await asyncio.to_thread(self.validate, identifier, body.revision)
            if report["blocking_reasons"]:
                raise MissionConflict(",".join(report["blocking_reasons"]))
            entry = self.definition(identifier, body.revision)
            return {"compiled": {"definition_id": identifier, "definition_revision": body.revision, "visits": entry["definition"]["visits"], "snapshot_pins": report["snapshot_pins"], "mode": "FLEXIBLE", "start_sent": False}, "validation": report}
        return await self._transaction(body.request_id, {"compile": identifier, **body.model_dump()}, operation)

    def route_draft(self, route_id):
        try:
            route = self.routes.detail(route_id)["route"]
        except SpatialRouteError as exc:
            raise MissionConflict("ROUTE_UNAVAILABLE") from exc
        points = select_execution_waypoints(route["poses"])
        return {"draft": {"label": route["label"], "map_family": route["map_family"], "annotation_revision": self.maps.annotations(route["map_family"]["occupancy_map_id"])["annotation_revision"], "mode": route["policy"]["mode"], "route_ref": {"route_id": route_id, "revision": route["revision"]}, "visits": [{"visit_id": secrets.token_hex(16), "label": f"방문 {i+1}", "target": "mission_local_pose", "pose": p, "kind": "STOP"} for i, p in enumerate(points)]}, "notice": "선호 geometry는 원본 경로에 보존됩니다. 표시된 STOP 목록을 검토해 저장하세요. compile은 이동 명령이 아닙니다."}

    async def create_run(self, identifier, body):
        async def operation():
            if len(self.data["runs"]) >= 32:
                raise MissionConflict("RUN_HISTORY_FULL: explicit archival required")
            report = await asyncio.to_thread(self.validate, identifier, body.revision)
            if report["blocking_reasons"]:
                raise MissionConflict(",".join(report["blocking_reasons"]))
            entry = self.definition(identifier, body.revision)
            d = entry["definition"]
            waypoints = []
            for visit in d["visits"]:
                waypoints.append({"visit_id": visit["visit_id"], "annotation_id": visit["annotation_id"], "mission_local_pose": visit["pose"], "label": visit["label"], "heading_yaw": visit["heading_yaw"], "hold_seconds": visit["hold_seconds"], "arrival_tolerance": visit["arrival_tolerance"], "requires_operator_confirmation": visit["requires_operator_confirmation"], "after_arrival_confirmation": visit["after_arrival_confirmation"]})
            created = await self.coordinator.create(label=d["label"], map_id=d["map_family"]["occupancy_map_id"], map_revision=d["map_family"]["occupancy_revision"], annotation_revision=d["annotation_revision"], waypoints=waypoints, context_revision=report["snapshot_pins"]["context_revision"])
            run = {"id": created["mission"]["id"], "definition_id": identifier, "definition_revision": body.revision, "definition": d, "snapshot_pins": report["snapshot_pins"], "created_at": utc(), "source_sha": None, "runtime_sha": None, "provenance_status": "runtime build identity unavailable", "events": [], "trajectory": [], "preview": None, "live_plan": {"status": "unavailable", "reason": "NAV2_RUNTIME_PATH_WITH_PROVENANCE_UNAVAILABLE"}}
            self.data["runs"][run["id"]] = run
            self._save()
            return self.run(run["id"])
        return await self._transaction(body.request_id, {"create_run": identifier, **body.model_dump()}, operation)

    def run(self, identifier):
        run = self.data["runs"].get(identifier)
        if run is None:
            raise MissionNotFound("mission run was not found")
        return {"run": copy.deepcopy(run), "mission": self.coordinator.snapshot(identifier)["mission"]}

    def export_run(self, identifier):
        # History is a read-only artifact, never executable resume state.
        result = self.run(identifier)
        run_fields = {"id", "definition_id", "definition_revision", "definition", "snapshot_pins", "created_at", "source_sha", "runtime_sha", "provenance_status", "events", "trajectory", "preview", "live_plan", "last_state", "last_phase", "visit_results", "started_at", "completed_at", "outcome", "logs"}
        mission_fields = {"id", "label", "state", "phase", "outcome", "current_index", "completed_count", "waypoints", "started_at", "completed_at", "hold_remaining", "pause_reason", "error", "logs"}
        return {"schema": "mission-history.v1", "executable": False, "run": {k:v for k,v in result["run"].items() if k in run_fields}, "mission": {k:v for k,v in result["mission"].items() if k in mission_fields}}

    def runs(self):
        return {"runs": [self.run(k) for k in reversed(self.data["runs"])]}

    def observe(self, mission):
        run = self.data["runs"].get(mission["id"])
        if run is None:
            return
        now = time.monotonic()
        previous = self._last_observation.get(mission["id"])
        terminal_changed = run.get("last_state") != mission["state"]
        if previous is not None and now - previous < 0.5 and not terminal_changed:
            return
        self._last_observation[mission["id"]] = now
        run["last_state"] = mission["state"]
        run["last_phase"] = mission.get("phase")
        run["visit_results"] = mission["waypoints"]
        run["started_at"] = mission["started_at"]
        run["completed_at"] = mission["completed_at"]
        run["outcome"] = mission.get("outcome")
        run["logs"] = mission["logs"]
        context = self.context.snapshot()
        point = context.get("operational_pose")
        if point is not None and mission["ownership_active"]:
            epoch = context["navigation_context_revision"]
            last = run["trajectory"][-1] if run["trajectory"] else None
            discontinuity = last is not None and math.hypot(point["x"]-last["x"], point["y"]-last["y"]) > 1.0
            if previous is None or now - previous > 2.0 or discontinuity:
                run["trajectory_epoch"] = secrets.token_hex(8)
            run["trajectory"].append({**point, "observed_at": utc(), "epoch": epoch + ":" + run.setdefault("trajectory_epoch", secrets.token_hex(8)), "evidence_type": "operational_pose_observation"})
            run["trajectory"] = run["trajectory"][-256:]
        elif previous is not None:
            run["trajectory_epoch"] = secrets.token_hex(8)
        self._save()

    def require_run_context(self, mission):
        run = self.data["runs"].get(mission["id"])
        if run is None:
            raise MissionConflict("MISSION_RUN_NOT_BOUND")
        context = self.context.snapshot()
        if context["navigation_context_revision"] != run["snapshot_pins"]["context_revision"]:
            raise MissionConflict("RUN_CONTEXT_CHANGED: create a new run after revalidation")
        # Pose readiness is checked by the existing navigation owner. This
        # guard also runs while moving, when can_send_goal may legitimately be false.
        reasons = [reason for reason in context["blocking_reasons"] if reason != "GOAL_ADMISSION_UNAVAILABLE"]
        if reasons:
            raise MissionConflict(",".join(reasons))
        self._resolved({"definition": run["definition"]})

    @staticmethod
    def _planned_points(plan):
        raw = plan.get("poses")
        if plan.get("frame") != "map" or not isinstance(raw, list) or not 1 <= len(raw) <= 4096:
            raise MissionConflict("PLANNER_RESULT_INVALID")
        try:
            return [Pose.model_validate(point).model_dump() for point in raw]
        except (TypeError, ValueError) as exc:
            raise MissionConflict("PLANNER_RESULT_INVALID") from exc

    async def preflight_dispatch(self, mission):
        self.require_run_context(mission)
        run = self.data["runs"][mission["id"]]
        report = await asyncio.to_thread(self._validate_entry, {"revision": run["definition_revision"], "definition": run["definition"]})
        context = self.context.snapshot()
        if report["blocking_reasons"] or context["blocking_reasons"]:
            raise MissionConflict(",".join(report["blocking_reasons"] + context["blocking_reasons"]))
        geometry, annotations, poses, _ = self._resolved({"definition": run["definition"]})
        start = context["operational_pose"]
        target = poses[mission["current_index"]]
        plan = await self.planner.plan(start, target)
        if plan.get("actual_nav2_run") is not True:
            raise MissionConflict("NATIVE_START_PLAN_REQUIRED")
        points = [start, *self._planned_points(plan), target]
        checked = self._path_validation(run["definition"], points, geometry, annotations, report["effective"]["authoring_radius_m"])
        if not checked["valid"]:
            raise MissionConflict("LIVE_START_PATH_INVALID")
        if checked.get("zones"):
            raise MissionConflict("ZONE_BEHAVIOR_UNSUPPORTED: SLOW_ZONE/WAIT_ZONE runtime behavior is unavailable")
        self.require_run_context(mission)
        run["preview"] = {"legs": [{"visit_id": run["definition"]["visits"][mission["current_index"]]["visit_id"], "poses": points}], "actual_nav2_run": True, "observed_at": utc(), "scope": "dispatch_preflight", "notice": "실행 직전 계획 · Nav2 내부 재계획 가능"}
        self._save()

    async def action(self, identifier, action, body):
        async def operation():
            run = self.data["runs"].get(identifier)
            if run is None:
                raise MissionNotFound("mission run was not found")
            mission = self.coordinator.snapshot(identifier)["mission"]
            if action in {"start", "resume", "retry", "skip"}:
                self.require_run_context(mission)
                token = mission.get("confirmation_token")
                if action == "resume" and token is not None and body.confirmation_token != token:
                    raise MissionConflict("CONFIRMATION_TOKEN_STALE")
            methods = {"start": self.coordinator.start, "pause": self.coordinator.pause, "resume": self.coordinator.resume, "abort": self.coordinator.abort, "retry": self.coordinator.retry, "skip": self.coordinator.skip}
            if action not in methods:
                raise MissionValidationError("unsupported mission action")
            if action == "resume":
                result = await methods[action](identifier, confirmation_token=body.confirmation_token, admission=self._admission)
            elif action in {"start", "retry", "skip"}:
                result = await methods[action](identifier, admission=self._admission)
            else:
                result = await methods[action](identifier)
            run = self.data["runs"][identifier]
            run["event_seq"] = run.get("event_seq", 0) + 1
            run["events"].append({"seq": run["event_seq"], "action": action, "at": utc(), "phase": result["mission"].get("phase"), "physical_stop_observed": None})
            run["events"] = run["events"][-200:]
            warning = result.get("audit_warning")
            try:
                self._save()
            except MissionUnavailable:
                if action not in {"pause", "abort"}:
                    raise
                warning = "STOP_APPLIED_WITHOUT_DURABLE_HISTORY"
            response = self.run(identifier)
            if warning:
                response["audit_warning"] = warning
            return response
        return await self._transaction(body.request_id, {"run": identifier, "action": action, **body.model_dump()}, operation, safety=action in {"pause", "abort"})
