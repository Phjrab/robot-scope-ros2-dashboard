import copy
import tempfile
import unittest
from unittest.mock import patch

from robot_dashboard.expansion_contracts import ContractError
from robot_dashboard.expansion_contracts.fixtures import obstacle
from robot_dashboard.expansion_contracts.time_binding import (
    ClockBinding,
    normalize_collision_assessment,
)
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from robot_dashboard.expansion_services.scene_assets import SceneAssets
from tests.expansion_contracts.test_time_binding import assessment
from tests.expansion_services.http_client import TestClient
from experiments.expansion_20261029.c1_service_host.host import create_test_host


class SceneRound2Tests(unittest.TestCase):
    def scene(self):
        self.now = 110
        o = obstacle().to_dict()
        o["received_monotonic_ns"] = 100
        return SceneSnapshotService(
            o["map_binding"],
            schema_version="0.2",
            host_clock_id="test-host",
            clock=lambda: self.now,
            max_age_ns=50,
        ), o

    def test_missing_pending_ready_expired_empty_does_not_mean_free(self):
        s, o = self.scene()
        self.assertEqual(
            s.snapshot()["sources"]["obstacle_frame"]["status"], "unavailable"
        )
        s.reset_source("obstacle_frame", o["source_epoch"])
        self.assertEqual(s.snapshot()["sources"]["obstacle_frame"]["status"], "pending")
        s.ingest("obstacle_frame", o)
        packet = s.snapshot()
        self.assertEqual(packet["sources"]["obstacle_frame"]["status"], "ready")
        self.assertTrue(packet["sources"]["obstacle_frame"]["empty_result"])
        self.assertNotIn("known_free", packet["sources"]["obstacle_frame"])
        self.assertEqual(packet["obstacle_frame"]["received_monotonic_ns"], "100")
        self.now = 151
        self.assertIsNone(s.snapshot()["obstacle_frame"])
        self.assertEqual(s.snapshot()["sources"]["obstacle_frame"]["status"], "expired")

    def test_full_reference_accepted_but_changed_identity_not_paired(self):
        s, o = self.scene()
        s.ingest("obstacle_frame", o)
        raw = assessment()
        raw["received_monotonic_ns"] = 100
        raw["obstacle_frame_ref"] = copy.deepcopy(o)
        c = normalize_collision_assessment(
            raw,
            binding=ClockBinding(
                "fixture-clock", "fixture-epoch", "test-host", 0, 0, "explicit-test"
            ),
        )
        s.ingest("collision_assessment", c)
        self.assertEqual(s.snapshot()["collision_assessment"]["severity"], "UNKNOWN")
        c["sequence"] += 1
        c["obstacle_frame_ref"]["map_binding"]["revision"] = "f" * 64
        s.ingest("collision_assessment", c)
        self.assertIsNone(s.snapshot()["collision_assessment"])

    def test_rejected_restart_is_atomic_and_old_epoch_is_retired(self):
        s, o = self.scene()
        s.ingest("obstacle_frame", o)
        before = s.snapshot()
        with self.assertRaises(ContractError):
            s.reset_source("obstacle_frame", o["source_epoch"])
        self.assertEqual(s.snapshot(), before)
        s.reset_source("obstacle_frame", "restart")
        self.assertFalse(s.ingest("obstacle_frame", o))
        o["source_epoch"] = o["frame_key"]["source_epoch"] = "restart"
        o["sequence"] = 0
        self.assertTrue(s.ingest("obstacle_frame", o))
        s.reset({**o["map_binding"], "generation": 1}, "new-map")
        self.assertFalse(s.ingest("obstacle_frame", o))

    def test_clock_unknown_is_unavailable_and_missing_calibration_visible(self):
        s, o = self.scene()
        o["calibration_id"] = None
        s.ingest("obstacle_frame", o)
        self.assertEqual(
            s.snapshot()["sources"]["obstacle_frame"]["calibration_status"], "UNKNOWN"
        )
        o.update(sequence=1, host_clock_id="browser")
        s.ingest("obstacle_frame", o)
        self.assertIsNone(s.snapshot()["obstacle_frame"])
        self.assertIsNone(s.snapshot()["sources"]["obstacle_frame"]["received_age_ms"])

    def test_assets_are_bounded_display_refs_without_hashing_on_poll(self):
        s, o = self.scene()
        data = b"x" * 1000000
        ref = s.publish_asset("saved_reference_cloud", "saved", data)
        with patch(
            "robot_dashboard.expansion_services.scene_assets.hashlib.sha256",
            side_effect=AssertionError("poll rehash"),
        ):
            for _ in range(5):
                self.assertEqual(s.snapshot()["sources"]["assets"], [ref])
                self.assertEqual(s.get_asset(ref["id"], ref["revision"])[0], data)
        self.assertLess(len(str(s.snapshot())), 2000)
        changed = s.publish_asset("saved_reference_cloud", "saved", b"y")
        self.assertNotEqual(ref["revision"], changed["revision"])
        with self.assertRaises(KeyError):
            s.get_asset(ref["id"], ref["revision"])
        s.reset({**o["map_binding"], "generation": 1}, "new-map")
        with self.assertRaises(KeyError):
            s.get_asset(changed["id"], changed["revision"])
        store = SceneAssets(max_bytes=10, max_asset_bytes=6, max_items=2)
        store.publish("live_cloud", "a", b"123456")
        with self.assertRaises(ContractError):
            store.publish("live_cloud", "b", b"123456")
        with self.assertRaises(ContractError):
            store.publish("arbitrary-url", "b", b"a")

    def test_bulk_http_is_authenticated_revision_bound_and_no_paths(self):
        with tempfile.TemporaryDirectory() as root:
            bearer = "public-test-bearer-123456789"
            app = create_test_host(root, bearer)
            scene = app.state.c1[2]
            ref = scene.publish_asset("live_cloud", "sensor", b"xyz")
            path = f"/api/v1/extensions/scene/assets/{ref['id']}/{ref['revision']}"
            headers = {"Authorization": "Bearer " + bearer}
            with TestClient(app) as client:
                self.assertEqual(client.get(path).status_code, 401)
                response = client.get(path, headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b"xyz")
                self.assertEqual(
                    client.get(path + "0", headers=headers).status_code, 404
                )
                packet = client.get(
                    "/api/v1/extensions/scene/snapshot", headers=headers
                )
                self.assertNotIn(root, packet.text)
                self.assertEqual(
                    client.get(
                        "/api/v1/extensions/multimap/exports", headers=headers
                    ).json(),
                    {"exports": []},
                )

    def test_aggregate_budget_includes_duplicated_health(self):
        from dataclasses import fields
        from robot_dashboard.expansion_contracts.messages import Observation

        s, o = self.scene()
        sample = {field.name: o[field.name] for field in fields(Observation)}
        sample.update(data={}, health={"diagnostic": "x" * 13000})
        for slot in (
            "robot_pose",
            "global_path",
            "controller_local_trajectory",
            "costmap_snapshot",
        ):
            self.assertTrue(s.ingest(slot, sample))
        o["health"] = {"diagnostic": "x" * 13000}
        self.assertFalse(s.ingest("obstacle_frame", o))
        from robot_dashboard.expansion_contracts import canonical

        self.assertLess(len(canonical(s.snapshot())), 128 * 1024)
