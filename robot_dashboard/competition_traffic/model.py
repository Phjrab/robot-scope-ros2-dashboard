"""Reuse the pinned VM loader; do not execute unacknowledged pickle weights."""
from __future__ import annotations

from pathlib import Path
import os
from experiments.competition_vm.traffic_signals.detector import LocalUltralytics

from .config import sha256_file


class OwnerModel:
    """The caller must establish trust independently; a hash is not provenance."""

    def __init__(self, path, config, *, acknowledge_trusted_pickle=False):
        path = Path(path).resolve(strict=True)
        model = config.document["model"]
        if path.suffix.lower() not in (".pt", ".onnx") or not path.is_file():
            raise ValueError("LOCAL_MODEL_FILE_REQUIRED")
        if sha256_file(path) != model["sha256"]:
            raise ValueError("MODEL_CHECKSUM_MISMATCH")
        if path.suffix.lower() == ".pt" and not (
            model["trusted_pickle"] and acknowledge_trusted_pickle
        ):
            raise ValueError("TRUSTED_PICKLE_ACK_REQUIRED")
        # Pin optional library behavior before it is imported by the VM loader.
        # This package is offline; it must not install missing modules or send
        # analytics. The explicit call, not package import, establishes this.
        os.environ["YOLO_OFFLINE"] = "true"
        os.environ["YOLO_AUTOINSTALL"] = "false"
        self.adapter = LocalUltralytics(
            path, expected_sha256=model["sha256"],
            trusted_pickle=acknowledge_trusted_pickle,
            package_version=model["package_version"], family=model["family"],
            allowed_classes=[int(k) for k in config.document["class_map"]],
        )
        names = self.adapter.model.names
        if isinstance(names, list):
            names = dict(enumerate(names))
        if not isinstance(names, dict):
            raise ValueError("MODEL_CLASS_NAMES_UNAVAILABLE")
        for key, expected in config.document["class_map"].items():
            if names.get(int(key)) != expected:
                raise ValueError("MODEL_CLASS_NAME_MISMATCH")
        self.names = {str(k): str(v) for k, v in names.items()}
        self.sha256 = self.adapter.sha256
        self.coordinate_space = "native_xyxy"
        self.model_size = None

    def infer(self, bgr):
        return self.adapter.infer(bgr)
