import ast
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from robot_dashboard.api.models import SpatialRouteCreateRequest
from robot_dashboard.saved_maps import NavigationMapSnapshot
from robot_dashboard.spatial_routes import (
    MAX_EXECUTION_WAYPOINTS,
    MAX_RAW_POSES,
    SpatialRouteCatalog,
    SpatialRouteConflict,
    SpatialRouteFormatError,
    SpatialRouteNotFound,
    SpatialRouteUnavailable,
    enforce_max_segment_length,
    normalize_route,
    remove_duplicate_poses,
    route_length,
    select_execution_waypoints,
    simplify_rdp,
    unwrap_yaws,
    validate_route,
    wrap_yaw,
)


MAP_ID = "1" * 24
MAP_REVISION = "2" * 64
FAMILY_ID = "3" * 24
FAMILY_REVISION = "4" * 64
PCD_ID = "5" * 24
PCD_REVISION = "6" * 64


def family(**changes):
    value = {
        "family_id": FAMILY_ID,
        "family_revision": FAMILY_REVISION,
        "pcd_map_id": PCD_ID,
        "pcd_revision": PCD_REVISION,
        "occupancy_map_id": MAP_ID,
        "occupancy_revision": MAP_REVISION,
    }
    value.update(changes)
    return value


def policy(mode="FLEXIBLE"):
    return {
        "mode": mode,
        "corridor_width_m": 0.5,
        "blocked_behavior": "REPLAN",
    }


def pose(x=2.0, y=2.0, yaw=0.0, **changes):
    value = {"x": x, "y": y, "yaw": yaw}
    value.update(changes)
    return value


class MapProvider:
    def __init__(self):
        occupancy = bytearray([0] * 400)
        # ROS row-major cells: unknown at (8, 8), occupied at (10, 10).
        occupancy[8 * 20 + 8] = 255
        occupancy[10 * 20 + 10] = 100
        self.geometry = NavigationMapSnapshot(
            map_id=MAP_ID,
            revision=MAP_REVISION,
            name="arena",
            frame_id="map",
            yaml_path=Path("private.yaml"),
            image_path=Path("private.pgm"),
            width=20,
            height=20,
            resolution=0.5,
            origin=(0.0, 0.0, 0.0),
            occupancy=bytes(occupancy),
            family_id=FAMILY_ID,
            family_revision=FAMILY_REVISION,
            source_pcd_id=PCD_ID,
            source_pcd_revision=PCD_REVISION,
            occupancy_map_id=MAP_ID,
            occupancy_map_revision=MAP_REVISION,
        )
        self.document = {
            "map_id": MAP_ID,
            "map_revision": MAP_REVISION,
            "annotation_revision": "7" * 64,
            "points": [],
            "polygons": [],
        }

    def route_geometry(self, map_id, expected_revision):
        if (map_id, expected_revision) != (MAP_ID, MAP_REVISION):
            raise ValueError("map revision unavailable")
        return self.geometry

    def annotations(self, map_id):
        if map_id != MAP_ID:
            raise ValueError("map unavailable")
        return self.document


def normalized(poses=None, mode="FLEXIBLE", **changes):
    values = {
        "route_id": "8" * 24,
        "label": "Arena route",
        "map_family": family(),
        "authoring_source": "POINT_CLICK",
        "parent_revision": None,
        "policy": policy(mode),
        "poses": [pose(2.0, 2.0), pose(3.0, 2.0)] if poses is None else poses,
        "created_at": "2026-09-08T00:00:00.000Z",
    }
    values.update(changes)
    return normalize_route(**values)


