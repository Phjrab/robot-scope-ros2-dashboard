import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.hesai_calibration_manifest import (
    ACQUISITION_METHOD,
    DRIVER_REVISION,
    SDK_REVISION,
    CalibrationContract,
    CalibrationError,
    stage_manifest,
    validate_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


class HesaiCalibrationManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.correction = self.directory / "xt16-correction.dat"
        self.manifest = self.directory / "xt16-calibration.manifest"
        self.payload = bytes(range(64))
        self.correction.write_bytes(self.payload)
        self.correction.chmod(0o640)
        self.contract = CalibrationContract(
            manifest_path=self.manifest,
            correction_path=self.correction,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
        self.document = {
            "schema_version": 1,
            "sensor": {
                "model": "XT16",
                "parser_identity": "JT16",
                "serial": "private-test-serial",
            },
            "driver_revision": DRIVER_REVISION,
            "sdk_revision": SDK_REVISION,
            "acquisition": {
                "method": ACQUISITION_METHOD,
                "timestamp_utc": "2026-08-31T07:00:00Z",
            },
            "correction": {
                "path": str(self.correction),
                "sha256": hashlib.sha256(self.payload).hexdigest(),
                "bytes": 64,
            },
        }
        self._write_manifest()

    def _write_manifest(self):
        self.manifest.write_text(json.dumps(self.document), encoding="utf-8")
        self.manifest.chmod(0o640)

    def test_valid_fixed_bundle_passes_without_exposing_identity(self):
        validate_bundle(self.contract)

    def test_hash_mismatch_fails_closed(self):
        self.correction.write_bytes(b"x" * 64)
        self.correction.chmod(0o640)
        with self.assertRaisesRegex(CalibrationError, "hash mismatch"):
            validate_bundle(self.contract)

    def test_symlinked_correction_is_rejected(self):
        target = self.directory / "actual.dat"
        target.write_bytes(self.payload)
        target.chmod(0o640)
        self.correction.unlink()
        self.correction.symlink_to(target)
        with self.assertRaisesRegex(CalibrationError, "regular files"):
            validate_bundle(self.contract)

    def test_broad_manifest_mode_is_rejected(self):
        self.manifest.chmod(0o642)
        with self.assertRaisesRegex(CalibrationError, "accessible by others"):
            validate_bundle(self.contract)

    def test_revision_and_unknown_fields_are_rejected(self):
        self.document["sdk_revision"] = "0" * 40
        self._write_manifest()
        with self.assertRaisesRegex(CalibrationError, "SDK revision mismatch"):
            validate_bundle(self.contract)
        self.document["sdk_revision"] = SDK_REVISION
        self.document["unexpected"] = True
        self._write_manifest()
        with self.assertRaisesRegex(CalibrationError, "fixed schema"):
            validate_bundle(self.contract)

    def test_stage_creates_private_manifest_without_firetime(self):
        self.manifest.unlink()
        self.correction.chmod(0o600)
        serial = self.directory / "xt16-serial.txt"
        serial.write_text("private-test-serial\n", encoding="utf-8")
        serial.chmod(0o600)

        staged = stage_manifest(self.directory, "2026-08-31T07:00:00Z")

        self.assertEqual(staged, self.manifest)
        self.assertEqual(staged.stat().st_mode & 0o777, 0o600)
        document = json.loads(staged.read_text(encoding="utf-8"))
        self.assertNotIn("firetime", document)
        self.assertEqual(document["correction"]["bytes"], 64)
        self.assertEqual(document["correction"]["path"], "/etc/robot-scope/hesai/xt16-correction.dat")

    def test_stage_refuses_to_overwrite_manifest(self):
        self.correction.chmod(0o600)
        serial = self.directory / "xt16-serial.txt"
        serial.write_text("private-test-serial\n", encoding="utf-8")
        serial.chmod(0o600)
        with self.assertRaisesRegex(CalibrationError, "refusing to overwrite"):
            stage_manifest(self.directory, "2026-08-31T07:00:00Z")

    def test_acquisition_helper_is_fixed_read_only_and_non_overwriting(self):
        source = (
            ROOT / "tools" / "hesai_xt16_calibration" / "acquire_xt16_correction.cc"
        ).read_text(encoding="utf-8")
        self.assertIn('kSensorIp[] = "192.168.123.20"', source)
        self.assertIn("kPtcPort = 9347", source)
        self.assertIn("client.JT16GetCorrectionInfo(correction)", source)
        self.assertIn("correction.size() != kCorrectionBytes", source)
        self.assertIn("O_EXCL", source)
        self.assertIn("O_NOFOLLOW", source)
        for forbidden in (
            "SetNet(",
            "SetDesIpandPort(",
            "SetStandbyMode(",
            "SetSpinSpeed(",
            "GetFiretimesInfo(",
            "QueryCommand(",
        ):
            self.assertNotIn(forbidden, source)

    def test_acquisition_build_disables_ptcs_and_enforces_warnings(self):
        cmake = (
            ROOT / "tools" / "hesai_xt16_calibration" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("WITH_PTCS_USE OFF", cmake)
        self.assertIn("-Werror", cmake)
        self.assertIn("HESAI_SDK_ROOT", cmake)
        self.assertIn(SDK_REVISION, cmake)
        self.assertIn("status --porcelain", cmake)

    def test_runbook_keeps_ptc_execution_behind_exact_approval(self):
        runbook = (ROOT / "docs" / "HESAI_XT16_CALIBRATION_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        for contract in (
            "APPROVE_WIRELESS_XT16_DEPLOY",
            "does not support firetime",
            "physical label",
            "second operator",
            "HW-2 still",
        ):
            self.assertIn(contract, runbook)


if __name__ == "__main__":
    unittest.main()
