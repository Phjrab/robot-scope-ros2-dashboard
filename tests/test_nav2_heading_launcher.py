"""Execute the launcher with isolated shell probes; never start ROS processes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HeadingLauncherTests(unittest.TestCase):
    def launch(self, *, selected=True, validation_status=0, load_status=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            launcher = scripts / "run_go2_navigation_humble.sh"
            launcher.write_bytes((ROOT / "scripts" / launcher.name).read_bytes())
            (scripts / "setup_go2_ros2_humble.sh").write_text(":\n")
            overlay = root / "overlay"
            setup = overlay / "share/nav2_rotation_shim_controller/local_setup.bash"
            setup.parent.mkdir(parents=True)
            setup.write_text('printf "source\\n" >> "$PROBE_LOG"\nexport PROBE_SOURCED=1\n')
            bootstrap = root / "bootstrap.bash"
            bootstrap.write_text('''
# Only regular temporary snapshot paths are used; avoid platform realpath flags.
realpath() { printf '%s\\n' "$3"; }
function /usr/bin/python3() {
  if [[ "$1" == */check_nav2_heading_overlay.py ]]; then
    if [[ "${4:-}" == --check-load ]]; then
      [[ "${PROBE_SOURCED:-}" == 1 ]] || return 74
      printf 'load\\n' >> "$PROBE_LOG"
      return "$PROBE_LOAD_STATUS"
    fi
    printf 'validate\\n' >> "$PROBE_LOG"
    return "$PROBE_VALIDATION_STATUS"
  fi
  # Make both runtime import probes fail before any ROS executable starts.
  printf 'runtime-probe\\n' >> "$PROBE_LOG"
  return 1
}
''')
            snapshot = root / "snapshot.yaml"
            snapshot.write_text("{}\n")
            log = root / "probe.log"
            env = dict(os.environ, BASH_ENV=str(bootstrap), PROBE_LOG=str(log),
                       PROBE_LOAD_STATUS=str(load_status),
                       PROBE_VALIDATION_STATUS=str(validation_status),
                       ROBOT_SCOPE_MAPPING_PROFILE="go2-onboard",
                       ROBOT_SCOPE_NAV2_HEADING_OVERLAY=str(overlay) if selected else "")
            result = subprocess.run(
                ["bash", str(launcher), "--map-yaml", str(snapshot),
                 "--params-file", str(snapshot)], env=env, capture_output=True,
                text=True, timeout=5,
            )
            return result, log.read_text().splitlines() if log.exists() else []

    def test_selected_overlay_checks_actual_loader_after_sourcing(self):
        result, calls = self.launch()
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(calls, ["validate", "source", "load", "runtime-probe", "runtime-probe"])

    def test_loader_mismatch_aborts_before_runtime_or_ros_start(self):
        result, calls = self.launch(load_status=73)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertEqual(calls, ["validate", "source", "load"])

    def test_invalid_receipt_never_sources_overlay(self):
        result, calls = self.launch(validation_status=72)
        self.assertEqual(result.returncode, 72, result.stderr)
        self.assertEqual(calls, ["validate"])

    def test_unselected_overlay_keeps_installed_controller_path(self):
        result, calls = self.launch(selected=False)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(calls, ["runtime-probe", "runtime-probe"])