class SpatialRoutePureTests(unittest.TestCase):
    def setUp(self):
        self.maps = MapProvider()

    def test_schema_is_strict_bounded_finite_and_revisioned(self):
        route = normalized()
        self.assertEqual(len(route["revision"]), 64)
        self.assertEqual(route, normalized())
        self.assertNotIn("path", json.dumps(route).lower())
        invalid = (
            {"poses": []},
            {"poses": [pose()] * (MAX_RAW_POSES + 1)},
            {"poses": [pose(x=float("nan"))]},
            {"poses": [{**pose(), "script": "no"}]},
            {"map_family": family(family_revision="x" * 64)},
            {"policy": {**policy(), "mode": "EXECUTE"}},
            {"label": "x" * 65},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises(SpatialRouteFormatError):
                    normalized(**changes)

    def test_free_route_and_modes_are_nonexecuting_artifacts(self):
        result = validate_route(normalized(), self.maps.geometry, self.maps.document)
        self.assertTrue(result["valid"])
        self.assertTrue(result["execution"]["eligible"])
        self.assertFalse(result["execution"]["mission_created"])
        self.assertFalse(result["execution"]["route_executed"])
        self.assertGreaterEqual(result["minimum_clearance_m"], 0.25)
        for mode in ("CORRIDOR", "STRICT"):
            result = validate_route(normalized(mode=mode), self.maps.geometry, self.maps.document)
            self.assertTrue(result["valid"])
            self.assertFalse(result["execution"]["eligible"])
            self.assertEqual(result["execution"]["reason"], "MODE_AUTHORING_ONLY")

    def test_unknown_occupied_boundary_and_segment_are_rejected(self):
        cases = {
            "UNKNOWN": [pose(4.25, 4.25)],
            "OCCUPIED": [pose(5.25, 5.25)],
            "BOUNDARY": [pose(20.0, 20.0)],
            "segment": [pose(3.0, 5.25), pose(6.0, 5.25)],
        }
        for expected, poses in cases.items():
            with self.subTest(expected=expected):
                result = validate_route(normalized(poses=poses), self.maps.geometry, self.maps.document)
                self.assertFalse(result["valid"])
                kinds = {item["kind"] for item in result["violations"]}
                if expected == "segment":
                    self.assertTrue({"OCCUPIED", "FOOTPRINT_CLEARANCE"} & kinds)
                    self.assertTrue(any("segment" in item for item in result["violations"]))
                else:
                    self.assertIn(expected, kinds)

    def test_keep_out_rejects_and_slow_wait_zones_are_tagged(self):
        vertices = [{"x": 1.5, "y": 1.5}, {"x": 3.5, "y": 1.5}, {"x": 3.5, "y": 3.5}, {"x": 1.5, "y": 3.5}]
        for kind in ("KEEP_OUT", "SLOW_ZONE", "WAIT_ZONE"):
            self.maps.document["polygons"] = [{"id": kind[0].lower() * 24, "type": kind, "name": kind, "vertices": vertices}]
            result = validate_route(normalized(poses=[pose(2.0, 2.0)]), self.maps.geometry, self.maps.document)
            if kind == "KEEP_OUT":
                self.assertFalse(result["valid"])
                self.assertEqual(result["violations"][0]["kind"], "KEEP_OUT")
            else:
                self.assertTrue(result["valid"])
                self.assertEqual(result["zones"][0]["type"], kind)

    def test_family_and_annotation_revision_mismatch_fail_closed(self):
        with self.assertRaises(SpatialRouteConflict):
            validate_route(normalized(map_family=family(family_revision="9" * 64)), self.maps.geometry, self.maps.document)
        document = dict(self.maps.document, map_revision="9" * 64)
        with self.assertRaises(SpatialRouteConflict):
            validate_route(normalized(), self.maps.geometry, document)

    def test_simplification_is_deterministic_and_preserves_final_yaw(self):
        values = [pose(index * 0.1, 2.0 + (0.001 if index % 2 else 0.0), yaw=0.0) for index in range(100)]
        values[-1]["yaw"] = 3.0
        first = simplify_rdp(values, 0.01)
        self.assertEqual(first, simplify_rdp(values, 0.01))
        self.assertEqual(first[-1]["yaw"], 3.0)
        self.assertLess(len(first), len(values))
        bounded = select_execution_waypoints(values)
        self.assertLessEqual(len(bounded), MAX_EXECUTION_WAYPOINTS)
        self.assertEqual(bounded[-1]["yaw"], 3.0)
        self.assertGreater(route_length(values), 0.0)

        # The maximum schema size must not depend on Python recursion depth.
        zigzag = [pose(index * 0.01, 2.0 + (0.1 if index % 2 else 0.0)) for index in range(MAX_RAW_POSES)]
        self.assertLessEqual(len(select_execution_waypoints(zigzag)), MAX_EXECUTION_WAYPOINTS)

    def test_yaw_duplicate_and_segment_utilities(self):
        values = unwrap_yaws([3.1, -3.1, -3.0])
        self.assertLess(max(abs(right - left) for left, right in zip(values, values[1:])), 0.2)
        self.assertAlmostEqual(wrap_yaw(3.0 + 2 * 3.141592653589793), 3.0)
        deduplicated = remove_duplicate_poses([pose(), pose(yaw=1.0), pose(1.0, 2.0)])
        self.assertEqual(len(deduplicated), 2)
        self.assertEqual(deduplicated[0]["yaw"], 1.0)
        enforced = enforce_max_segment_length([pose(1.0, 2.0), pose(2.0, 2.0, yaw=1.0)], 0.25)
        self.assertEqual(len(enforced), 5)
        self.assertEqual(enforced[-1]["yaw"], 1.0)

    def test_validation_work_is_bounded(self):
        with self.assertRaisesRegex(SpatialRouteFormatError, "too many"):
            validate_route(
                normalized(poses=[pose(0.5, 0.5), pose(1_000.0, 0.5)]),
                replace(self.maps.geometry, resolution=0.001),
                self.maps.document,
            )

    def test_simplified_execution_projection_is_revalidated(self):
        safe = normalized(poses=[pose(2.0 + index * 0.01, 2.0) for index in range(33)])
        shortcut = [pose(3.0, 5.25), pose(6.0, 5.25)]
        with mock.patch(
            "robot_dashboard.spatial_routes.select_execution_waypoints",
            return_value=shortcut,
        ):
            result = validate_route(safe, self.maps.geometry, self.maps.document)
        self.assertTrue(result["valid"])
        self.assertFalse(result["execution"]["eligible"])
        self.assertEqual(result["execution"]["reason"], "SIMPLIFIED_ROUTE_INVALID")


class SpatialRouteCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "routes"
        self.root.mkdir(mode=0o700)
        identifiers = iter(("a" * 24, "b" * 24, "c" * 24))
        times = iter(("2026-09-08T00:00:00.000Z", "2026-09-08T00:01:00.000Z", "2026-09-08T00:02:00.000Z"))
        self.catalog = SpatialRouteCatalog(self.root, MapProvider(), identifier_factory=lambda: next(identifiers), clock=lambda: next(times))

    def tearDown(self):
        self.temporary.cleanup()

    def create(self, **changes):
        values = {"label": "Route one", "map_family": family(), "authoring_source": "POINT_CLICK", "policy": policy(), "poses": [pose(2.0, 2.0), pose(3.0, 2.0)]}
        values.update(changes)
        return self.catalog.create(**values)

    def test_create_update_copy_delete_are_cas_and_path_free(self):
        created = self.create()
        route_id = created["route"]["route_id"]
        revision = created["route"]["revision"]
        self.assertEqual(self.catalog.list_snapshot()["count"], 1)
        self.assertEqual(self.catalog.detail(route_id), created)
        for path in self.root.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), json.dumps(created))

        updated = self.catalog.update(
            route_id, base_revision=revision, label="Route two", map_family=family(),
            authoring_source="POINT_CLICK", policy=policy(), poses=[pose(2.0, 2.0), pose(3.5, 2.0)],
        )
        self.assertEqual(updated["route"]["authoring"]["parent_revision"], revision)
        with self.assertRaises(SpatialRouteConflict):
            self.catalog.update(route_id, base_revision=revision, label="stale", map_family=family(), authoring_source="POINT_CLICK", policy=policy(), poses=[pose()])

        copied = self.catalog.copy(route_id, base_revision=updated["route"]["revision"], label="Copy")
        self.assertEqual(copied["route"]["authoring"]["source"], "IMPORT")
        self.assertEqual(self.catalog.list_snapshot()["count"], 2)
        deleted = self.catalog.delete(route_id, base_revision=updated["route"]["revision"])
        self.assertTrue(deleted["deleted"])
        self.assertFalse(deleted["route_executed"])
        with self.assertRaises(SpatialRouteNotFound):
            self.catalog.detail(route_id)
        self.assertTrue(list(self.root.glob(f"{route_id}.*.json")), "immutable audit revisions must remain")

    def test_atomic_pointer_failure_does_not_replace_current(self):
        created = self.create()
        route_id = created["route"]["route_id"]
        revision = created["route"]["revision"]
        real_replace = os.replace

        def fail_current(source, target):
            if str(target).endswith(".current"):
                raise OSError("injected")
            return real_replace(source, target)

        with mock.patch("robot_dashboard.spatial_routes.os.replace", side_effect=fail_current):
            with self.assertRaises(SpatialRouteUnavailable):
                self.catalog.update(route_id, base_revision=revision, label="not published", map_family=family(), authoring_source="POINT_CLICK", policy=policy(), poses=[pose(2.0, 2.0)])
        self.assertEqual(self.catalog.detail(route_id)["route"]["revision"], revision)
        self.assertFalse(list(self.root.glob(".*.current.*")))

    def test_symlink_root_and_entries_fail_closed(self):
        alias = Path(self.temporary.name) / "alias"
        alias.symlink_to(self.root)
        with self.assertRaises(SpatialRouteUnavailable):
            SpatialRouteCatalog(alias, MapProvider())
        created = self.create()
        route_id = created["route"]["route_id"]
        current = self.root / f"{route_id}.current"
        current.unlink()
        current.symlink_to(next(self.root.glob(f"{route_id}.*.json")))
        with self.assertRaises(SpatialRouteNotFound):
            self.catalog.detail(route_id)


