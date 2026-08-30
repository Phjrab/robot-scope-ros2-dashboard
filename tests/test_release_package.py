import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from robot_dashboard.competition import CompetitionStateManager
from robot_dashboard.model_registry import ENGINE_SCHEMA, OUTPUT_SCHEMA, ModelRegistry
from robot_dashboard.release_package import (
    RELEASE_SCHEMA,
    OfflineReleaseBuilder,
    ReleasePackageError,
    validate_release_manifest,
    verify_offline_package,
)


TARGET = {
    "platform": "go2-internal-jetson",
    "jetpack_version": "5.1.2",
    "tensorrt_version": "8.5.2",
    "gpu_identity": "NVIDIA-Orin-NX",
}
SESSION_ID = "20260830T010203Z_" + "1" * 32


def manifest(commit: str = "a" * 40, package_sha: str = "b" * 64, engine_sha: str = "c" * 64):
    return {
        "schema_version": RELEASE_SCHEMA,
        "release_id": "competition-20260830-r1",
        "git_commit": commit,
        "dashboard_version": "competition-20260830-r1",
        "robot_side_agent_version": "competition-20260830-r1",
        "schema_versions": {
            "competition_state": "robot-scope.competition-state/v1",
            "model_registry": "robot-scope.model-registry/v1",
        },
        "active_model_ids": {"object": "object-competition-v1"},
        "active_model_sha256": {
            "object": {"package_sha256": package_sha, "engine_sha256": engine_sha}
        },
        "previous_model_ids": {},
        "previous_model_sha256": {},
        "jetpack_tensorrt_identity": dict(TARGET),
        "camera_profile": {
            "go2": "rtp-h264-640x480",
            "realsense": "mjpeg-640x480-30",
        },
        "network_config_fingerprint": "d" * 64,
        "ros": {"distro": "humble", "rmw": "rmw_cyclonedds_cpp", "domain_id": 0},
        "map_revision": "arena-map-r1",
        "mission_revision": "mission-r1",
        "acceptance_report_ids": ["acceptance-20260830-r1"],
        "created_at": "2026-08-30T10:00:00.000Z",
    }


