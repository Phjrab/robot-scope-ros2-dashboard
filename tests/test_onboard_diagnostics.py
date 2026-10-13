import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("onboard_diagnostics", ROOT / "scripts/robot_scope_onboard_diagnostics.py")
assert SPEC and SPEC.loader
diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostics)


def write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


class OnboardDiagnosticTests(unittest.TestCase):
    def test_runtime_sample_keeps_direct_frame_metrics_and_distinguishes_ros_ages(self):
        payloads = {
            "/api/v1/health": {"agent_ready": True},
            "/api/v1/cameras": {"sources": [{"id": "go2_front", "fps": 15, "frames": 31, "age_s": 0.02}]},
            "/api/v1/topics": {"topics": [{"name": "/lowstate", "hz": 100, "age_s": 0.03,
                                            "source_timestamp_age_s": 0.08, "jitter_ms": 4}]},
        }
        class Response:
            def __init__(self, value):
                self.value = value
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, limit):
                return json.dumps(self.value).encode()
        def fetch(url, **kwargs):
            return Response(payloads[url.split(":8088", 1)[1]])
        with mock.patch.object(diagnostics.urllib.request, "urlopen", side_effect=fetch):
            report = diagnostics.runtime_sample(8088)
        self.assertEqual(report["cameras"][0]["fps"], 15)
        self.assertEqual(report["cameras"][0]["frames"], 31)
        self.assertEqual(report["topics"][0]["source_timestamp_age_s"], 0.08)
        self.assertIn("callback receipt", report["topics"][0]["age_semantics"])
        self.assertEqual(report["ros_source_latency"], "NOT_RUN")

    def test_inventory_keeps_partial_nvidia_observation_and_omits_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root, "etc/os-release", 'ID=ubuntu\nVERSION_ID="22.04"\nPASSWORD=never-print\n')
            write(root, "etc/nv_tegra_release", "# R36 (release), REVISION: 5.2\n")
            write(root, "proc/device-tree/model", "Jetson Orin NX\x00")
            commands = []

            def runner(command, **kwargs):
                commands.append(command)
                if command[0] == "dpkg-query":
                    return subprocess.CompletedProcess(command, 1, "nvidia-l4t-core\t36.5.2\tinstalled\n", "missing optional nvidia-jetpack")
                return subprocess.CompletedProcess(command, 1, "", "secret=never-print")

            report = diagnostics.snapshot(root=root, runner=runner, include_imports=False)
            packages = report["platform"]["nvidia_packages"]
            self.assertEqual(packages["status"], "PASS")
            self.assertEqual(packages["installed"], ["nvidia-l4t-core\t36.5.2\tinstalled"])
            self.assertEqual(report["platform"]["device_tree_model"], "Jetson Orin NX")
            self.assertNotIn("never-print", json.dumps(report))
            self.assertFalse(any("ExecStart" in argument or "Environment" in argument for command in commands for argument in command))
            self.assertEqual(report["external_jetson_off"], "NOT_RUN")

    def test_resources_report_real_counters_and_absent_metrics_as_null(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root, "proc/meminfo", "MemTotal: 1000 kB\nMemAvailable: 400 kB\nSwapTotal: 100 kB\nSwapFree: 70 kB\n")
            write(root, "proc/stat", "cpu  10 0 5 70 5 0 0 0 0 0\n")
            write(root, "proc/vmstat", "oom_kill 3\n")
            write(root, "sys/class/thermal/thermal_zone0/type", "cpu-thermal\n")
            write(root, "sys/class/thermal/thermal_zone0/temp", "42000\n")
            value = diagnostics.resource_snapshot(root=root)
            self.assertEqual(value["memory_bytes"]["MemAvailable"], 409600)
            self.assertEqual(value["oom_kill_count"], 3)
            self.assertEqual(value["temperatures"][0]["celsius"], 42)
            self.assertIsNone(value["gpu_percent"])
            self.assertEqual(diagnostics.cpu_percent({"total": 10, "idle": 8}, {"total": 20, "idle": 12}), 60)
            write(root, "sys/devices/platform/bus@0/17000000.gpu/load", "520\n")
            self.assertEqual(diagnostics.resource_snapshot(root=root)["gpu_percent"], 52)

    def test_summary_distinguishes_measurement_from_acceptance(self):
        row = {"cpu_percent": 25, "gpu_percent": None, "temperatures": [{"celsius": 45}],
               "memory_bytes": {"MemAvailable": 200, "SwapTotal": 50, "SwapFree": 40}, "oom_kill_count": 2}
        summary = diagnostics.summarize([row, {**row, "oom_kill_count": 3}], 20, 1800)
        self.assertFalse(summary["duration_complete"])
        self.assertEqual(summary["oom_kill_increase"], 1)
        self.assertIsNone(summary["gpu_max_percent"])
        for key in ("external_jetson_off", "cold_boot", "acceptance", "throttling"):
            self.assertEqual(summary[key], "NOT_RUN")

    def test_private_report_refuses_overwrite_and_symlink_ancestors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "reports/record.json"
            with diagnostics.private_output(output) as stream:
                stream.write("preserve")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                diagnostics.private_output(output)
            (root / "link").symlink_to(root / "reports", target_is_directory=True)
            with self.assertRaises(ValueError):
                diagnostics.private_output(root / "link/other.json")
            self.assertEqual(output.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
