import importlib.util
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "check_xt16_lidar_ready.py"
START_SCRIPT = ROOT / "scripts" / "start_hesai_mapping_humble.sh"
SPEC = importlib.util.spec_from_file_location("check_xt16_lidar_ready", HELPER)
readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readiness
assert SPEC.loader is not None
SPEC.loader.exec_module(readiness)


def field(name, offset, datatype, count=1):
    return SimpleNamespace(
        name=name,
        offset=offset,
        datatype=datatype,
        count=count,
    )


def raw_cloud(*, stamp=1_000.0, width=4_000, overrides=None):
    fields = [
        field("x", 0, readiness.FLOAT32),
        field("y", 4, readiness.FLOAT32),
        field("z", 8, readiness.FLOAT32),
        field("intensity", 12, readiness.FLOAT32),
        field("ring", 16, readiness.UINT16),
        field("timestamp", 18, readiness.FLOAT64),
    ]
    if overrides is not None:
        fields = overrides
    point_step = 32
    row_step = width * point_step
    data = bytearray(row_step)
    if width:
        struct.pack_into("<d", data, 18, stamp)
    return SimpleNamespace(
        width=width,
        height=1,
        fields=fields,
        is_bigendian=False,
        point_step=point_step,
        row_step=row_step,
        data=data,
        header=SimpleNamespace(
            frame_id="hesai_lidar",
            stamp=SimpleNamespace(sec=int(stamp), nanosec=0),
        ),
    )


def publisher(
    gid=(1,),
    *,
    topic_type=readiness.POINTCLOUD_TYPE,
    reliability="reliable",
    durability="volatile",
):
    return SimpleNamespace(
        endpoint_gid=gid,
        topic_type=topic_type,
        qos_profile=SimpleNamespace(
            reliability=reliability,
            durability=durability,
        ),
    )


class Xt16ReadinessCoreTests(unittest.TestCase):
    def test_exact_bridge_layout_frame_and_payload_are_accepted(self):
        message = raw_cloud(width=64_000)
        self.assertEqual(readiness.validate_xt16_cloud(message), 64_000)
        self.assertEqual(readiness.xt16_scan_timestamp(message), 1_000.0)

    def test_missing_or_incompatible_bridge_field_is_rejected(self):
        wrong = raw_cloud().fields
        wrong[-1] = field("timestamp", 20, readiness.FLOAT64)
        with self.assertRaisesRegex(readiness.ReadinessError, "timestamp.*offset=20"):
            readiness.validate_xt16_cloud(raw_cloud(overrides=wrong))

        missing = raw_cloud().fields[:-1]
        with self.assertRaisesRegex(readiness.ReadinessError, "missing.*timestamp"):
            readiness.validate_xt16_cloud(raw_cloud(overrides=missing))

    def test_small_truncated_padded_or_organized_cloud_is_rejected(self):
        with self.assertRaisesRegex(readiness.ReadinessError, "expected at least 1000"):
            readiness.validate_xt16_cloud(raw_cloud(width=10))

        truncated = raw_cloud()
        truncated.data = truncated.data[:-1]
        with self.assertRaisesRegex(readiness.ReadinessError, "expected exactly"):
            readiness.validate_xt16_cloud(truncated)

        padded = raw_cloud()
        padded.data += b"\0"
        with self.assertRaisesRegex(readiness.ReadinessError, "expected exactly"):
            readiness.validate_xt16_cloud(padded)

        organized = raw_cloud()
        organized.height = 2
        with self.assertRaisesRegex(readiness.ReadinessError, "height must be 1"):
            readiness.validate_xt16_cloud(organized)

    def test_five_fresh_scans_at_a_real_mapping_rate_are_required(self):
        gate = readiness.Xt16ReadinessGate()
        for index in range(4):
            self.assertFalse(
                gate.observe_cloud(
                    raw_cloud(stamp=1_000.0 + index * 0.1),
                    received_at=10.0 + index * 0.1,
                    publisher=(1,),
                )
            )
        self.assertTrue(
            gate.observe_cloud(
                raw_cloud(stamp=1_000.4),
                received_at=10.4,
                publisher=(1,),
            )
        )
        self.assertGreaterEqual(gate.observed_rate_hz, 5.0)

    def test_gap_replayed_stamp_and_new_publisher_reset_the_window(self):
        gate = readiness.Xt16ReadinessGate()
        gate.observe_cloud(raw_cloud(stamp=1_000.0), received_at=10.0, publisher=(1,))
        gate.observe_cloud(raw_cloud(stamp=1_000.1), received_at=10.1, publisher=(1,))
        gate.observe_cloud(raw_cloud(stamp=1_000.2), received_at=11.0, publisher=(1,))
        self.assertEqual(gate.consecutive_frames, 1)
        self.assertIn("gap", gate.last_reset_reason)

        gate.observe_cloud(raw_cloud(stamp=1_000.2), received_at=11.1, publisher=(1,))
        self.assertEqual(gate.consecutive_frames, 1)
        self.assertIn("timestamp", gate.last_reset_reason)

        gate.observe_cloud(raw_cloud(stamp=1_000.3), received_at=11.2, publisher=(2,))
        self.assertEqual(gate.consecutive_frames, 1)
        self.assertIn("publisher", gate.last_reset_reason)

    def test_low_or_zero_frame_rate_never_becomes_ready(self):
        gate = readiness.Xt16ReadinessGate()
        for index in range(8):
            self.assertFalse(
                gate.observe_cloud(
                    raw_cloud(stamp=1_000.0 + index),
                    received_at=10.0 + index,
                    publisher=(1,),
                )
            )
        self.assertEqual(gate.consecutive_frames, 1)
        self.assertIn("gap", gate.last_reset_reason)

    def test_exactly_one_reliable_volatile_pointcloud_publisher_is_required(self):
        kwargs = {
            "topic": "/lidar_points",
            "expected_type": readiness.POINTCLOUD_TYPE,
            "reliable_policy": "reliable",
            "volatile_policy": "volatile",
        }
        self.assertEqual(readiness.publisher_identity([publisher()], **kwargs), (1,))
        with self.assertRaisesRegex(readiness.ReadinessError, "exactly one"):
            readiness.publisher_identity([publisher(), publisher((2,))], **kwargs)
        with self.assertRaisesRegex(readiness.ReadinessError, "type"):
            readiness.publisher_identity(
                [publisher(topic_type="sensor_msgs/msg/LaserScan")], **kwargs
            )
        with self.assertRaisesRegex(readiness.ReadinessError, "reliable"):
            readiness.publisher_identity(
                [publisher(reliability="best_effort")], **kwargs
            )
        with self.assertRaisesRegex(readiness.ReadinessError, "volatile"):
            readiness.publisher_identity(
                [publisher(durability="transient_local")], **kwargs
            )

    def test_bridge_and_fastlio_stages_require_every_output_topic(self):
        bridge = readiness.StageState("bridge")
        self.assertEqual(
            set(bridge.gates), {"/velodyne_points", "/imu/body"}
        )
        self.assertFalse(bridge.ready)
        fastlio = readiness.StageState("fastlio")
        self.assertEqual(set(fastlio.gates), {"/Odometry", "/Laser_map"})
        self.assertFalse(fastlio.ready)


