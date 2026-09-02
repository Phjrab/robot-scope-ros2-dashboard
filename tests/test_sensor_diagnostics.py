import json
import unittest
from pathlib import Path

from robot_dashboard.runtime_status import ros_transport_status


ROOT = Path(__file__).resolve().parents[1]


class SensorDiagnosticsTests(unittest.TestCase):
    def test_go2_profile_observes_both_lowstate_aliases(self):
        profile = json.loads((ROOT / "config" / "go2.json").read_text(encoding="utf-8"))
        self.assertIn("/lowstate", profile["observed_topics"])
        self.assertIn("/lf/lowstate", profile["observed_topics"])

    def test_go2_runner_marks_bound_and_offline_startup_modes(self):
        script = (ROOT / "scripts" / "run_go2_humble.sh").read_text(encoding="utf-8")
        self.assertIn('ROBOT_SCOPE_DDS_MODE="offline_viewer"', script)
        self.assertIn('ROBOT_SCOPE_DDS_INTERFACE_READY="0"', script)
        self.assertIn('ROBOT_SCOPE_DDS_MODE="go2_interface"', script)
        self.assertIn('ROBOT_SCOPE_DDS_MODE="wireless_gateway"', script)
        self.assertIn('ROBOT_SCOPE_DDS_INTERFACE_READY="1"', script)
        self.assertIn('ROBOT_SCOPE_ROBOT_GATEWAY_IP:-192.168.50.30', script)
        self.assertIn('setup_wireless_mapping_ros2_humble.sh', script)

    def test_runtime_status_distinguishes_offline_viewer_from_go2_interface(self):
        offline = ros_transport_status({
            "ROBOT_SCOPE_DDS_MODE": "offline_viewer",
            "ROBOT_SCOPE_DDS_INTERFACE_READY": "0",
        })
        self.assertFalse(offline["interface_ready"])
        self.assertTrue(offline["offline_viewer"])
        self.assertFalse(offline["dds_uri_configured"])

        online = ros_transport_status({
            "ROBOT_SCOPE_DDS_MODE": "go2_interface",
            "ROBOT_SCOPE_DDS_INTERFACE_READY": "1",
            "ROBOT_SCOPE_DDS_INTERFACE": "eno1",
            "RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
            "CYCLONEDDS_URI": "private-value-not-returned",
        })
        self.assertTrue(online["interface_ready"])
        self.assertFalse(online["offline_viewer"])
        self.assertEqual(online["interface"], "eno1")
        self.assertTrue(online["dds_uri_configured"])
        self.assertNotIn("private-value-not-returned", online.values())

        wireless = ros_transport_status({
            "ROBOT_SCOPE_DDS_MODE": "wireless_gateway",
            "ROBOT_SCOPE_DDS_INTERFACE_READY": "1",
            "ROBOT_SCOPE_DDS_INTERFACE": "eno1",
            "RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
            "CYCLONEDDS_URI": "private-wireless-value",
        }, require_go2_interface=True)
        self.assertTrue(wireless["interface_ready"])
        self.assertFalse(wireless["offline_viewer"])
        self.assertFalse(wireless["dedicated_interface_required"])
        self.assertNotIn("private-wireless-value", wireless.values())

    def test_runtime_status_rejects_untrusted_labels_and_invalid_flags(self):
        status = ros_transport_status({
            "ROBOT_SCOPE_DDS_MODE": "unexpected",
            "ROBOT_SCOPE_DDS_INTERFACE_READY": "sometimes",
            "ROBOT_SCOPE_DDS_INTERFACE": "eno1<script>",
        })
        self.assertEqual(status["mode"], "unknown")
        self.assertIsNone(status["interface_ready"])
        self.assertEqual(status["interface"], "")

    def test_go2_direct_launch_requires_cyclone_rmw_and_uri_but_generic_does_not(self):
        go2 = ros_transport_status(
            {"RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp"},
            require_go2_interface=True,
        )
        self.assertEqual(go2["mode"], "offline_viewer")
        self.assertFalse(go2["interface_ready"])
        self.assertTrue(go2["offline_viewer"])

        configured = ros_transport_status(
            {
                "RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
                "CYCLONEDDS_URI": "configured-but-private",
            },
            require_go2_interface=True,
        )
        self.assertEqual(configured["mode"], "go2_interface")
        self.assertTrue(configured["interface_ready"])

        generic = ros_transport_status({}, require_go2_interface=False)
        self.assertEqual(generic["mode"], "unknown")
        self.assertIsNone(generic["interface_ready"])
        self.assertFalse(generic["offline_viewer"])


if __name__ == "__main__":
    unittest.main()
