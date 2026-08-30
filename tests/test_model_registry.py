import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import yaml

from robot_dashboard.model_registry import (
    ENGINE_SCHEMA,
    OUTPUT_SCHEMA,
    ModelRegistry,
    ModelRegistryConflict,
    ModelRegistryUnavailable,
    ModelRegistryValidationError,
)


SESSION_ID = "20260830T010203Z_" + "1" * 32
TARGET = {
    "platform": "go2-internal-jetson",
    "jetpack_version": "5.1.2",
    "tensorrt_version": "8.5.2",
    "gpu_identity": "NVIDIA Orin NX",
}


def package_archive(root: Path, model_id: str, task: str = "object", mutate=None) -> Path:
    onnx = f"onnx-{model_id}".encode()
    onnx_sha = hashlib.sha256(onnx).hexdigest()
    classes = ["person", "cone"] if task == "object" else []
    metadata = {
        "model_id": model_id,
        "task": task,
        "source_dataset_sessions": [SESSION_ID],
        "training_code_commit": "a" * 40,
        "class_names": classes,
        "input_shape": [1, 3, 480, 640],
        "preprocessing": {
            "color_space": "RGB",
            "scale": 0.003921568627,
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        },
        "output_schema_version": OUTPUT_SCHEMA,
        "opset": 17,
        "validation_metrics": {"map50": 0.81},
        "created_at": "2026-08-30T01:02:03.000Z",
        "onnx_sha256": onnx_sha,
        "supported_target": dict(TARGET),
    }
    files = {
        "model.onnx": onnx,
        "labels.yaml": yaml.safe_dump(classes).encode(),
        "metadata.json": json.dumps(metadata).encode(),
        "evaluation.json": json.dumps(
            {"split": "by-session", "test_sessions": [SESSION_ID], "metrics": {"map50": 0.81}}
        ).encode(),
        "sha256.txt": f"{onnx_sha}  model.onnx\n".encode(),
    }
    if mutate is not None:
        mutate(files, metadata)
        files["metadata.json"] = json.dumps(metadata).encode()
    path = root / f"{model_id}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return path


def engine_evidence(root: Path, record, **overrides):
    engine = root / f"{record['model_id']}.plan"
    log = root / f"{record['model_id']}.log"
    evidence = root / f"{record['model_id']}.json"
    engine.write_bytes(f"engine-{record['model_id']}".encode())
    log.write_text("TensorRT build completed with fixed bindings\n")
    payload = {
        "schema_version": ENGINE_SCHEMA,
        "model_id": record["model_id"],
        "package_sha256": record["package_sha256"],
        "engine_sha256": hashlib.sha256(engine.read_bytes()).hexdigest(),
        "jetpack_version": TARGET["jetpack_version"],
        "tensorrt_version": TARGET["tensorrt_version"],
        "gpu_identity": TARGET["gpu_identity"],
        "build_log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        "created_at": "2026-08-30T02:03:04.000Z",
        "shadow_smoke_passed": True,
        "resource_check_passed": True,
    }
    payload.update(overrides)
    evidence.write_text(json.dumps(payload))
    return engine, evidence, log