class Xt16ReadinessLauncherContractTests(unittest.TestCase):
    def setUp(self):
        self.script = START_SCRIPT.read_text(encoding="utf-8")
        self.helper_source = HELPER.read_text(encoding="utf-8")

    def test_scripts_have_valid_syntax_and_helper_help_needs_no_ros(self):
        subprocess.run(["bash", "-n", str(START_SCRIPT)], check=True)
        result = subprocess.run(
            [sys.executable, str(HELPER), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("raw", result.stdout)
        self.assertIn("bridge", result.stdout)
        self.assertIn("fastlio", result.stdout)

    def test_ros_node_does_not_assign_the_read_only_subscriptions_property(self):
        self.assertNotIn("self.subscriptions =", self.helper_source)
        self.assertIn("self._readiness_subscriptions =", self.helper_source)

    def test_each_readiness_gate_follows_its_producer_before_commit(self):
        driver = self.script.index('start_once "hesai_ros_driver_node"')
        raw = self.script.index("--stage raw")
        bridge_process = self.script.index('start_once "xt16_fastlio_bridge.py"')
        bridge_gate = self.script.index("--stage bridge")
        fastlio_process = self.script.index('start_once "fastlio_mapping"')
        fastlio_gate = self.script.index("--stage fastlio")
        committed = self.script.index("PIPELINE_COMMITTED=1")
        self.assertLess(driver, raw)
        self.assertLess(raw, bridge_process)
        self.assertLess(bridge_process, bridge_gate)
        self.assertLess(bridge_gate, fastlio_process)
        self.assertLess(fastlio_process, fastlio_gate)
        self.assertLess(fastlio_gate, committed)

    def test_failure_cleanup_targets_only_processes_started_by_this_launch(self):
        self.assertIn('STARTED_PIDS+=("$pid")', self.script)
        self.assertIn('STARTED_IDENTITIES+=("$identity")', self.script)
        self.assertIn('current_identity" == "$expected_identity', self.script)
        self.assertIn("cleanup_started_processes", self.script)
        self.assertIn("trap on_exit EXIT", self.script)
        self.assertIn("PIPELINE_COMMITTED=1", self.script)


if __name__ == "__main__":
    unittest.main()
