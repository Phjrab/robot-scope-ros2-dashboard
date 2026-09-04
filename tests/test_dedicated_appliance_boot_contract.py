import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_DOC = ROOT / "docs" / "INSTALL.md"
ROLLBACK_DOC = ROOT / "docs" / "UPDATE_ROLLBACK.md"
INSTALLER = ROOT / "scripts" / "install_ubuntu.sh"
DEFAULT_ENV_EXAMPLE = ROOT / "deploy" / "robot-scope.env.example"
DASHBOARD_RELEASE_DROP_IN = (
    ROOT / "deploy" / "robot-scope-dashboard-release-symlink.conf.example"
)
DASHBOARD_NETWORK_HELPER = (
    ROOT
    / "deploy"
    / "robot-scope-dashboard-appliance-network-ready.py.example"
)
DASHBOARD_APPLIANCE_DROP_IN = (
    ROOT / "deploy" / "robot-scope-dashboard-appliance.conf.example"
)
ROBOT_NETWORK_HELPER = (
    ROOT / "deploy" / "robot-scope-appliance-network-ready.py.example"
)
ROBOT_NETWORK_DROP_IN = (
    ROOT
    / "deploy"
    / "robot-scope-robot-side-appliance-network-ready.conf.example"
)

EXTERNAL_BOOT_UNITS = ("robot-scope.service",)
ROBOT_BOOT_UNITS = (
    "robot-scope-control-bridge.service",
    "robot-scope-xt16-wireless-relay.service",
)
ALLOWED_BOOT_UNITS = set(EXTERNAL_BOOT_UNITS + ROBOT_BOOT_UNITS)


def markdown_section(source: str, heading: str) -> str:
    marker = next(
        line for line in source.splitlines() if line.rstrip() == heading
    )
    level = len(marker) - len(marker.lstrip("#"))
    start = source.index(marker) + len(marker)
    remainder = source[start:]
    following = re.search(rf"(?m)^#{{1,{level}}} .+$", remainder)
    return remainder[: following.start()] if following else remainder


def normalized(source: str) -> str:
    return " ".join(source.split())


def exact_systemctl_units(source: str, action: str) -> tuple[str, ...]:
    commands = re.findall(
        rf"(?m)^sudo systemctl {re.escape(action)} ([^\n]+)$",
        source,
    )
    units: list[str] = []
    for command in commands:
        tokens = command.split()
        if any(token.startswith("-") for token in tokens):
            raise AssertionError(f"{action} command must not add flags: {command}")
        units.extend(tokens)
    return tuple(units)


class DedicatedApplianceBootContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.install = INSTALL_DOC.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK_DOC.read_text(encoding="utf-8")
        cls.install_section = markdown_section(
            cls.install,
            "### 전용 appliance 부팅 자동 시작 opt-in",
        )
        cls.rollback_section = markdown_section(
            cls.rollback,
            "## 전용 appliance enable 상태와 cold-boot 검증",
        )

    def test_boot_enable_allowlist_is_exact_and_host_scoped(self):
        enabled = exact_systemctl_units(self.install_section, "enable")
        self.assertEqual(enabled, EXTERNAL_BOOT_UNITS + ROBOT_BOOT_UNITS)
        self.assertEqual(set(enabled), ALLOWED_BOOT_UNITS)

        external_commands, robot_commands = self.install_section.split(
            "탑재 Jetson:", 1
        )
        external_commands = external_commands.rsplit("외부 dashboard Orin:", 1)[1]
        self.assertEqual(
            exact_systemctl_units(external_commands, "enable"),
            EXTERNAL_BOOT_UNITS,
        )
        self.assertEqual(
            exact_systemctl_units(robot_commands, "enable"),
            ROBOT_BOOT_UNITS,
        )

        named_units = set(
            re.findall(r"\brobot-scope(?:-[a-z0-9]+)*\.service\b", self.install_section)
        )
        self.assertEqual(named_units, ALLOWED_BOOT_UNITS)

    def test_installer_and_helpers_remain_outside_boot_enablement(self):
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertNotRegex(
            installer,
            r"(?m)^\s*(?:sudo\s+)?systemctl\s+enable(?:\s|$)",
        )
        self.assertIn("installed without enabling", installer)
        self.assertIn("existing enablement was unchanged", installer)
        self.assertNotIn("robot-scope-service-lifecycle.sudoers", installer)
        self.assertNotIn("robot-scope-xt16-wireless-relay.service", installer)
        self.assertNotIn(
            "ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER",
            DEFAULT_ENV_EXAMPLE.read_text(encoding="utf-8"),
        )

        policy = normalized(self.install_section)
        for required in (
            "모든 Robot Scope unit을 계속 `disabled`/수동 시작으로 유지합니다",
            "`scripts/install_ubuntu.sh`도 service를 설치할 수는 있지만 enable하거나 시작하지 않습니다",
            "다른 `robot-scope-*` unit, camera relay, wireless IMU/odometry sender·receiver, FAST-LIO",
            "Browser API와 제한된 SSH lifecycle helper에도 `enable`/`disable`, wildcard, 임의 unit 이름 또는 host 선택 권한을 추가하지 않습니다",
        ):
            self.assertIn(required, policy)
        self.assertNotIn("/etc/sudoers.d", self.install_section)
        self.assertNotIn("visudo", self.install_section)

    def test_dashboard_release_drop_in_only_repoints_the_dashboard_service(self):
        source = DASHBOARD_RELEASE_DROP_IN.read_text(encoding="utf-8")
        directives = tuple(
            line.strip()
            for line in source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertEqual(
            directives,
            (
                "[Service]",
                "WorkingDirectory=/home/jetson_orin_nano/robot-scope",
                "ExecStart=",
                "ExecStart=/home/jetson_orin_nano/robot-scope/scripts/run_go2_dashboard_supervisor.py",
            ),
        )
        self.assertFalse(any(".service" in line for line in directives))
        self.assertFalse(
            any(
                line.startswith(("WantedBy=", "Requires=", "Wants=", "After="))
                for line in directives
            )
        )
        self.assertNotIn("ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER", source)

    def test_dashboard_network_gate_is_fixed_bounded_and_read_only(self):
        source = DASHBOARD_NETWORK_HELPER.read_text(encoding="utf-8")
        namespace = {
            "__name__": "robot_scope_dashboard_appliance_network_ready_test"
        }
        exec(compile(source, str(DASHBOARD_NETWORK_HELPER), "exec"), namespace)

        self.assertEqual(
            namespace["EXPECTED_INTERFACE"],
            ("eno1", "192.168.50.10", "255.255.255.0"),
        )
        self.assertEqual(namespace["TIMEOUT_SECONDS"], 60.0)
        self.assertEqual(namespace["POLL_SECONDS"], 1.0)
        for forbidden in (
            "subprocess",
            "os.system",
            "nmcli",
            "systemctl",
            "ip address add",
            "ip link set",
        ):
            self.assertNotIn(forbidden, source)

        original_interface_state = namespace["_interface_state"]
        try:
            namespace["_interface_state"] = lambda interface: (
                True,
                "192.168.50.10",
                "255.255.255.0",
            )
            self.assertTrue(namespace["_fixed_interface_ready"]())
            namespace["_interface_state"] = lambda interface: (
                False,
                "192.168.50.10",
                "255.255.255.0",
            )
            self.assertFalse(namespace["_fixed_interface_ready"]())
        finally:
            namespace["_interface_state"] = original_interface_state

        sleep_calls: list[float] = []
        attempts = iter((False, True))
        self.assertTrue(
            namespace["wait_until_ready"](
                probe=lambda: next(attempts),
                monotonic=iter((0.0, 0.0)).__next__,
                sleep=sleep_calls.append,
            )
        )
        self.assertEqual(sleep_calls, [1.0])

        bounded_sleep_calls: list[float] = []
        self.assertFalse(
            namespace["wait_until_ready"](
                probe=lambda: False,
                monotonic=iter((0.0, 60.0)).__next__,
                sleep=bounded_sleep_calls.append,
            )
        )
        self.assertEqual(bounded_sleep_calls, [])

    def test_dashboard_appliance_drop_in_is_separate_and_exact(self):
        source = DASHBOARD_APPLIANCE_DROP_IN.read_text(encoding="utf-8")
        directives = tuple(
            line.strip()
            for line in source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertEqual(
            directives,
            (
                "[Unit]",
                "Wants=NetworkManager-wait-online.service",
                "After=NetworkManager-wait-online.service",
                "[Service]",
                "ExecStartPre=/usr/bin/python3 "
                "/usr/local/libexec/robot-scope/"
                "robot_scope_dashboard_appliance_network_ready.py",
                "Environment=ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER=1",
            ),
        )
        for forbidden in (
            "StartLimitIntervalSec=",
            "StartLimitBurst=",
            "Restart=",
            "RestartSec=",
            "WorkingDirectory=",
            "ExecStart=",
            "WantedBy=",
        ):
            self.assertNotIn(forbidden, source)

        for required in (
            "deploy/robot-scope-dashboard-appliance-network-ready.py.example",
            "/usr/local/libexec/robot-scope/robot_scope_dashboard_appliance_network_ready.py",
            "/etc/systemd/system/robot-scope.service.d/10-appliance-network-ready.conf",
            "`ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER=1`",
        ):
            self.assertIn(required, self.install_section)

    def test_boot_opt_in_cannot_resume_autonomy_or_motion(self):
        policy = normalized(self.install_section)
        for required in (
            "자동 시작은 lease를 획득하거나 ARM, deadman, Move/action, 비영점 명령 또는 이전 동작을 복구하는 권한이 아닙니다",
            "XT16 relay는 고정 peer로 센서 payload만 전달하며 Mapping/Nav/Mission, Dataset Capture 또는 goal을 시작하지 않습니다",
            "기존 relay가 이미 active이면 preview lifecycle은 이를 자기 소유로 간주하거나 cleanup에서 중지하면 안 됩니다",
        ):
            self.assertIn(required, policy)

    def test_robot_network_gate_is_fixed_bounded_and_read_only(self):
        source = ROBOT_NETWORK_HELPER.read_text(encoding="utf-8")
        namespace = {"__name__": "robot_scope_appliance_network_ready_test"}
        exec(compile(source, str(ROBOT_NETWORK_HELPER), "exec"), namespace)

        self.assertEqual(
            namespace["EXPECTED_INTERFACES"],
            {
                "eth0": ("192.168.123.18", "255.255.255.0"),
                "wlan0": ("192.168.50.30", "255.255.255.0"),
            },
        )
        self.assertEqual(namespace["TIMEOUT_SECONDS"], 60.0)
        self.assertEqual(namespace["POLL_SECONDS"], 1.0)
        for forbidden in (
            "subprocess",
            "os.system",
            "nmcli",
            "systemctl",
            "ip address add",
            "ip link set",
        ):
            self.assertNotIn(forbidden, source)

        state_by_interface = {
            "eth0": (True, "192.168.123.18", "255.255.255.0"),
            "wlan0": (True, "192.168.50.30", "255.255.255.0"),
        }
        original_interface_state = namespace["_interface_state"]
        try:
            namespace["_interface_state"] = state_by_interface.get
            self.assertTrue(namespace["_all_interfaces_ready"]())
            state_by_interface["wlan0"] = (
                False,
                "192.168.50.30",
                "255.255.255.0",
            )
            self.assertFalse(namespace["_all_interfaces_ready"]())
        finally:
            namespace["_interface_state"] = original_interface_state

        sleep_calls: list[float] = []
        attempts = iter((False, True))
        self.assertTrue(
            namespace["wait_until_ready"](
                probe=lambda: next(attempts),
                monotonic=iter((0.0, 0.0)).__next__,
                sleep=sleep_calls.append,
            )
        )
        self.assertEqual(sleep_calls, [1.0])

        bounded_sleep_calls: list[float] = []
        self.assertFalse(
            namespace["wait_until_ready"](
                probe=lambda: False,
                monotonic=iter((0.0, 60.0)).__next__,
                sleep=bounded_sleep_calls.append,
            )
        )
        self.assertEqual(bounded_sleep_calls, [])

    def test_robot_network_drop_in_only_adds_bounded_readiness(self):
        source = ROBOT_NETWORK_DROP_IN.read_text(encoding="utf-8")
        directives = tuple(
            line.strip()
            for line in source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertEqual(
            directives,
            (
                "[Unit]",
                "Wants=NetworkManager-wait-online.service",
                "After=NetworkManager-wait-online.service",
                "[Service]",
                "ExecStartPre=/usr/bin/python3 "
                "/usr/local/libexec/robot-scope/"
                "robot_scope_appliance_network_ready.py",
            ),
        )
        for forbidden in (
            "StartLimitIntervalSec=",
            "StartLimitBurst=",
            "Restart=",
            "RestartSec=",
            "ExecStart=",
            "WantedBy=",
        ):
            self.assertNotIn(forbidden, source)

        for required in (
            "deploy/robot-scope-appliance-network-ready.py.example",
            "/usr/local/libexec/robot-scope/robot_scope_appliance_network_ready.py",
            "/etc/systemd/system/robot-scope-control-bridge.service.d/10-appliance-network-ready.conf",
            "/etc/systemd/system/robot-scope-xt16-wireless-relay.service.d/10-appliance-network-ready.conf",
            "`StartLimitIntervalSec=60`, `StartLimitBurst=5`가 그대로 적용됩니다",
        ):
            self.assertIn(required, self.install_section)

    def test_rollback_preserves_only_exact_allowlist_and_requires_cold_boot(self):
        disabled = exact_systemctl_units(self.rollback_section, "disable")
        self.assertEqual(disabled, EXTERNAL_BOOT_UNITS + ROBOT_BOOT_UNITS)
        self.assertEqual(set(disabled), ALLOWED_BOOT_UNITS)
        named_units = set(
            re.findall(r"\brobot-scope(?:-[a-z0-9]+)*\.service\b", self.rollback_section)
        )
        self.assertEqual(named_units, ALLOWED_BOOT_UNITS)

        policy = normalized(self.rollback_section)
        for required in (
            "이것만이 부팅 자동 시작 allowlist이며 installer는 업데이트나 롤백 중 이 상태를 변경하지 않습니다",
            "이전에 `enabled`였던 unit만 exact `systemctl enable <exact-unit>`로 복원하고, 이전 값이 `disabled`였던 일반 설치는 그대로 둡니다",
            "Browser나 제한된 SSH helper에 enable/disable 권한을 추가하거나 다른 unit을 함께 변경하지 않습니다",
            "이 절차는 ARM, lease, initial pose, goal, motion 또는 Mapping start/save를 실행하지 않습니다",
            "Move, non-zero Move, action과 malformed Move가 모두 0인지 확인합니다",
            "StopMove count가 증가하는 것은 예상되는 안전 동작",
            "실제 MainPID의 `/proc/<MainPID>/environ`",
            "`EnvironmentFile=`에 같은 key가 생기면 실제 process 값이 우선 증거입니다",
            "cold boot",
            "PASS",
        ):
            self.assertIn(required, policy)

    def test_network_autoconnect_alone_is_not_accepted_as_boot_readiness(self):
        policy = normalized(self.rollback_section)
        for required in (
            "`connection.autoconnect=yes`",
            "`NetworkManager-wait-online.service`",
            "`disabled`/`inactive`",
            "`NOT_ACCEPTED`",
            "60초",
            "192.168.50.10/24",
            "192.168.123.18/24",
            "192.168.50.30/24",
        ):
            self.assertIn(required, policy)


if __name__ == "__main__":
    unittest.main()
