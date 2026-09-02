import ipaddress
import json
import threading
import unittest
from pathlib import Path

from robot_dashboard.capabilities import (
    CAPABILITY_NAMES,
    capabilities_for_robot_type,
)
from robot_dashboard.discovery import (
    DiscoveryBusy,
    LocalRobotDiscovery,
    UnknownRobotType,
    infer_robot_type,
    is_local_robot_ipv4,
    normalize_hostname,
    public_robot_types,
    robot_type_definition,
)


ROOT = Path(__file__).resolve().parents[1]


def interface(name, address, network):
    return {
        "name": name,
        "address": address,
        "network": network,
        "_network": ipaddress.ip_network(network),
    }


class FixtureDiscovery(LocalRobotDiscovery):
    def __init__(self):
        super().__init__()
        self.probed = []

    def _local_interfaces(self):
        return [
            interface("eno1", "192.168.123.99", "192.168.123.0/24"),
            interface("wlan0", "10.100.0.89", "10.100.0.0/23"),
        ]

    def _default_interface(self):
        return "wlan0"

    def _neighbors(self, interfaces):
        return {
            "10.100.0.42": {"interface": "wlan0", "source": "neighbor"},
            "192.168.123.20": {"interface": "eno1", "source": "neighbor"},
        }

    def _mdns_hosts(self, interfaces):
        return {
            "10.100.0.42": {
                "interface": "wlan0",
                "source": "mdns",
                "hostname": "turtlebot3.local",
            }
        }

    def _probe_many(self, addresses):
        self.probed = list(addresses)
        responsive = {
            "192.168.123.161": 0.31,
            "192.168.123.20": 0.52,
            "10.100.0.42": 1.25,
        }
        return {address: responsive[address] for address in addresses if address in responsive}

    def _resolve_many(self, addresses):
        return {}


class DiscoveryMetadataTests(unittest.TestCase):
    def test_catalog_has_stable_mobile_robot_ids_and_models(self):
        types = public_robot_types()
        self.assertEqual([item["id"] for item in types], ["go2", "turtlebot"])
        self.assertEqual(
            types[0]["model"]["asset_url"],
            "/static/assets/go2/go2-official-lite.json",
        )
        self.assertEqual(
            types[1]["model"]["urdf_url"],
            "/static/assets/turtlebot/source/turtlebot3_description/urdf/turtlebot3_burger.urdf",
        )
        self.assertEqual(types[1]["model"]["fidelity"], "official-derived")
        self.assertEqual(types[0]["capabilities"], capabilities_for_robot_type("go2"))
        self.assertEqual(
            types[1]["capabilities"],
            capabilities_for_robot_type("turtlebot"),
        )
        self.assertEqual(tuple(types[0]["capabilities"]), CAPABILITY_NAMES)
        for item in types:
            self.assertNotIn("known_ips", item)
            self.assertNotIn("hostname_hints", item)

    def test_unknown_type_and_untrusted_hostname_are_rejected(self):
        with self.assertRaises(UnknownRobotType):
            robot_type_definition("unsupported")
        with self.assertRaises(UnknownRobotType):
            robot_type_definition("so-101")
        self.assertEqual(normalize_hostname(" TurtleBot3.Local. "), "turtlebot3.local")
        for value in ("bad host", "<script>", "line\nbreak", "a" * 254):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_hostname(value)

    def test_only_rfc1918_or_link_local_hosts_are_selectable(self):
        for value in ("10.1.2.3", "172.16.0.2", "192.168.123.161", "169.254.5.6"):
            self.assertTrue(is_local_robot_ipv4(value), value)
        for value in ("127.0.0.1", "0.0.0.0", "8.8.8.8", "224.0.0.1", "::1"):
            self.assertFalse(is_local_robot_ipv4(value), value)

    def test_explicit_profile_robot_type_overrides_name_inference(self):
        self.assertEqual(
            infer_robot_type({"name": "misleading Unitree Go2", "robot_type": "turtlebot"}),
            "turtlebot",
        )
        self.assertEqual(infer_robot_type({"name": "anything", "robot_type": "so101"}), "")
        self.assertEqual(infer_robot_type({"name": "Unitree Go2", "robot_type": ""}), "")
        self.assertEqual(infer_robot_type({"name": "Unitree Go2", "robot_type": "invalid"}), "")

    def test_committed_startup_profiles_declare_safe_robot_type(self):
        expected = {
            "generic.json": "",
            "go2.json": "go2",
            "turtlebot.json": "turtlebot",
        }
        for filename, robot_type in expected.items():
            with self.subTest(filename=filename):
                payload = json.loads((ROOT / "config" / filename).read_text(encoding="utf-8"))
                self.assertEqual(payload["robot_type"], robot_type)
                self.assertEqual(infer_robot_type(payload), robot_type)
                self.assertEqual(
                    set(capabilities_for_robot_type(robot_type)),
                    set(CAPABILITY_NAMES),
                )
                if robot_type != "go2":
                    self.assertFalse(payload["control"]["enabled"])