class ModelRegistryTests(unittest.TestCase):
    def test_registry_root_rejects_relative_root_and_symlink_components(self):
        with self.assertRaises(ModelRegistryValidationError):
            ModelRegistry(Path("relative-registry"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            real = root / "real"
            real.mkdir()
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(ModelRegistryValidationError):
                ModelRegistry(link / "registry")

    def test_corrupt_persisted_active_state_fails_closed_on_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "registry"
            registry = ModelRegistry(root)
            payload = registry.list_models()
            (root / "registry.json").write_text(
                json.dumps(
                    {
                        "schema_version": payload["schema_version"],
                        "models": {},
                        "active": {"object": "missing-model"},
                        "previous": {},
                    }
                )
            )
            with self.assertRaises(ModelRegistryUnavailable):
                ModelRegistry(root)

    def test_valid_package_stages_without_activation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            registry = ModelRegistry(root / "registry")
            record = registry.stage_archive(package_archive(root, "object-v1"))
            self.assertEqual(record["state"], "staged")
            self.assertRegex(record["package_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(registry.active_snapshot()["active"], {})
            self.assertEqual(registry.list_models()["activation_surface"], "LOCAL_OPERATOR_ONLY")
            with self.assertRaises(ModelRegistryConflict):
                registry.activate("object-v1", "object-v1")

    def test_invalid_metadata_hash_task_schema_and_archive_layout_fail_closed(self):
        cases = {
            "hash": lambda files, metadata: metadata.update(onnx_sha256="f" * 64),
            "task": lambda files, metadata: metadata.update(task="motion"),
            "schema": lambda files, metadata: metadata.update(output_schema_version="unknown/v9"),
            "nan": lambda files, metadata: metadata.update(validation_metrics={"map50": float("nan")}),
        }
        for name, mutation in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                registry = ModelRegistry(root / "registry")
                archive = package_archive(root, f"bad-{name}", mutate=mutation)
                with self.assertRaises(ModelRegistryValidationError):
                    registry.stage_archive(archive)
                self.assertEqual(registry.list_models()["models"], [])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = package_archive(root, "layout")
            with zipfile.ZipFile(archive, "a") as bundle:
                bundle.writestr("../outside", b"bad")
            registry = ModelRegistry(root / "registry")
            with self.assertRaises(ModelRegistryValidationError):
                registry.stage_archive(archive)
            self.assertFalse((root / "outside").exists())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            corrupt = root / "corrupt.zip"
            corrupt.write_bytes(b"not-a-zip")
            registry = ModelRegistry(root / "registry")
            with self.assertRaisesRegex(ModelRegistryValidationError, "archive is invalid"):
                registry.stage_archive(corrupt)
            self.assertEqual(registry.list_models()["models"], [])

    def test_engine_target_mismatch_and_secret_log_reject_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            registry = ModelRegistry(root / "registry")
            record = registry.stage_archive(package_archive(root, "object-v2"))
            engine, evidence, log = engine_evidence(
                root,
                record,
                tensorrt_version="99.0",
            )
            with self.assertRaises(ModelRegistryValidationError):
                registry.validate_engine("object-v2", engine, evidence, log)
            self.assertEqual(registry.list_models()["models"][0]["state"], "rejected")

            engine, evidence, log = engine_evidence(root, record)
            log.write_text("password=hunter2\n")
            payload = json.loads(evidence.read_text())
            payload["build_log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
            evidence.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ModelRegistryValidationError, "redacted"):
                registry.validate_engine("object-v2", engine, evidence, log)

    def test_activation_is_atomic_and_rollback_swaps_previous(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            registry = ModelRegistry(root / "registry")
            first = registry.stage_archive(package_archive(root, "object-v1"))
            engine, evidence, log = engine_evidence(root, first)
            registry.validate_engine("object-v1", engine, evidence, log)
            with self.assertRaises(ModelRegistryConflict):
                registry.activate("object-v1", "wrong")
            registry.activate("object-v1", "object-v1")
            self.assertEqual(registry.active_snapshot()["active"]["object"]["model_id"], "object-v1")

            second = registry.stage_archive(package_archive(root, "object-v2"))
            engine, evidence, log = engine_evidence(root, second)
            registry.validate_engine("object-v2", engine, evidence, log)
            with mock.patch.object(
                registry,
                "_atomic_registry",
                side_effect=ModelRegistryUnavailable("synthetic publication failure"),
            ):
                with self.assertRaises(ModelRegistryUnavailable):
                    registry.activate("object-v2", "object-v2")
            self.assertEqual(registry.active_snapshot()["active"]["object"]["model_id"], "object-v1")

            registry.activate("object-v2", "object-v2")
            snapshot = registry.active_snapshot()
            self.assertEqual(snapshot["active"]["object"]["model_id"], "object-v2")
            self.assertEqual(snapshot["previous"]["object"], "object-v1")
            reloaded = ModelRegistry(root / "registry")
            self.assertEqual(
                reloaded.active_snapshot()["active"]["object"]["model_id"],
                "object-v2",
            )
            self.assertEqual(reloaded.active_snapshot()["previous"]["object"], "object-v1")
            previous_package = next(registry.packages.glob("object-v1-*"))
            metadata_path = previous_package / "metadata.json"
            original_metadata = metadata_path.read_bytes()
            metadata_path.write_text("{}")
            with self.assertRaisesRegex(ModelRegistryValidationError, "package hash changed"):
                registry.rollback("object", "object-v2")
            self.assertEqual(
                registry.active_snapshot()["active"]["object"]["model_id"],
                "object-v2",
            )
            metadata_path.write_bytes(original_metadata)
            rolled_back = registry.rollback("object", "object-v2")
            self.assertEqual(rolled_back["active"]["object"]["model_id"], "object-v1")
            self.assertEqual(rolled_back["previous"]["object"], "object-v2")

    def test_tampered_package_cannot_replace_active(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            registry = ModelRegistry(root / "registry")
            record = registry.stage_archive(package_archive(root, "lane-v1", task="lane"))
            engine, evidence, log = engine_evidence(root, record)
            registry.validate_engine("lane-v1", engine, evidence, log)
            package = next(registry.packages.glob("lane-v1-*"))
            (package / "metadata.json").write_text("{}")
            with self.assertRaises(ModelRegistryValidationError):
                registry.activate("lane-v1", "lane-v1")
            self.assertEqual(registry.active_snapshot()["active"], {})


if __name__ == "__main__":
    unittest.main()