class SpatialRouteRequestTests(unittest.TestCase):
    @staticmethod
    def payload():
        return {"label": "API route", "map_family": family(), "authoring_source": "POINT_CLICK", "policy": policy(), "poses": [pose(2.0, 2.0), pose(3.0, 2.0)]}

    def test_request_schema_forbids_extra_and_bounds_poses(self):
        self.assertEqual(len(SpatialRouteCreateRequest.model_validate(self.payload()).poses), 2)
        for changes in ({"script": "forbidden"}, {"poses": [pose()] * (MAX_RAW_POSES + 1)}):
            invalid = self.payload()
            invalid.update(changes)
            with self.assertRaises(ValidationError):
                SpatialRouteCreateRequest.model_validate(invalid)

    def test_router_registers_exact_crud_and_gates_every_mutation(self):
        path = Path(__file__).resolve().parents[1] / "robot_dashboard" / "api" / "routers" / "spatial_routes.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        routes = {}
        for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
            for decorator in function.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.args and isinstance(decorator.args[0], ast.Constant):
                    routes[(decorator.func.attr.upper(), decorator.args[0].value)] = function
        self.assertEqual(
            set(routes),
            {
                ("GET", "/api/v1/routes"),
                ("POST", "/api/v1/routes"),
                ("GET", "/api/v1/routes/{route_id}"),
                ("PATCH", "/api/v1/routes/{route_id}"),
                ("DELETE", "/api/v1/routes/{route_id}"),
                ("POST", "/api/v1/routes/{route_id}/copy"),
            },
        )
        for (method, _), function in routes.items():
            if method == "GET":
                continue
            called = {
                node.func.id
                for node in ast.walk(function)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            self.assertIn("require_same_origin", called)
            self.assertIn("require_competition_unlocked", called)


if __name__ == "__main__":
    unittest.main()
