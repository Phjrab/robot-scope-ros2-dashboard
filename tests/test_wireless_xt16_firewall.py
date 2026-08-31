import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wireless_xt16_firewall.py"
SERVICE = ROOT / "deploy" / "robot-scope-wireless-firewall.service.example"
SPEC = importlib.util.spec_from_file_location("wireless_xt16_firewall", SCRIPT)
firewall = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = firewall
assert SPEC.loader is not None
SPEC.loader.exec_module(firewall)


class FakeIptables:
    def __init__(self):
        self.chain = False
        self.rules = []
        self.jump = False
        self.calls = []

    def __call__(self, argv, **_kwargs):
        values = tuple(argv)
        self.calls.append(values)
        if values == (firewall.IPTABLES, "--version"):
            return subprocess.CompletedProcess(values, 0, "iptables v1.8.7 (legacy)\n", "")
        if values[:5] == (firewall.IP, "-o", "link", "show", "dev"):
            return subprocess.CompletedProcess(values, 0, "2: eno1: <UP>\n", "")
        args = values[3:]
        if args == ("-S", firewall.CHAIN):
            if not self.chain:
                return subprocess.CompletedProcess(values, 1, "", "")
            lines = [f"-N {firewall.CHAIN}"] + ["-A " + " ".join(rule) for rule in self.rules]
            return subprocess.CompletedProcess(values, 0, "\n".join(lines) + "\n", "")
        if args == ("-S",):
            lines = ["-P INPUT ACCEPT"]
            if self.jump:
                lines.append("-A " + " ".join(firewall._JUMP))
            return subprocess.CompletedProcess(values, 0, "\n".join(lines) + "\n", "")
        if args == ("-N", firewall.CHAIN):
            self.chain = True
            return subprocess.CompletedProcess(values, 0, "", "")
        if args[:1] == ("-A",):
            self.rules.append(args[1:])
            return subprocess.CompletedProcess(values, 0, "", "")
        if args == ("-I", *firewall._JUMP):
            self.jump = True
            return subprocess.CompletedProcess(values, 0, "", "")
        if args[:1] == ("-C",):
            target = args[1:]
            present = target == firewall._JUMP and self.jump or target in self.rules
            return subprocess.CompletedProcess(values, 0 if present else 1, "", "")
        if args == ("-D", *firewall._JUMP):
            self.jump = False
            return subprocess.CompletedProcess(values, 0, "", "")
        if args == ("-F", firewall.CHAIN):
            self.rules.clear()
            return subprocess.CompletedProcess(values, 0, "", "")
        if args == ("-X", firewall.CHAIN):
            self.chain = False
            return subprocess.CompletedProcess(values, 0, "", "")
        raise AssertionError(values)


class WirelessXt16FirewallTests(unittest.TestCase):
    def test_install_status_remove_are_exact_and_idempotent(self):
        fake = FakeIptables()
        with mock.patch.object(os, "geteuid", return_value=0):
            firewall.install(runner=fake)
            firewall.install(runner=fake)
            firewall.status(runner=fake)
            firewall.remove(runner=fake)
        self.assertFalse(fake.chain)
        self.assertFalse(fake.jump)
        flattened = " ".join(" ".join(call) for call in fake.calls)
        for value in ("192.168.50.30/32", "192.168.50.10/32", "46236", "46020", "2368"):
            self.assertIn(value, flattened)
        for forbidden in ("FORWARD", "MASQUERADE", "nat", "0.0.0.0"):
            self.assertNotIn(forbidden, flattened)
        self.assertIn((firewall.CHAIN, "-j", "RETURN"), firewall._RULES)
        self.assertTrue(all("-i" not in rule for rule in firewall._RULES))
        self.assertIn("-i", firewall._JUMP)

    def test_unknown_existing_chain_fails_without_mutation(self):
        fake = FakeIptables()
        fake.chain = True
        fake.rules = [(firewall.CHAIN, "-j", "ACCEPT")]
        with mock.patch.object(os, "geteuid", return_value=0):
            with self.assertRaisesRegex(firewall.FirewallError, "unexpected rules"):
                firewall.install(runner=fake)
        mutations = {"-N", "-A", "-I", "-D", "-F", "-X"}
        self.assertFalse(any(call[3] in mutations for call in fake.calls if len(call) > 3))

    def test_runtime_is_root_fixed_interface_and_legacy_only(self):
        with self.assertRaisesRegex(firewall.FirewallError, "root is required"):
            firewall.status(runner=FakeIptables())
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("ROBOT_SCOPE_", source.replace("ROBOT_SCOPE_WIRELESS", ""))

    def test_service_is_privileged_bounded_and_separate_from_dashboard(self):
        service = SERVICE.read_text(encoding="utf-8")
        for value in (
            "Before=robot-scope.service robot-scope-wireless-imu-receiver.service",
            "User=root",
            "CapabilityBoundingSet=CAP_NET_ADMIN",
            "NoNewPrivileges=true",
            "RemainAfterExit=yes",
            "WantedBy=multi-user.target",
        ):
            self.assertIn(value, service)
        for forbidden in ("ExecStart=/usr/sbin/iptables", "sudo", "reboot", "enable --now"):
            self.assertNotIn(forbidden, service)


if __name__ == "__main__":
    unittest.main()