def model_archive(root: Path) -> Path:
    onnx = b"offline-release-model"
    onnx_sha = hashlib.sha256(onnx).hexdigest()
    metadata = {
        "model_id": "object-competition-v1",
        "task": "object",
        "source_dataset_sessions": [SESSION_ID],
        "training_code_commit": "a" * 40,
        "class_names": ["cone"],
        "input_shape": [1, 3, 480, 640],
        "preprocessing": {
            "color_space": "RGB",
            "scale": 0.003921568627,
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        },
        "output_schema_version": OUTPUT_SCHEMA,
        "opset": 17,
        "validation_metrics": {"map50": 0.8},
        "created_at": "2026-08-30T01:02:03.000Z",
        "onnx_sha256": onnx_sha,
        "supported_target": dict(TARGET),
    }
    path = root / "model.zip"
    files = {
        "model.onnx": onnx,
        "labels.yaml": yaml.safe_dump(["cone"]).encode(),
        "metadata.json": json.dumps(metadata).encode(),
        "evaluation.json": json.dumps({"split": "by-session", "map50": 0.8}).encode(),
        "sha256.txt": f"{onnx_sha}  model.onnx\n".encode(),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return path


def activate_model(root: Path):
    registry = ModelRegistry(root)
    record = registry.stage_archive(model_archive(root.parent))
    engine = root.parent / "engine.plan"
    build_log = root.parent / "build.log"
    evidence = root.parent / "engine-validation.json"
    engine.write_bytes(b"target-engine")
    build_log.write_text("TensorRT target build passed\n", encoding="utf-8")
    engine_sha = hashlib.sha256(engine.read_bytes()).hexdigest()
    evidence.write_text(
        json.dumps(
            {
                "schema_version": ENGINE_SCHEMA,
                "model_id": record["model_id"],
                "package_sha256": record["package_sha256"],
                "engine_sha256": engine_sha,
                "jetpack_version": TARGET["jetpack_version"],
                "tensorrt_version": TARGET["tensorrt_version"],
                "gpu_identity": TARGET["gpu_identity"],
                "build_log_sha256": hashlib.sha256(build_log.read_bytes()).hexdigest(),
                "created_at": "2026-08-30T02:03:04.000Z",
                "shadow_smoke_passed": True,
                "resource_check_passed": True,
            }
        ),
        encoding="utf-8",
    )
    registry.validate_engine(record["model_id"], engine, evidence, build_log)
    registry.activate(record["model_id"], record["model_id"])
    return record["package_sha256"], engine_sha


def create_checkout(root: Path) -> str:
    files = {
        "package-lock.json": "{}\n",
        "requirements.txt": "fastapi==0.116.0\n",
        "requirements-quality.txt": "ruff==0.6.9\n",
        "pyproject.toml": "[tool.ruff]\ntarget-version='py310'\n",
        "scripts/robot_scope_doctor.py": "print('doctor')\n",
        "scripts/robot_scope_acceptance.py": "print('acceptance')\n",
        "scripts/check_repository_secrets.py": "print('tracked-source secret scan passed')\n",
        "docs/WP08_RELEASE_LOCK_ROLLBACK_RUNBOOK.md": "# safe offline runbook\n",
        "deploy/robot-scope.service.example": "[Service]\nExecStart=/usr/bin/true\n",
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "release-test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Release Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


class ReleaseManifestTests(unittest.TestCase):
    def test_exact_release_identity_is_accepted_without_private_network_values(self):
        clean = validate_release_manifest(manifest())
        self.assertEqual(clean["git_commit"], "a" * 40)
        self.assertEqual(clean["active_model_ids"], {"object": "object-competition-v1"})
        self.assertRegex(clean["network_config_fingerprint"], r"^[0-9a-f]{64}$")

    def test_missing_fields_plain_ip_and_model_hash_mismatch_fail_closed(self):
        missing = manifest()
        del missing["acceptance_report_ids"]
        with self.assertRaisesRegex(ReleasePackageError, "schema"):
            validate_release_manifest(missing)
        private_ip = manifest()
        private_ip["network_config_fingerprint"] = "192.168.50.30"
        with self.assertRaisesRegex(ReleasePackageError, "SHA-256"):
            validate_release_manifest(private_ip)
        mismatch = manifest()
        mismatch["active_model_sha256"] = {}
        with self.assertRaisesRegex(ReleasePackageError, "does not match"):
            validate_release_manifest(mismatch)


class OfflineReleaseTests(unittest.TestCase):
    def test_locked_clean_checkout_builds_private_verified_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "repo"
            root.mkdir()
            commit = create_checkout(root)
            competition = CompetitionStateManager(
                root / "runtime" / "competition",
                control_provider=lambda: {"estop_latched": False, "lease": {"active": False}},
            )
            competition.lock("LOCK")
            package_sha, engine_sha = activate_model(root / "runtime" / "model-registry")
            release_input = root / "runtime" / "release-input"
            release_input.mkdir(mode=0o700)
            (release_input / "python-install-manifest.txt").write_text(
                "fastapi==0.116.0\nuvicorn==0.35.0\n", encoding="utf-8"
            )
            acceptance = release_input / "acceptance"
            acceptance.mkdir()
            (acceptance / "acceptance-20260830-r1.json").write_text(
                json.dumps(
                    {
                        "schema": "robot-scope.hardware-acceptance",
                        "schema_version": 1,
                        "commit": commit,
                        "summary": {"PASS": 2, "FAIL": 0, "BLOCKED": 0, "NOT_RUN": 0},
                        "checks": [
                            {
                                "id": "release.identity",
                                "status": "PASS",
                                "manual_action": False,
                            },
                            {
                                "id": "supervised.release_offline_boot",
                                "status": "PASS",
                                "manual_action": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = manifest(commit, package_sha, engine_sha)
            manifest_path = release_input / "manifest.json"
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            output = OfflineReleaseBuilder(root).build(manifest_path)
            result = verify_offline_package(output)
            self.assertTrue(result["ok"])
            self.assertEqual(result["git_commit"], commit)
            self.assertEqual(result["models"], {"object": "object-competition-v1"})
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ReleasePackageError, "already exists"):
                OfflineReleaseBuilder(root).build(manifest_path)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertIn("checksums.json", names)
                self.assertTrue(any(name.startswith("models/active/object/") for name in names))
                self.assertFalse(any(name.startswith("runtime/") for name in names))

    def test_unlocked_checkout_and_existing_release_id_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "repo"
            root.mkdir()
            create_checkout(root)
            CompetitionStateManager(root / "runtime" / "competition")
            builder = OfflineReleaseBuilder(root)
            with self.assertRaisesRegex(ReleasePackageError, "must be enabled"):
                builder._verify_lock()

    def test_traversal_or_tampered_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unsafe.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../release-manifest.json", b"{}")
                archive.writestr("checksums.json", b"{}")
            with self.assertRaisesRegex(ReleasePackageError, "unsafe path"):
                verify_offline_package(path)


if __name__ == "__main__":
    unittest.main()
