"""Reuse the pinned VM loader; do not execute unacknowledged pickle weights."""
from __future__ import annotations

from pathlib import Path
import os
from experiments.competition_vm.traffic_signals.detector import Detection, LocalUltralytics

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
        self.last_diagnostics = {}
        self.confidence_floor = min(.25, config.document["min_confidence"])

    def infer(self, bgr):
        # Reuse the VM-loaded model and its identical CPU prediction path. Capture
        # post-NMS diagnostics before its allowlist filter would discard objects.
        r = self.adapter.model.predict(source=bgr, device="cpu", verbose=False,
                                       conf=self.confidence_floor)[0]
        boxes = [Detection(tuple(box), float(conf), int(cls), f"detection-{idx}")
                 for idx, (box, conf, cls) in enumerate(zip(
                     r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()))]
        selected = [d for d in boxes if d.class_id in self.adapter.allowed]
        self.last_diagnostics = {
            "post_nms_boxes": len(boxes), "allowlist_boxes": len(selected),
            "non_allowlist_boxes": len(boxes) - len(selected),
            "model_confidence_floor": self.confidence_floor,
            "below_model_floor": "NOT_OBSERVABLE_AFTER_NMS",
            "input_encoding": "bgr8", "result_original_shape_hw": list(r.orig_shape),
            "coordinate_space": "native_xyxy", "inverse_letterbox_applied": False,
        }
        if list(r.orig_shape) != list(bgr.shape[:2]):
            raise ValueError("MODEL_ORIGINAL_SHAPE_MISMATCH")
        return selected
