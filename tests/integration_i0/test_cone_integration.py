"""Real C1 owner and real HTTP router; no alternate obstacle state store."""

import copy
import json
import threading
import tempfile
from pathlib import Path
import unittest
import urllib.request
from unittest.mock import patch
from fastapi import FastAPI
from robot_dashboard.expansion_contracts import ContractError, canonical
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from tests.expansion_services.http_client import TestClient
from robot_dashboard.expansion_integration.cone_demo import (
    adapt_cones,
    demo_context,
    load_scenario,
)
from robot_dashboard.expansion_integration.cone_input import (
    validate_legacy_cones,
    ObstacleValidationError,
)
from robot_dashboard.expansion_integration.host import install_expansion
from robot_dashboard.expansion_integration.flags import ExpansionFlags
from experiments.expansion_20261101.cone_display.demo import compose_demo, SCENARIO
from tests.integration_i0.test_cone_validation import payload, cone


class ConeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.value = load_scenario(SCENARIO)
        self.context = demo_context(self.value)
        self.now = 9007199254740993
        self.scene = SceneSnapshotService(
            {k: self.context[k] for k in ("map_id", "revision", "generation")},
            schema_version="0.2",
            stream_epoch=self.context["stream_epoch"],
            host_clock_id="test-host",
            clock=lambda: self.now,
            max_sample_bytes=64 * 1024,
            max_age_ns=1_000_000_000,
        )

    def offer(self, seq=1, stamp=1, **overrides):
        value = dict(self.value, stamp=stamp, **overrides)
        return adapt_cones(
            value,
            self.context,
            sequence=seq,
            received_monotonic_ns=self.now,
            host_clock_id="test-host",
        )

    def test_scenario_exact_dimensions_and_frame_no_real_height_confidence_model_path(
        self,
    ):
        raw = json.loads(SCENARIO.read_text())
        m = self.offer()
        self.assertEqual(self.context["frame_id"], raw["frame_id"])
        for o, c in zip(m["obstacles"], raw["obstacles"]):
            self.assertEqual(o["geometry"]["center"][:2], c["xy"])
            self.assertEqual(o["provenance"]["radius_m"], c["radius_m"])
            self.assertEqual(o["provenance"]["height_m"], c["height_m"])
            self.assertEqual(o["provenance"]["height_status"], "HEIGHT_UNVERIFIED")
            self.assertIsNone(o["class_score"])
            self.assertFalse(o["provenance"]["model_hash_verified"])
        self.assertNotIn("path", json.dumps(m))
        self.assertFalse(m["published_to_nav2"])
        self.assertEqual(m["received_monotonic_ns"], "9007199254740993")

    def test_scenario_bounded_file_duplicate_keys_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_bytes(SCENARIO.read_bytes())
            link = Path(directory) / "alias.json"
            link.symlink_to(path)
            with self.assertRaises(ObstacleValidationError):
                load_scenario(link)
            path.write_text('{"schema_version":"0.1","schema_version":"0.1"}')
            with self.assertRaisesRegex(ObstacleValidationError, "DUPLICATE_JSON_KEY"):
                load_scenario(path)
            path.write_bytes(b" " * (256 * 1024 + 1))
            with self.assertRaisesRegex(ObstacleValidationError, "SCENARIO_LIMIT"):
                load_scenario(path)
            document = json.loads(SCENARIO.read_text())
            document["obstacles"][0]["xy"][0] = True
            path.write_text(json.dumps(document))
            with self.assertRaises(ObstacleValidationError):
                load_scenario(path)

    def test_frame_rename_and_real_map_are_rejected(self):
        with self.assertRaisesRegex(ContractError, "UNALIGNED"):
            self.offer(frame="map")
        for key, value in [
            ("space_kind", "MAP"),
            ("map_id", "a" * 24),
            ("units", "cm"),
            ("source_identity", "LIVE"),
        ]:
            context = dict(self.context, **{key: value})
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ContractError, "PAIRED_REAL"),
            ):
                adapt_cones(
                    self.value,
                    context,
                    sequence=1,
                    received_monotonic_ns=1,
                    host_clock_id="test",
                )

    def test_duplicate_stamp_new_sequence_and_get_do_not_extend_ttl(self):
        m = self.offer()
        self.assertTrue(self.scene.ingest("obstacle_frame", m))
        self.now += 1_100_000_000
        self.assertFalse(self.scene.ingest("obstacle_frame", self.offer(seq=2)))
        for _ in range(4):
            wire = self.scene.snapshot()
            self.assertIsNone(wire["obstacle_frame"])
            self.assertEqual(wire["sources"]["obstacle_frame"]["status"], "expired")
            self.assertEqual(wire["sources"]["obstacle_frame"]["received_age_ms"], 1100)
            self.assertEqual(wire["sequence"], 1)

    def test_stamp_rollback_even_with_higher_sequence_and_foreign_clock_rejected(self):
        self.scene.ingest("obstacle_frame", self.offer())
        for changes in [
            dict(stamp_ns="0"),
            dict(clock_domain="foreign"),
            dict(host_clock_id="other"),
            dict(producer="other"),
        ]:
            m = self.offer(seq=2, stamp=2)
            m.update(changes)
            self.assertFalse(self.scene.ingest("obstacle_frame", m))

    def test_source_restart_requires_reset_and_cannot_reuse_retired_epoch(self):
        self.scene.ingest("obstacle_frame", self.offer())
        self.context = demo_context(self.value, epoch="cone-demo-2")
        m = self.offer()
        self.assertFalse(self.scene.ingest("obstacle_frame", m))
        self.scene.reset_source("obstacle_frame", self.context["source_epoch"])
        self.assertTrue(self.scene.ingest("obstacle_frame", m))
        with self.assertRaises(ContractError):
            self.scene.reset_source("obstacle_frame", "cone-demo-1")

    def test_same_frame_different_map_revision_generation_refused(self):
        for key, value in [
            ("map_id", "a" * 24),
            ("revision", "b" * 64),
            ("generation", 2),
        ]:
            m = self.offer()
            m["map_binding"][key] = value
            self.assertFalse(self.scene.ingest("obstacle_frame", m))

    def test_concurrent_validation_12_commits_before_11_cannot_regress(self):
        self.scene.ingest("obstacle_frame", self.offer(seq=10, stamp=10))
        entered, release = threading.Event(), threading.Event()
        original = canonical

        def bounded(payload, *args):
            if threading.current_thread().name == "older" and not entered.is_set():
                entered.set()
                release.wait(3)
            return original(payload, *args)

        result = []
        with patch("robot_dashboard.expansion_services.scene.canonical", bounded):
            t = threading.Thread(
                name="older",
                target=lambda: result.append(
                    self.scene.ingest("obstacle_frame", self.offer(11, 11))
                ),
            )
            t.start()
            self.assertTrue(entered.wait(3))
            self.assertTrue(self.scene.ingest("obstacle_frame", self.offer(12, 12)))
            release.set()
            t.join(3)
            self.assertFalse(t.is_alive())
        self.assertEqual(result, [False])
        self.assertEqual(self.scene.snapshot()["obstacle_frame"]["sequence"], 12)

    def test_empty_and_health_stale_are_not_waiting(self):
        self.scene.ingest("obstacle_frame", self.offer(cones=[]))
        first = self.scene.snapshot()
        self.assertEqual(first["sources"]["obstacle_frame"]["status"], "ready")
        self.now += 1_000_000_001
        later = self.scene.snapshot()
        self.assertEqual(later["sources"]["obstacle_frame"]["status"], "expired")
        self.assertTrue(later["sources"]["obstacle_frame"]["empty_result"])
        self.scene.ingest(
            "obstacle_frame", self.offer(2, 2, health={"stale": True, "fps": 0})
        )
        self.assertIsNone(self.scene.snapshot()["obstacle_frame"])

    def test_whole_payload_limit_and_max_cones(self):
        value = payload(cones=[cone(identifier=i) for i in range(64)])
        self.assertEqual(len(validate_legacy_cones(value)["cones"]), 64)
        with self.assertRaises(ObstacleValidationError):
            validate_legacy_cones(
                payload(model={"path": "x" * 70000, "sha256_12": "0" * 12})
            )
        self.assertTrue(self.scene.ingest("obstacle_frame", self.offer()))
        value = copy.deepcopy(self.value)
        value["cones"].append(dict(value["cones"][0]))
        with self.assertRaises(ObstacleValidationError):
            adapt_cones(
                value,
                self.context,
                sequence=2,
                received_monotonic_ns=self.now,
                host_clock_id="test-host",
            )
        self.assertEqual(self.scene.snapshot()["sequence"], 1)

    def test_c1_sample_size_is_bounded_at_64_cones(self):
        m = self.offer(cones=[cone(identifier=i) for i in range(64)])
        self.assertTrue(self.scene.ingest("obstacle_frame", m))
        self.assertLess(len(canonical(self.scene.snapshot())), 128 * 1024)

    def test_off_auth_missing_source_and_no_legacy_route(self):
        for flags, expected in [
            (ExpansionFlags(), 404),
            (ExpansionFlags(scene=True), 401),
        ]:
            app = FastAPI()
            install_expansion(app, flags)
            with TestClient(app) as client:
                self.assertEqual(
                    client.get("/api/v1/extensions/scene/snapshot").status_code,
                    expected,
                )
                self.assertEqual(client.get("/api/v1/obstacles").status_code, 404)

    def test_loopback_demo_uses_existing_auth_read_only_c1_and_no_get_refresh(self):
        d = compose_demo()
        d.running = False
        with TestClient(d.app, base_url="http://127.0.0.1:4192") as client:
            self.assertEqual(
                client.get("/api/v1/extensions/scene/snapshot").status_code, 401
            )

            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args):
                    return None

            client.opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), NoRedirect()
            )
            entry = client.get("/")
            cookie = entry.headers["set-cookie"].split(";")[0]
            headers = {"Cookie": cookie}
            self.assertTrue(d.offer())
            a = client.get("/api/v1/extensions/scene/snapshot", headers=headers)
            b = client.get("/api/v1/extensions/scene/snapshot", headers=headers)
            self.assertEqual(a.json()["sequence"], b.json()["sequence"])
            self.assertIn("no-store", a.headers["cache-control"])
            self.assertEqual(
                client.post(
                    "/api/v1/extensions/scene/snapshot", headers=headers
                ).status_code,
                405,
            )
            self.assertEqual(
                client.get("/", headers={"Host": "attacker.example"}).status_code, 403
            )
            d.owner.scene = None
            self.assertEqual(
                client.get(
                    "/api/v1/extensions/scene/snapshot", headers=headers
                ).status_code,
                503,
            )
