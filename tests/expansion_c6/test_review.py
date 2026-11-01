import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from robot_dashboard.run_review.io import loads, open_local, read_jsonl, write_new
from robot_dashboard.run_review.review import Builder, MANIFEST, load_run, timestamp
from robot_dashboard.run_review.summary import compare, markdown, summary
from expansion_c6.fixtures import goal_fixture


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_actual_goal_producer_sink_parser_preserve_precision(self):
        manifest = goal_fixture(self.root, yaw=0.5)
        original = (self.root / manifest["file"]).read_bytes()
        with patch(
            "socket.socket", side_effect=AssertionError("No transport permitted")
        ):
            run = load_run(self.root, manifest)
        self.assertEqual(run["mode"], "REPLAY")
        self.assertEqual(run["precision"]["result"]["state"], "succeeded")
        self.assertAlmostEqual(run["precision"]["after_stop"]["error"]["yaw_rad"], 0.5)
        self.assertEqual(
            run["precision"]["near_result"]["stamp_ns"], "1793244679103000000"
        )
        self.assertEqual(
            run["precision"]["after_stop"]["stamp_ns"], "1793244681103000000"
        )
        self.assertIsNotNone(run["precision"]["motion_vs_correction"])
        self.assertEqual(run["observations"]["bridge_ack"], "UNOBSERVED")
        self.assertEqual(run["observations"]["contact"], "UNOBSERVED")
        self.assertEqual(original, (self.root / manifest["file"]).read_bytes())
        self.assertEqual(
            summary(run)["near_result"]["stamp_ns"],
            run["precision"]["near_result"]["stamp_ns"],
        )
        self.assertGreater(int(run["events"][-1]["replay_ns"]), 3_000_000_000)

    def test_arrival_and_cancel_and_different_conditions(self):
        a = load_run(self.root, goal_fixture(self.root, "arrival"))
        b = load_run(self.root, goal_fixture(self.root, "cancel", "canceled"))
        self.assertEqual(a["precision"]["near_result"]["error"]["xy_m"], 0)
        self.assertEqual(b["precision"]["result"]["state"], "canceled")
        result = compare(a, b)
        self.assertEqual(
            result["classification"], "REFERENCE_COMPARISON_NOT_SAME_CONDITION_AB"
        )
        self.assertIsNone(result["algorithm_improvement_rate"])
        self.assertIn("goal_id", [d["field"] for d in result["differences"]])

    def test_unpaired_motion_remains_unobserved(self):
        manifest = goal_fixture(self.root)
        path = self.root / manifest["file"]
        rows = [json.loads(r) for r in path.read_text().splitlines()]
        for r in rows:
            after = r["evidence"].get("after_stop")
            if after:
                after["odom_body"]["stamp_ns"] = "1"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.assertIsNone(
            load_run(self.root, manifest)["precision"]["motion_vs_correction"]
        )

    def test_accepted_event_does_not_invent_timestamp(self):
        run = load_run(self.root, goal_fixture(self.root))
        e = next(e for e in run["events"] if e["kind"] == "accepted")
        self.assertIsNone(e["time"]["value"])
        self.assertEqual(e["time"]["basis"], "EVENT_TIME_UNOBSERVED")

    def test_ns_duplicate_depth_and_file_bound(self):
        self.assertEqual(
            loads('{"stamp_ns":9007199254740993}')["stamp_ns"], "9007199254740993"
        )
        for raw in (
            '{"a":1,"a":2}',
            '{"stamp_ns":1.1}',
            '{"n":NaN}',
            '{"n":1e999}',
            '{"n":9007199254740993}',
            "[" * 34 + "0" + "]" * 34,
        ):
            with self.assertRaises(ValueError):
                loads(raw)
        path = self.root / "huge.jsonl"
        path.write_bytes(b" " * (256 * 1024 + 1))
        with self.assertRaises(ValueError):
            list(read_jsonl(self.root, path.name))

    def test_paths_symlinks_archives_and_existing_output_rejected(self):
        (self.root / "ok.json").write_text("{}")
        (self.root / "link.json").symlink_to(self.root / "ok.json")
        for name in (
            "../ok.json",
            "/ok.json",
            "https://host/a.json",
            "a.zip",
            "a\\b.json",
            "link.json",
        ):
            with self.assertRaises((ValueError, OSError)):
                with open_local(self.root, name):
                    pass
        folder = self.root / "linkdir"
        folder.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            open_local(self.root, "linkdir/ok.json")
        with self.assertRaises(FileExistsError):
            write_new(self.root / "ok.json", {})

    def test_public_allowlist_drops_private_arbitrary_values(self):
        manifest = goal_fixture(self.root)
        manifest["source_id"] = "http://192.168.1.2/private/token=secret"
        run = load_run(self.root, manifest)
        run["precision"]["context"] = {
            "token": "TOP_SECRET",
            "path": "/Users/private",
            "html": "<script>bad()</script>",
        }
        public = summary(run)
        text = json.dumps(public) + markdown(public)
        for needle in ["TOP_SECRET", "/Users/", "192.168", "<script>", "token="]:
            self.assertNotIn(needle, text)
        self.assertEqual(public["requested"], run["precision"]["requested"])

    def test_cross_host_and_epoch_clocks_are_not_subtracted(self):
        b = Builder({"data_kind": "SYNTHETIC"})
        b.event("pose", timestamp(), ns=100, clock=("host-a", "epoch-1"))
        b.event(
            "pose", timestamp(), ns=9000000000000000000, clock=("host-b", "epoch-1")
        )
        self.assertLess(int(b.events[-1]["replay_ns"]), 10_000_000)
        self.assertEqual(b.finish()["quality"]["cross_host_latency"], "UNOBSERVED")

    def test_unknown_format_and_goal_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_FORMAT"):
            load_run(
                self.root, {"schema": MANIFEST, "data_kind": "REAL", "format": "rosbag"}
            )
        manifest = goal_fixture(self.root)
        manifest["goal_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "INPUT_REQUIRED"):
            load_run(self.root, manifest)

    def test_javascript_mock_transport_regressions(self):
        result = subprocess.run(
            ["node", "--test", "tests/expansion_c6/test_replay.mjs"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(
    os.environ.get("C6_DEPS"),
    "explicit pinned owner export required; mock tests are separate",
)
class ActualOwnerTests(unittest.TestCase):
    def test_expired_snapshot_cannot_reappear_after_seek_import(self):
        from robot_dashboard.run_review.dependencies import c1_validator
        from expansion_c6.fixtures import scene_fixture

        validate = c1_validator(os.environ["C6_DEPS"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = scene_fixture(root, validate)
            path = root / manifest["file"]
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            delayed = copy.deepcopy(rows[0])
            delayed["recorded_at"]["stamp_ns"] = str(
                int(rows[1]["recorded_at"]["stamp_ns"]) + 1
            )
            path.write_text(
                "".join(json.dumps(r) + "\n" for r in [rows[0], rows[1], delayed])
            )
            with self.assertRaisesRegex(ValueError, "RETIRED_SOURCE"):
                load_run(root, manifest, validator=validate)

    def test_actual_c1_producer_validator_and_c3_parser(self):
        from robot_dashboard.run_review.dependencies import c1_validator
        from expansion_c6.fixtures import scene_fixture

        validate = c1_validator(os.environ["C6_DEPS"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = load_run(root, scene_fixture(root, validate), validator=validate)
            self.assertEqual(
                run["frames"][0]["packet"]["global_path"]["received_monotonic_ns"],
                "9007199254740993",
            )
            self.assertIsNone(run["frames"][1]["packet"]["global_path"])
            self.assertEqual(run["observations"]["map_change"], 1)
            path = root / "review.json"
            path.write_text(json.dumps(run))
            r = subprocess.run(
                [
                    "node",
                    "tests/expansion_c6/actual_c3.mjs",
                    os.environ["C6_DEPS"],
                    str(path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
