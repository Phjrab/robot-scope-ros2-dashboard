import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WIRELESS_CONFIG = ROOT / "config" / "hesai_xt16_wireless.yaml"
WIRED_CONFIG = ROOT / "config" / "hesai_xt16.yaml"
DECISION = ROOT / "docs" / "HESAI_WIRELESS_INPUT_CONTRACT.md"
DEPENDENCIES = ROOT / "config" / "ros_dependencies_humble.json"


class HesaiWirelessProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile_text = WIRELESS_CONFIG.read_text(encoding="utf-8")
        cls.profile = yaml.safe_load(cls.profile_text)["lidar"][0]
        cls.decision = DECISION.read_text(encoding="utf-8")

    def test_wireless_udp_receive_tuple_is_exact_and_filterable(self):
        driver = self.profile["driver"]
        udp = driver["lidar_udp_type"]
        self.assertEqual(driver["source_type"], 1)
        self.assertEqual(udp["host_ip_address"], "192.168.50.10")
        self.assertEqual(udp["udp_port"], 2368)
        self.assertEqual(udp["device_ip_address"], "192.168.50.30")
        self.assertEqual(driver["device_udp_src_port"], 46236)
        self.assertEqual(udp["multicast_ip_address"], "")
        self.assertEqual(udp["fault_message_port"], 0)
        self.assertEqual(driver["device_fault_port"], 0)
        self.assertGreaterEqual(driver["device_udp_src_port"], 1024)
        self.assertLessEqual(driver["device_udp_src_port"], 65535)

    def test_ptc_is_disabled_and_only_fixed_private_files_are_used(self):
        udp = self.profile["driver"]["lidar_udp_type"]
        self.assertFalse(udp["use_ptc_connected"])
        self.assertEqual(udp["ptc_port"], 9347)
        self.assertEqual(udp["host_ptc_port"], 0)
        self.assertEqual(udp["ptc_mode"], 0)
        self.assertEqual(
            udp["correction_file_path"],
            "/etc/robot-scope/hesai/xt16-correction.csv",
        )
        self.assertEqual(
            udp["firetimes_path"],
            "/etc/robot-scope/hesai/xt16-firetime.csv",
        )
        self.assertGreater(udp["recv_point_cloud_timeout"], 0)
        self.assertLessEqual(udp["recv_point_cloud_timeout"], 10)
        self.assertGreaterEqual(udp["ptc_connect_timeout"], 0)
        self.assertLessEqual(udp["ptc_connect_timeout"], 10)

    def test_profile_publishes_only_the_bounded_lidar_output(self):
        ros = self.profile["ros"]
        self.assertEqual(ros["ros_frame_id"], "hesai_lidar")
        self.assertEqual(ros["ros_send_point_cloud_topic"], "/lidar_points")
        self.assertTrue(ros["send_point_cloud_ros"])
        self.assertFalse(ros["send_packet_ros"])
        self.assertFalse(ros["send_imu_ros"])

    def test_profile_contains_no_general_network_or_artifact_override(self):
        for forbidden in (
            "0.0.0.0",
            "192.168.123.20",
            "192.168.123.99",
            "${",
            "localhost",
            "http://",
            "https://",
        ):
            self.assertNotIn(forbidden, self.profile_text)
        self.assertNotIn("/home/", self.profile_text)
        self.assertNotIn("correction/angle_correction", self.profile_text)

    def test_legacy_wired_profile_is_still_separate_and_unchanged(self):
        wired = yaml.safe_load(WIRED_CONFIG.read_text(encoding="utf-8"))[
            "lidar"
        ][0]
        udp = wired["driver"]["lidar_udp_type"]
        self.assertEqual(udp["device_ip_address"], "192.168.123.20")
        self.assertEqual(udp["host_ip_address"], "")
        self.assertTrue(udp["use_ptc_connected"])
        self.assertEqual(wired["driver"]["device_udp_src_port"], 0)

    def test_decision_is_bound_to_the_pinned_driver_and_sdk(self):
        dependencies = json.loads(DEPENDENCIES.read_text(encoding="utf-8"))
        hesai = dependencies["repositories"]["hesai_ros2"]
        self.assertEqual(
            hesai["commit"], "e7e112f0809f0eed5e3c81c55a1a0376474db234"
        )
        self.assertEqual(
            hesai["submodule_commit"],
            "9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168",
        )
        for contract in (
            "source_drive_common.hpp",
            "SocketSource",
            "hesai_lidar_sdk.hpp",
            "device_ip_address",
            "device_udp_src_port",
            "host_ip_address",
            "use_ptc_connected: false",
            "1024..65535",
        ):
            self.assertIn(contract, self.decision)

    def test_decision_keeps_calibration_private_and_proxy_blocked(self):
        for contract in (
            "xt16-calibration.manifest",
            "SHA-256 of both files",
            "Actual calibration contents, serial numbers and hashes are not",
            "PTC proxy is not required",
            "remains `BLOCKED`",
            "HW-2 remains `NOT_RUN`",
            "never starts Mapping",
        ):
            self.assertIn(contract, self.decision)


if __name__ == "__main__":
    unittest.main()