class DiscoveryScanTests(unittest.TestCase):
    def test_go2_known_network_overrides_default_route_and_scan_is_bounded(self):
        scanner = FixtureDiscovery()
        result = scanner.discover("go2")
        self.assertEqual(result["scan_scope"]["interface"], "eno1")
        self.assertEqual(result["scan_scope"]["network"], "192.168.123.0/24")
        self.assertLessEqual(len(scanner.probed), 256)
        go2 = next(item for item in result["candidates"] if item["ip"] == "192.168.123.161")
        self.assertEqual(go2["confidence"], 0.99)
        self.assertEqual(go2["interface"], "eno1")
        self.assertNotIn("10.100.0.42", {item["ip"] for item in result["candidates"]})

    def test_generic_type_uses_default_lan_and_hostname_confidence(self):
        scanner = FixtureDiscovery()
        result = scanner.discover("turtlebot")
        self.assertEqual(result["scan_scope"]["interface"], "wlan0")
        # The host has /23, but active scanning is limited to the local /24.
        self.assertEqual(result["scan_scope"]["network"], "10.100.0.0/24")
        candidate = next(item for item in result["candidates"] if item["ip"] == "10.100.0.42")
        self.assertEqual(candidate["hostname"], "turtlebot3.local")
        self.assertEqual(candidate["confidence"], 0.85)
        self.assertTrue(0.0 <= candidate["confidence"] <= 1.0)
        self.assertNotIn("192.168.123.20", {item["ip"] for item in result["candidates"]})

    def test_go2_wireless_management_lan_prefers_onboard_gateway(self):
        class WirelessFixture(FixtureDiscovery):
            def _local_interfaces(self):
                return [
                    interface("eno1", "192.168.50.10", "192.168.50.0/24"),
                ]

            def _default_interface(self):
                return "eno1"

            def _neighbors(self, interfaces):
                return {
                    "192.168.50.30": {"interface": "eno1", "source": "neighbor"},
                }

            def _mdns_hosts(self, interfaces):
                return {}

            def _probe_many(self, addresses):
                self.probed = list(addresses)
                return {"192.168.50.30": 1.2} if "192.168.50.30" in addresses else {}

        result = WirelessFixture().discover("go2")
        self.assertEqual(result["connection_kind"], "gateway_or_robot")
        self.assertEqual(result["scan_scope"]["network"], "192.168.50.0/24")
        self.assertEqual(result["candidates"][0]["ip"], "192.168.50.30")
        self.assertEqual(result["candidates"][0]["confidence"], 0.99)

    def test_unsupported_product_type_cannot_start_discovery(self):
        scanner = FixtureDiscovery()
        with self.assertRaises(UnknownRobotType):
            scanner.discover("so-101")

    def test_selection_must_stay_on_a_directly_attached_interface(self):
        scanner = FixtureDiscovery()
        self.assertEqual(
            scanner.validate_target("go2", "192.168.123.161"),
            "192.168.123.161",
        )
        self.assertEqual(scanner.validate_target("turtlebot", "10.100.1.200"), "10.100.1.200")
        with self.assertRaisesRegex(ValueError, "직접 연결"):
            scanner.validate_target("turtlebot", "172.20.1.2")
        with self.assertRaisesRegex(ValueError, "로컬 RFC1918"):
            scanner.validate_target("go2", "8.8.8.8")
        for invalid in ("10.100.0.89", "10.100.0.0", "10.100.1.255"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "자체 IP|network/broadcast"):
                    scanner.validate_target("turtlebot", invalid)

    def test_repeated_request_uses_type_scoped_cache(self):
        scanner = FixtureDiscovery()
        first = scanner.discover("go2")
        first_probe = scanner.probed
        scanner.probed = []
        second = scanner.discover("go2")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertTrue(first_probe)
        self.assertFalse(scanner.probed)

    def test_duplicate_requests_share_one_inflight_scan(self):
        started = threading.Event()
        release = threading.Event()

        class BlockingDiscovery(LocalRobotDiscovery):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def _scan(self, definition):
                self.calls += 1
                started.set()
                release.wait(timeout=2.0)
                return {
                    "robot_type": definition["id"],
                    "candidates": [],
                    "interfaces": [],
                    "cached": False,
                }

        scanner = BlockingDiscovery()
        results = []
        errors = []

        def run(robot_type):
            try:
                results.append(scanner.discover(robot_type))
            except Exception as exc:
                errors.append(exc)

        first = threading.Thread(target=run, args=("go2",))
        second = threading.Thread(target=run, args=("turtlebot",))
        first.start()
        self.assertTrue(started.wait(timeout=1.0))
        second.start()
        release.set()
        first.join(timeout=2.0)
        second.join(timeout=2.0)
        self.assertEqual(scanner.calls, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], DiscoveryBusy)


if __name__ == "__main__":
    unittest.main()
