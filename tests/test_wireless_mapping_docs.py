import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WirelessMappingDocumentationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adr = (
            ROOT / "docs" / "ADR_WIRELESS_XT16_FASTLIO_TRANSPORT.md"
        ).read_text(encoding="utf-8")
        cls.acceptance = (
            ROOT / "docs" / "WIRELESS_MAPPING_ACCEPTANCE.md"
        ).read_text(encoding="utf-8")
        cls.deployment = (
            ROOT / "docs" / "WIRELESS_MAPPING_DEPLOYMENT_PLAN.md"
        ).read_text(encoding="utf-8")

    def test_adr_freezes_the_measured_topology_and_narrow_data_boundary(self):
        for value in (
            "wlan0=192.168.50.30/24",
            "eth0=192.168.123.18/24",
            "eno1=192.168.50.10/24",
            "192.168.123.161",
            "192.168.123.20",
            "192.168.50.30:46236",
            "192.168.50.10:2368",
            "568-byte payload",
            "HMAC-SHA256",
        ):
            self.assertIn(value, self.adr)

        for forbidden in (
            "PointCloud2 over management Wi-Fi",
            "full `/lowstate`",
            "full ROS 2 DDS graph",
            "route, NAT, Linux bridge",
            "generic TCP/UDP proxy",
            "reuse of the Control Bridge HMAC key",
        ):
            self.assertIn(forbidden, self.adr)

    def test_adr_preserves_existing_safety_and_fail_closed_ownership(self):
        for invariant in (
            "DISARMED",
            "FORWARD DROP",
            "does not auto-start",
            "never automatic resume",
            "never creates a control lease",
            "disabled by default",
            "APPROVE_WIRELESS_XT16_DEPLOY",
        ):
            self.assertIn(invariant, self.adr)

        for owner in (
            "Hesai driver and `/lidar_points`",
            "cloud-only C++ conversion",
            "FAST-LIO and map lifecycle",
            "Nav2, Mission and motion coordination",
        ):
            self.assertIn(owner, self.adr)

    def test_acceptance_separates_gates_hardware_and_statuses(self):
        for gate in range(0, 8):
            self.assertIn(f"Gate {gate}", self.acceptance)
        for stage in range(1, 7):
            self.assertIn(f"HW-{stage}", self.acceptance)
        for result in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
            self.assertIn(result, self.acceptance)
        for status in (
            "CODE_READY",
            "XT16_RELAY_PASS",
            "LIDAR_PASS",
            "IMU_PASS",
            "CLOUD_PASS",
            "MAPPING_STATIONARY_PASS",
            "SOAK_PASS",
        ):
            self.assertIn(status, self.acceptance)

    def test_acceptance_keeps_deployment_motion_and_evidence_explicit(self):
        for contract in (
            "APPROVE_WIRELESS_XT16_DEPLOY",
            "APPROVE_STATIONARY_MAPPING_TEST",
            "physical remote/E-stop ready",
            "no control lease",
            "no automatic Mapping/Nav/Mission resume",
            "rate `>=4 Hz`",
            "age `<=1.0 s`",
            "age `<=0.5 s`",
            "jitter `<=300 ms`",
            "zero external `/lowstate`",
            "Gates 2, 3, 4 and 5 are repository-only PASS",
            "registered CTest PASS 1/1",
            "repository status is `CODE_READY`",
            "privileged network boundary is `PASS`",
            "external privileged network boundary is also `PASS`",
            "`ip_forward=1`",
            "accepted as evidence",
            "| HW-5 stationary FAST-LIO | `PASS` — `MAPPING_STATIONARY_PASS` |",
            "| HW-6 compound load | `NOT_RUN` |",
            "current hardware status is `MAPPING_STATIONARY_PASS`",
            "`10.007 Hz`",
            "`9.983 Hz`",
            "Commit `9bad38e`",
            "about `501.84 Hz`",
            "`9.998 Hz`",
            "maximum sampled header age `106.981 ms`",
            "no external UDP 2368/46020 listener",
            "zero external `/lowstate`",
            "no listener on UDP 46020",
            "survived an external-Orin reboot",
            "No sensor unit was enabled or started",
            "53,328 packets",
            "zero relay send errors",
        ):
            self.assertIn(contract, self.acceptance)

    def test_deployment_plan_is_fixed_peer_disabled_and_separately_approved(self):
        for contract in (
            "wlan0=192.168.50.30/24",
            "eth0=192.168.123.18/24",
            "eno1=192.168.50.10/24",
            "192.168.50.30:46236",
            "192.168.50.10:2368",
            "192.168.50.30:46020",
            "192.168.50.10:46020",
            "All three new sensor service units are installed disabled",
            "No sensor unit is enabled at boot",
            "is the only new unit enabled at boot",
            "APPROVE_WIRELESS_XT16_DEPLOY",
            "APPROVE_STATIONARY_MAPPING_TEST",
            "repository `CODE_READY`; HW-1 `XT16_RELAY_PASS`; HW-2",
            "`LIDAR_PASS`; HW-3 `IMU_PASS`; HW-4 `CLOUD_PASS`; HW-5",
            "`MAPPING_STATIONARY_PASS`; HW-6 `NOT_RUN`",
        ):
            self.assertIn(contract, self.deployment)

    def test_deployment_plan_preserves_network_control_and_private_state(self):
        for contract in (
            "add no `FORWARD`, NAT, MASQUERADE, bridge, route, multicast or DDS rule",
            "must not be printed, logged, passed as a command argument",
            "No PTC proxy is installed",
            "never starts Nav2, Mission, ARM, a control lease or a goal",
            "leaves maps, Dataset, private logs and calibration backups untouched",
            "HW-1 is `XT16_RELAY_PASS`, HW-2 is `LIDAR_PASS`, HW-3 is `IMU_PASS` and HW-4",
            "HW-5 is `MAPPING_STATIONARY_PASS`; HW-6 remains `NOT_RUN`",
            "No Nav2 or soak PASS",
            "about 502 Hz",
            "about 10 Hz",
            "process-group cleanup",
            "passes 1/1 through both colcon and direct CTest",
            "robot-side deployment and external checkout preserve rollback copies",
            "`iptables v1.8.4 (legacy)`",
            "`iptables v1.8.7 (legacy)`",
            "privileged network verification is cleared on both hosts",
        ):
            self.assertIn(contract, self.deployment)


if __name__ == "__main__":
    unittest.main()
