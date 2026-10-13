import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.hesai_calibration_manifest import ACQUISITION_METHOD, DRIVER_REVISION, SDK_REVISION


ROOT = Path(__file__).resolve().parents[1]
BASE_URI = ('<CycloneDDS><Domain><General><Interfaces>'
            '<NetworkInterface name="enP8p1s0" priority="default" multicast="default" />'
            '</Interfaces></General><Discovery><MaxAutoParticipantIndex>80</MaxAutoParticipantIndex>'
            '</Discovery><Internal><SocketReceiveBufferSize max="8 MiB" /></Internal>'
            '</Domain></CycloneDDS>')


class HesaiDriverRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        scripts = self.project / "scripts"
        scripts.mkdir(parents=True)
        config = self.project / "config"
        config.mkdir()
        for name in ("hesai_xt16.yaml", "hesai_xt16_onboard.yaml"):
            shutil.copy2(ROOT / "config" / name, config / name)
        for name in ("run_hesai_driver_humble.sh", "apply_go2_onboard_contract.sh"):
            shutil.copy2(ROOT / "scripts" / name, scripts / name)
        self.runner = scripts / "run_hesai_driver_humble.sh"
        self.trace = self.root / "events"
        self.correction = self.root / "xt16-correction.csv"
        payload = ("Channel,Elevation,Azimuth\n" + "".join(f"{i},{16-i},0\n" for i in range(1, 17))).encode()
        self.correction.write_bytes(payload)
        self.correction.chmod(0o640)
        manifest = self.root / "xt16-calibration.manifest"
        manifest.write_text(json.dumps({
            "schema_version": 1, "sensor": {"model": "XT16", "parser_identity": "PandarXT", "serial": "fixture"},
            "driver_revision": DRIVER_REVISION, "sdk_revision": SDK_REVISION,
            "acquisition": {"method": ACQUISITION_METHOD, "timestamp_utc": "2026-10-13T00:00:00Z"},
            "correction": {"path": str(self.correction), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
        }))
        manifest.chmod(0o640)
        # Exercise the real validator with a private test-only path contract;
        # the production runner still invokes the fixed validate vocabulary.
        (scripts / "hesai_calibration_manifest.py").write_text(
            "import os,sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from scripts.hesai_calibration_manifest import CalibrationContract,validate_bundle\n"
            "assert sys.argv[1:] == ['validate']\n"
            f"validate_bundle(CalibrationContract(Path({str(manifest)!r}), Path({str(self.correction)!r}), os.getuid(), os.getgid()))\n"
            f"with Path({str(self.trace)!r}).open('a') as stream: stream.write('calibration\\n')\n"
        )
        (scripts / "setup_go2_ros2_humble.sh").write_text(
            f"export CYCLONEDDS_URI='{BASE_URI}'\n"
            "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp\n"
            'printf "ros_setup\\n" >> "$FIXTURE_TRACE"\n'
        )
        self.workspace = self.root / "workspaces"
        setup = self.workspace / "ws/hesai_ws/install/setup.bash"
        setup.parent.mkdir(parents=True)
        setup.write_text('printf "hesai_setup\\n" >> "$FIXTURE_TRACE"\n')
        binaries = self.root / "bin"
        binaries.mkdir()
        ros2 = binaries / "ros2"
        ros2.write_text(f"#!{sys.executable}\n" +
            "import os,json,sys\nfrom pathlib import Path\n"
            "print(json.dumps({'argv':sys.argv[1:],'dds':os.environ['CYCLONEDDS_URI'],"
            "'interface':os.environ['ROBOT_SCOPE_GO2_INTERFACE'],'rmw':os.environ['RMW_IMPLEMENTATION'],"
            "'trace':Path(os.environ['FIXTURE_TRACE']).read_text().splitlines()}))\n")
        ros2.chmod(0o755)
        self.environment = {"PATH": f"{binaries}:{Path(sys.executable).parent}:/usr/bin:/bin",
                            "HOME": str(self.root), "PYTHONDONTWRITEBYTECODE": "1",
                            "ROBOT_SCOPE_WORKSPACE_ROOT": str(self.workspace),
                            "ROBOT_SCOPE_GO2_INTERFACE": "enP8p1s0", "FIXTURE_TRACE": str(self.trace)}

    def run_runner(self, profile):
        return subprocess.run(["bash", str(self.runner)],
                              env={**self.environment, "ROBOT_SCOPE_MAPPING_PROFILE": profile},
                              text=True, capture_output=True, timeout=5, check=False)

    def test_onboard_exec_uses_spdp_and_preserves_nic_discovery_and_buffer(self):
        result = self.run_runner("go2-onboard")
        self.assertEqual(result.returncode, 0, result.stderr)
        executed = json.loads(result.stdout)
        tree = ET.fromstring(executed["dds"])
        general = tree.find("Domain/General")
        multicast = general.find("AllowMulticast")
        self.assertEqual(multicast.text, "spdp")
        general.remove(multicast)
        self.assertEqual(ET.tostring(tree), ET.tostring(ET.fromstring(BASE_URI)))
        self.assertEqual(executed["interface"], "enP8p1s0")
        self.assertEqual(executed["rmw"], "rmw_cyclonedds_cpp")
        self.assertEqual(executed["trace"], ["calibration", "ros_setup", "hesai_setup"])
        self.assertEqual(executed["argv"], ["run", "hesai_ros_driver", "hesai_ros_driver_node",
                                           "--ros-args", "-p", f"config_path:={self.project / 'config/hesai_xt16_onboard.yaml'}"])

    def test_wired_exec_keeps_the_setup_dds_xml_exactly(self):
        result = self.run_runner("go2-xt16-wired")
        self.assertEqual(result.returncode, 0, result.stderr)
        executed = json.loads(result.stdout)
        self.assertEqual(executed["dds"], BASE_URI)
        self.assertEqual(executed["trace"], ["ros_setup", "hesai_setup"])
        self.assertEqual(executed["argv"][-1], f"config_path:={self.project / 'config/hesai_xt16.yaml'}")

    def test_invalid_onboard_calibration_blocks_both_ros_setups_and_exec(self):
        self.correction.write_bytes(self.correction.read_bytes().replace(b",0\n", b",1\n", 1))
        result = self.run_runner("go2-onboard")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hash mismatch", result.stderr)
        self.assertFalse(self.trace.exists())
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
