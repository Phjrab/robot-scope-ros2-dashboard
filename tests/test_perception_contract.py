import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from robot_dashboard.perception import (
    POLICY_SCHEMA,
    RESULT_SCHEMA,
    SNAPSHOT_SCHEMA,
    MAX_RESPONSE_BYTES,
    PerceptionBridgeClient,
    PerceptionPolicy,
    PerceptionStore,
    PerceptionValidationError,
)


SOURCE_IP = "192.168.50.30"
SOURCE_ID = "go2-internal-realsense"
BOOT_A = "11111111-1111-1111-1111-111111111111"
BOOT_B = "22222222-2222-2222-2222-222222222222"
HASHES = {"lane": "a" * 64, "object": "b" * 64, "depth_summary": "c" * 64}


def policy_payload():
    return {
        "schema_version": POLICY_SCHEMA,
        "source_id": SOURCE_ID,
        "models": [
            {"task": "lane", "model_id": "lane-1", "model_sha256": HASHES["lane"], "backend": "onnx", "input_width": 640, "input_height": 480, "classes": []},
            {"task": "object", "model_id": "object-1", "model_sha256": HASHES["object"], "backend": "tensorrt", "input_width": 640, "input_height": 480, "classes": ["person", "cone"]},
            {"task": "depth_summary", "model_id": "depth-1", "model_sha256": HASHES["depth_summary"], "backend": "onnx", "input_width": 640, "input_height": 480, "classes": []},
        ],
    }


def load_policy():
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "policy.json"
    path.write_text(json.dumps(policy_payload()), encoding="utf-8")
    return directory, PerceptionPolicy.load(path)


def result(
    task="lane",
    sequence=1,
    boot_id=BOOT_A,
    server_ns=10_000_000_000,
    source_sequence=None,
    source_epoch=1,
):
    payloads = {
        "lane": {"lateral_error_normalized": 0.1, "heading_error_rad": 0.02, "curvature": 0.001, "left_lane_visible": True, "right_lane_visible": True, "confidence": 0.9, "reason": "model_output"},
        "object": {"detections": [{"class_id": 1, "class_name": "cone", "x1": 10.0, "y1": 20.0, "x2": 100.0, "y2": 200.0, "confidence": 0.8}], "detection_count": 1},
        "depth_summary": {"front_min_distance_m": 2.0, "left_clearance_m": 1.5, "right_clearance_m": 1.7, "obstacle_count": 2, "ground_confidence": 0.7, "mode": "SUMMARY"},
    }
    confidence = {"lane": 0.9, "object": 0.8, "depth_summary": 0.7}[task]
    return {
        "schema_version": RESULT_SCHEMA,
        "source_id": SOURCE_ID,
        "boot_id": boot_id,
        "sequence": sequence,
        "source_sequence": sequence if source_sequence is None else source_sequence,
        "source_epoch": source_epoch,
        "task": task,
        "capture_timestamp": server_ns - 300_000_000,
        "capture_clock_domain": "robot-monotonic",
        "inference_started_at": server_ns - 200_000_000,
        "inference_completed_at": server_ns - 100_000_000,
        "model_id": f"{'depth' if task == 'depth_summary' else task}-1",
        "model_sha256": HASHES[task],
        "backend": "tensorrt" if task == "object" else "onnx",
        "input_width": 640,
        "input_height": 480,
        "result_status": "LIVE",
        "confidence": confidence,
        "payload": payloads[task],
    }


def snapshot(results, server_ns=10_000_000_000):
    return {"schema_version": SNAPSHOT_SCHEMA, "server_monotonic": server_ns, "mode": "SHADOW", "results": results}


class PerceptionContractTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.policy = load_policy()
        self.store = PerceptionStore(SOURCE_IP, self.policy, history_size=4)

    def tearDown(self):
        self.directory.cleanup()

    def assert_rejected(self, code, payload, **kwargs):
        with self.assertRaises(PerceptionValidationError) as caught:
            self.store.ingest(payload, source_ip=kwargs.get("source_ip", SOURCE_IP), received_monotonic_ns=20_000_000_000)
        self.assertEqual(caught.exception.code, code)

    def test_normal_lane_object_and_depth_are_validated_and_bounded(self):
        accepted = self.store.ingest(snapshot([result("lane"), result("object"), result("depth_summary")]), source_ip=SOURCE_IP, received_monotonic_ns=20_000_000_000)
        self.assertEqual(accepted, 3)
        latest = self.store.latest_snapshot(now_ns=20_100_000_000)
        self.assertEqual({item["task"] for item in latest["results"]}, {"lane", "object", "depth_summary"})
        self.assertTrue(all(item["result_status"] == "LIVE" for item in latest["results"]))
        self.assertTrue(all(item["clock_domain_verified"] is False for item in latest["results"]))
        self.assertTrue(all(item["source_sequence"] == 1 for item in latest["results"]))
        self.assertTrue(all(item["source_epoch"] == 1 for item in latest["results"]))
        self.assertTrue(all(item["input_age_s"] == 0.4 for item in latest["results"]))
        self.assertLessEqual(len(self.store.history_snapshot(limit=120)["results"]), 4)

    def test_nan_inf_detection_limit_and_coordinate_fail_closed(self):
        invalid = result()
        invalid["payload"]["curvature"] = float("nan")
        self.assert_rejected("INVALID_LANE_NUMBER", snapshot([invalid]))
        invalid = result("depth_summary")
        invalid["payload"]["front_min_distance_m"] = float("inf")
        self.assert_rejected("INVALID_DEPTH_NUMBER", snapshot([invalid]))
        invalid = result("object")
        invalid["payload"]["detections"] *= 101
        invalid["payload"]["detection_count"] = 101
        self.assert_rejected("DETECTION_LIMIT", snapshot([invalid]))
        invalid = result("object")
        invalid["payload"]["detections"][0]["x2"] = 700
        self.assert_rejected("INVALID_COORDINATE", snapshot([invalid]))

    def test_duplicate_gap_boot_change_and_stale_cleanup(self):
        self.assertEqual(self.store.ingest(snapshot([result(sequence=1)]), source_ip=SOURCE_IP, received_monotonic_ns=20_000_000_000), 1)
        self.assertEqual(self.store.ingest(snapshot([result(sequence=1)]), source_ip=SOURCE_IP, received_monotonic_ns=20_100_000_000), 0)
        self.assertEqual(self.store.health_snapshot()["duplicates"], 1)
        self.store.ingest(snapshot([result(sequence=4)]), source_ip=SOURCE_IP, received_monotonic_ns=20_200_000_000)
        self.assertEqual(self.store.latest_snapshot(now_ns=20_300_000_000)["results"][0]["receive_sequence_gap"], 2)
        self.store.ingest(snapshot([result(sequence=1, boot_id=BOOT_B)]), source_ip=SOURCE_IP, received_monotonic_ns=20_400_000_000)
        self.assertEqual(self.store.latest_snapshot(now_ns=20_500_000_000)["results"][0]["receive_sequence_gap"], 0)
        stale = self.store.latest_snapshot(now_ns=22_500_000_001)["results"][0]
        self.assertEqual(stale["result_status"], "STALE")
        self.assertEqual(self.store.health_snapshot(now_ns=22_500_000_001)["state"], "OFFLINE")

    def test_stale_unknown_model_malformed_schema_and_source_ip_are_rejected(self):
        stale = result(server_ns=10_000_000_000)
        stale["capture_timestamp"] = 7_500_000_000
        stale["inference_started_at"] = 7_800_000_000
        stale["inference_completed_at"] = 8_000_000_000
        self.assert_rejected("STALE_RESULT", snapshot([stale]))
        stale_input = result()
        stale_input["capture_timestamp"] = 8_000_000_000
        self.assert_rejected("STALE_RESULT", snapshot([stale_input]))
        unknown = result()
        unknown["model_sha256"] = "f" * 64
        self.assert_rejected("UNKNOWN_MODEL", snapshot([unknown]))
        malformed = snapshot([result()])
        malformed["schema_version"] = "unknown"
        self.assert_rejected("UNKNOWN_SCHEMA", malformed)
        invalid_source_sequence = result()
        invalid_source_sequence["source_sequence"] = 0
        self.assert_rejected(
            "INVALID_SOURCE_SEQUENCE", snapshot([invalid_source_sequence])
        )
        invalid_source_epoch = result()
        invalid_source_epoch["source_epoch"] = 0
        self.assert_rejected("INVALID_SOURCE_EPOCH", snapshot([invalid_source_epoch]))
        self.assert_rejected("SOURCE_IP_REJECTED", snapshot([result()]), source_ip="192.168.50.31")

    def test_one_malformed_result_rejects_the_whole_snapshot_atomically(self):
        invalid = result("object")
        invalid["payload"]["detections"][0]["class_name"] = "remote-added-class"
        self.assert_rejected("UNKNOWN_CLASS", snapshot([result("lane"), invalid]))
        self.assertEqual(self.store.history_snapshot()["results"], [])
        self.assert_rejected("DUPLICATE_TASK", snapshot([result("lane"), result("lane", sequence=2)]))
        self.assertEqual(self.store.history_snapshot()["results"], [])

    def test_reconnect_health_dataset_reference_and_read_only_api(self):
        self.store.note_transport("OFFLINE", "connection refused", now_ns=1)
        self.store.ingest(snapshot([result()]), source_ip=SOURCE_IP, received_monotonic_ns=20_000_000_000)
        self.assertEqual(self.store.health_snapshot()["reconnects"], 1)
        reference = self.store.metadata_reference()
        self.assertEqual(reference["results"][0]["model_sha256"], HASHES["lane"])
        self.assertEqual(reference["results"][0]["source_sequence"], 1)
        self.assertEqual(reference["results"][0]["source_epoch"], 1)
        self.assertGreaterEqual(reference["results"][0]["input_age_s"], 0.3)
        self.assertNotIn("payload", reference["results"][0])

        root = Path(__file__).resolve().parents[1]
        router_tree = ast.parse(
            (root / "robot_dashboard/api/routers/perception.py").read_text(encoding="utf-8")
        )
        decorators = [
            ast.unparse(decorator)
            for node in router_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for decorator in node.decorator_list
        ]
        self.assertTrue(any("router.get('/api/v1/perception/latest')" in item for item in decorators))
        self.assertTrue(any("router.get('/api/v1/perception/history')" in item for item in decorators))
        self.assertTrue(any("router.get('/api/v1/perception/health')" in item for item in decorators))
        self.assertFalse(any("router.post" in item for item in decorators))

    def test_bridge_rejects_oversized_response_before_json_decode(self):
        class Socket:
            @staticmethod
            def getpeername():
                return (SOURCE_IP, 8092)

        class Response:
            status = 200

            @staticmethod
            def getheader(name, default=""):
                return {
                    "Content-Type": "application/json",
                    "Content-Length": str(MAX_RESPONSE_BYTES + 1),
                }.get(name, default)

        class Connection:
            sock = Socket()

            def __init__(self, *_args, **_kwargs):
                pass

            @staticmethod
            def request(*_args, **_kwargs):
                return None

            @staticmethod
            def getresponse():
                return Response()

            @staticmethod
            def close():
                return None

        client = PerceptionBridgeClient(self.store)
        with mock.patch("robot_dashboard.perception.http.client.HTTPConnection", Connection):
            with self.assertRaisesRegex(ValueError, "size limit"):
                client.poll_once()

    def test_bridge_verifies_connected_peer_before_reading_response(self):
        calls = []

        class Socket:
            @staticmethod
            def getpeername():
                return ("192.168.50.31", 8092)

        class Connection:
            sock = Socket()

            def __init__(self, *_args, **_kwargs):
                pass

            @staticmethod
            def request(*_args, **_kwargs):
                calls.append("request")

            @staticmethod
            def getresponse():
                calls.append("response")
                raise AssertionError("response must not be read from an unexpected peer")

            @staticmethod
            def close():
                calls.append("close")

        client = PerceptionBridgeClient(self.store)
        with mock.patch("robot_dashboard.perception.http.client.HTTPConnection", Connection):
            with self.assertRaisesRegex(OSError, "fixed perception endpoint"):
                client.poll_once()
        self.assertEqual(calls, ["request", "close"])

    def test_perception_modules_do_not_import_motion_or_control_code(self):
        root = Path(__file__).resolve().parents[1]
        for relative in ("robot_dashboard/perception.py", "robot_dashboard/api/routers/perception.py"):
            tree = ast.parse((root / relative).read_text(encoding="utf-8"))
            imports = [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            ]
            self.assertFalse(any("control" in name or "navigation" in name for name in imports))


if __name__ == "__main__":
    unittest.main()
