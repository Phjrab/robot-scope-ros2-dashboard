import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from types import SimpleNamespace
from schematic_offline_server import make_app
from schematic_fixtures import install_test_templates
from robot_dashboard.route_planner.schematic import SchematicError, digest, missing_field, segment_covered, rect, template, validate_layout
from robot_dashboard.route_planner.schematic_session import SchematicSession
from robot_dashboard.route_planner.state_store import RoutePlannerStorageError


def order(destination="COEX", quantity=1):
    restaurant, menu = ("DOMINO", "CHEESE_PIZZA") if destination == "WHIMOON" else ("HANSOT", "CHICKEN_MAYO")
    return dict(label="무주행 도식 주문", locked=True, orders=[dict(destination_id=destination, lines=[dict(sequence=1, restaurant_id=restaurant, menu_id=menu, quantity=quantity)])])


class TestClient:
    """Exercise the real ASGI application without adding a test HTTP dependency."""
    def __init__(self, app, headers): self.app, self.headers = app, headers
    def close(self): pass
    def get(self, path, **kwargs): return self.request("GET", path, **kwargs)
    def post(self, path, **kwargs): return self.request("POST", path, **kwargs)
    def put(self, path, **kwargs): return self.request("PUT", path, **kwargs)
    def request(self, method, path, **kwargs):
        headers = {"host": "testserver", "content-type": "application/json", **self.headers, **kwargs.get("headers", {})}
        body = kwargs.get("content", json.dumps(kwargs.get("json", {})).encode())
        async def run():
            messages = []
            async def receive(): return {"type": "http.request", "body": body, "more_body": False}
            async def send(message): messages.append(message)
            await self.app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "server": ("testserver", 80), "client": ("127.0.0.1", 1), "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}, receive, send)
            text = b"".join(m.get("body", b"") for m in messages).decode()
            return SimpleNamespace(status_code=messages[0]["status"], text=text, json=lambda: json.loads(text))
        return asyncio.run(run())


class SchematicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.assets_patch = patch("robot_dashboard.route_planner.schematic.ASSETS", install_test_templates(self.root / "test-assets"))
        self.assets_patch.start()
        self.addCleanup(self.assets_patch.stop)
        self.session = SchematicSession(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def command(self, action, data=None):
        s = self.session.snapshot()
        return self.session.execute(action, s["revision"], s["context"], data or {})

    def ready(self, start="COEX", destination="COEX"):
        self.command("CONTEXT", {"context": "DEMO"})
        self.command("ORDER", {"order": order(destination)})
        self.command("START_POINT", {"node_id": start})
        s = self.command("RECOMMEND")
        route = s["recommendations"][0]
        pin = {"route_id": route["id"], "route_revision": route["revision"]}
        self.command("SELECT", pin)
        self.command("START", pin)
        return route

    def event(self, kind="STEP", venue=None, event_id=None):
        s = self.session.snapshot(); g = s["guidance"]
        r = next(r for r in s["recommendations"] if r["id"] == s["selected_route_id"])
        data = dict(event_id=event_id or f'event-{s["revision"]:08d}', route_id=r["id"], route_revision=r["revision"], expected_progress_revision=g["progress_revision"], expected_segment_index=g["current_segment_index"])
        if venue: data["venue_id"] = venue
        return self.command(kind, data)

    def test_all_four_starts_complete_without_pose_and_return_to_start(self):
        for start in ["COEX", "WHIMOON", "GANGNAM_POLICE", "GTX_SITE"]:
            self.ready(start, start)
            for _ in range(100):
                s = self.session.snapshot(); g = s["guidance"]; r = s["recommendations"][0]
                if not g["active"]: break
                pending = [p for p in r["stops"] if p["after_segment"] == g["current_segment_index"] and p["venue_id"] not in g["completed_pickups"] + g["completed_dropoffs"]]
                self.event(pending[0]["kind"], pending[0]["venue_id"]) if pending else self.event()
            self.assertEqual(self.session.snapshot()["guidance"]["state"], "COMPLETE")
            self.assertEqual(self.session.snapshot()["guidance"]["cargo"], 0)
            self.assertEqual(r["node_ids"][0], r["node_ids"][-1])
            self.command("UNLOCK")

    def test_relative_units_deterministic_bounded_and_no_underpass(self):
        route = self.ready()
        self.command("END")
        routes = self.command("RECOMMEND")["recommendations"]
        self.assertEqual(route, routes[0])
        self.assertLessEqual(len(routes), 3)
        for r in routes:
            self.assertIsNone(r["distance_m"]); self.assertIsNone(r["eta_s"])
            self.assertFalse(r["motion_authority"]); self.assertFalse(r["control_authority"])
            self.assertTrue(all(e["type"] != "UNDERPASS" and e["signal_state"] == "UNKNOWN" for e in r["segments"]))

    def test_field_empty_separate_and_cannot_approve_or_start(self):
        self.ready(); self.command("END")
        s = self.command("CONTEXT", {"context": "FIELD"})
        self.assertIsNone(s["order"]); self.assertIsNone(s["approval"])
        self.assertTrue(all(b["dock_point_px"] is None for b in s["layout"]["bindings"]))
        self.assertGreater(len(s["missing"]), 20)
        for action, data in [("APPROVE", {"reviewer": "tester", "layout_revision": s["layout_revision"]}), ("RECOMMEND", {})]:
            with self.assertRaises(SchematicError): self.command(action, data)

    def test_revision_idempotency_duplicate_and_stale(self):
        r = self.ready(); s = self.session.snapshot()
        data = dict(event_id="duplicate-0001", route_id=r["id"], route_revision=r["revision"], expected_progress_revision=0, expected_segment_index=0)
        first = self.session.execute("STEP", s["revision"], "DEMO", data)
        self.assertEqual(first, self.session.execute("STEP", s["revision"], "DEMO", data))
        with self.assertRaises(SchematicError): self.session.execute("STEP", s["revision"], "DEMO", {**data, "event_id": "other-tab-0001"})
        with self.assertRaises(SchematicError): self.command("STEP", {**data, "event_id": ""})
        with self.assertRaises(SchematicError): self.command("STEP", {**data, "expected_segment_index": 9})

    def test_pickup_delivery_and_active_context_gates(self):
        self.ready()
        for kind, venue in [("PICKUP", "HANSOT"), ("DROPOFF", "COEX")]:
            with self.assertRaises(SchematicError): self.event(kind, venue)
        for action, data in [("CONTEXT", {"context": "FIELD"}), ("LAYOUT", {"layout": template("DEMO")}), ("ORDER", {"order": order()})]:
            with self.assertRaises(SchematicError): self.command(action, data)

    def test_restart_does_not_resume_and_saved_records_remain(self):
        self.ready(); self.event()
        self.session = SchematicSession(self.root)
        s = self.session.snapshot()
        self.assertFalse(s["guidance"]["active"]); self.assertEqual(s["guidance"]["state"], "STALE")
        self.assertIsNone(s["guidance"]["operator_point"]); self.assertIsNotNone(s["order"])
        self.assertEqual(s["recommendations"], [])

    def test_layout_approval_revision_invalidation_and_confirmed_rules(self):
        self.command("CONTEXT", {"context": "FIELD"})
        layout = template("DEMO")  # TEST FIXTURE ONLY: never imported by the FIELD UI.
        layout.update(rules_profile="MANUAL_PREPARED_2_CONFIRMED", static_reference_allowed=True)
        for b in layout["bindings"]: b["dock_yaw_rad"] = 0.0
        self.assertEqual(missing_field(layout), [])
        s = self.command("LAYOUT", {"layout": layout})
        s = self.command("APPROVE", {"reviewer": "test fixture reviewer", "layout_revision": s["layout_revision"]})
        self.assertTrue(s["field_approved"])
        self.command("ORDER", {"order": order(quantity=3)})
        self.command("START_POINT", {"node_id": "COEX"})
        with self.assertRaises(SchematicError): self.command("RECOMMEND")
        layout["nodes"][0]["label"] = "changed"
        self.assertFalse(self.command("LAYOUT", {"layout": layout})["field_approved"])

    def test_full_segment_geometry_and_invalid_schema(self):
        self.assertFalse(segment_covered([0, 0], [10, 10], [rect(0, 0, 2, 2), rect(8, 8, 10, 10)]))
        self.assertFalse(segment_covered([0, 1], [10, 1], [rect(0, 0, 4.999, 2), rect(5.001, 0, 10, 2)]))
        mutations = [lambda l: l.update(field_approved=True), lambda l: l["nodes"][0].update(x_px=float("nan")), lambda l: l["nodes"][0].update(id="../evil"), lambda l: l["nodes"].append(copy.deepcopy(l["nodes"][0])), lambda l: l["corner_zones"].update(A="ZONE2"), lambda l: l["edges"][0].update(polyline_px=[[220, 146], [825, 666]]), lambda l: [e.update(enabled=False) for e in l["edges"]], lambda l: l["edges"][-1].update(enabled=True)]
        for mutate in mutations:
            l = template("DEMO"); mutate(l)
            with self.assertRaises((SchematicError, ValueError)): validate_layout(l)

    def test_two_access_edges_can_reach_one_venue_dock(self):
        layout = template("DEMO")
        primary = next(edge for edge in layout["edges"] if edge["id"] == "ACCESS_COEX")
        primary["enabled"] = False
        nodes = {node["id"]: node for node in layout["nodes"]}
        layout["nodes"].append(
            {
                "id": "COEX_ALT_APPROACH",
                "label": "COEX alternate approach",
                "x_px": 130,
                "y_px": 130,
                "role": "INTERSECTION",
            }
        )
        layout["edges"].append(
            {
                "id": "WALK_COEX_ALT",
                "from": "A",
                "to": "COEX_ALT_APPROACH",
                "type": "WALKWAY",
                "bidirectional": True,
                "enabled": True,
                "polyline_px": [
                    [nodes["A"]["x_px"], nodes["A"]["y_px"]],
                    [130, 130],
                ],
            }
        )
        layout["edges"].append(
            {
                "id": "ACCESS_COEX_2",
                "from": "COEX_ALT_APPROACH",
                "to": "COEX",
                "type": "WALKWAY",
                "bidirectional": True,
                "enabled": True,
                "polyline_px": [
                    [130, 130],
                    [nodes["COEX"]["x_px"], nodes["COEX"]["y_px"]],
                ],
            }
        )
        validated = validate_layout(layout)
        self.assertEqual(
            [edge["id"] for edge in validated["edges"] if edge["id"].startswith("ACCESS_COEX")],
            ["ACCESS_COEX", "ACCESS_COEX_2"],
        )

    def test_storage_is_private_bounded_and_symlink_rejected(self):
        path = self.session.store.path
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        path.unlink(); path.symlink_to(self.root / "missing")
        with self.assertRaises(RoutePlannerStorageError): SchematicSession(self.root)


class SchematicApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.assets_patch = patch("robot_dashboard.route_planner.schematic.ASSETS", install_test_templates(Path(self.temp.name) / "test-assets"))
        self.assets_patch.start()
        self.addCleanup(self.assets_patch.stop)
        self.app = make_app(Path(self.temp.name).resolve())
        self.client = TestClient(self.app, headers={"Origin": "http://testserver"})

    def tearDown(self):
        self.assertEqual(self.app.state.trap.calls, [])
        self.client.close(); self.temp.cleanup()

    def command(self, action, data=None, **overrides):
        s = self.client.get("/api/v1/route-planner/schematic").json()
        return self.client.post("/api/v1/route-planner/schematic", json={"action": action, "context": s["context"], "expected_revision": s["revision"], "data": data or {}, **overrides})

    def test_real_http_no_motion_and_legacy_provenance_rejected(self):
        self.assertEqual(self.command("CONTEXT", {"context": "DEMO"}).status_code, 200)
        self.assertEqual(self.command("ORDER", {"order": order()}).status_code, 200)
        self.command("START_POINT", {"node_id": "COEX"})
        s = self.command("RECOMMEND").json(); r = s["recommendations"][0]
        for suffix in ["preview", "mission-dry-run", "export-mission"]:
            response = self.client.post(f'/api/v1/route-planner/routes/{r["id"]}/{suffix}', json={"route_revision": r["revision"]})
            self.assertIn(response.status_code, (409, 422))
        self.assertEqual(self.client.put("/api/v1/route-planner/graph", json=s["layout"]).status_code, 422)
        for path in ["/api/v1/navigation/goal", "/api/v1/missions"]:
            self.assertEqual(self.client.post(path, json={**r, "map_kind": "SCHEMATIC_MANUAL"}).status_code, 422)
        pin = dict(route_id=r["id"], route_revision=r["revision"])
        self.command("SELECT", pin); self.command("START", pin)
        for _ in range(100):
            s = self.client.get("/api/v1/route-planner/schematic").json(); g = s["guidance"]
            if not g["active"]: break
            pending = [p for p in r["stops"] if p["after_segment"] == g["current_segment_index"] and p["venue_id"] not in g["completed_pickups"] + g["completed_dropoffs"]]
            data = {**pin, "event_id": f'api-event-{s["revision"]}', "expected_progress_revision": g["progress_revision"], "expected_segment_index": g["current_segment_index"]}
            if pending: data["venue_id"] = pending[0]["venue_id"]
            response = self.command(pending[0]["kind"] if pending else "STEP", data)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(s["guidance"]["state"], "COMPLETE")

    def test_missing_private_assets_fail_closed_without_fabricated_field(self):
        with patch("robot_dashboard.route_planner.schematic.ASSETS", Path(self.temp.name) / "absent"):
            view = self.client.get("/api/v1/route-planner/schematic").json()
            self.assertFalse(view["available"])
            self.assertFalse(view["motion_authority"])
            self.assertFalse(view["control_authority"])
            self.assertEqual(self.command("CONTEXT", {"context": "DEMO"}).status_code, 503)

    def test_origin_competition_task_and_payload_gates(self):
        response = self.client.post("/api/v1/route-planner/schematic", headers={"Origin": "http://attacker"}, json={})
        self.assertEqual(response.status_code, 403)
        self.app.state.runtime.competition.lock("LOCK")
        self.assertEqual(self.command("CONTEXT", {"context": "DEMO"}).status_code, 423)
        self.app.state.runtime.competition.unlock("UNLOCK", stationary_confirmed=True)
        for gate in ["navigation", "mapping"]:
            self.app.state.gates[gate] = True
            self.assertEqual(self.command("CONTEXT", {"context": "DEMO"}).status_code, 409)
            self.app.state.gates[gate] = False
        self.app.state.trap.active = True
        self.assertEqual(self.command("CONTEXT", {"context": "DEMO"}).status_code, 409)
        self.app.state.trap.active = False
        self.assertEqual(self.command("GOAL").status_code, 422)
        self.assertEqual(self.command("CONTEXT", {"context": "DEMO"}, motion_authority=True).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/route-planner/schematic", content=b'x' * (1024 * 1024 + 1)).status_code, 413)

    def test_two_tab_revision_race_uses_coordinator_lock(self):
        self.command("CONTEXT", {"context": "DEMO"})
        s = self.client.get("/api/v1/route-planner/schematic").json()
        async def race():
            c = self.app.state.runtime.route_planner
            return await asyncio.gather(*(c.schematic_command("START_POINT", s["revision"], "DEMO", {"node_id": "COEX"}) for _ in range(2)), return_exceptions=True)
        result = asyncio.run(race())
        self.assertEqual(sum(isinstance(r, SchematicError) and r.status == 409 for r in result), 1)
