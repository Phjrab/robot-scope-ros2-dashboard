"""Reuse the pinned VM loader; do not execute unacknowledged pickle weights."""
from __future__ import annotations

from pathlib import Path
import os
import math
import time
from experiments.competition_vm.traffic_signals.detector import Detection, LocalUltralytics

from .config import sha256_file
from .inference import settings, regions, interior_edge, native_nms


class OwnerModel:
    """The caller must establish trust independently; a hash is not provenance."""

    def __init__(self, path, config, *, acknowledge_trusted_pickle=False, inference_profile="full640"):
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
        if config.document.get("color_policy"):
            from .consensus import MODEL_CLASSES
            if self.names != MODEL_CLASSES or self.adapter.model.task != "detect":
                raise ValueError("COLOR_POLICY_MODEL_METADATA_MISMATCH")
        self.sha256 = self.adapter.sha256
        self.coordinate_space = "native_xyxy"
        self.model_size = None
        self.last_diagnostics = {}
        self.confidence_floor = min(.25, config.document["min_confidence"])
        self.inference_settings, self.inference_settings_sha256 = settings(
            inference_profile, confidence_floor=self.confidence_floor, model_sha256=self.sha256,
            color_policy=config.document.get("color_policy"))

    def infer(self, bgr):
        start = time.monotonic()
        h, w = bgr.shape[:2]
        selected, post_nms, non_allowlist, edge_rejected = [], 0, 0, 0
        views = regions((w, h), self.inference_settings)
        for view_index, region in enumerate(views):
            x1, y1, x2, y2 = region
            source = bgr if view_index == 0 else bgr[y1:y2, x1:x2]
            r = self.adapter.model.predict(
                source=source, device="cpu", verbose=False, conf=self.confidence_floor,
                imgsz=self.inference_settings["imgsz"], rect=True, iou=.7, max_det=300)[0]
            if list(r.orig_shape) != list(source.shape[:2]):
                raise ValueError("MODEL_ORIGINAL_SHAPE_MISMATCH")
            for idx, (box, conf, cls) in enumerate(zip(
                    r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())):
                post_nms += 1
                if (not all(math.isfinite(x) for x in box + [conf, cls])
                        or cls != int(cls) or not 0 <= conf <= 1):
                    raise ValueError("MODEL_NONFINITE_DETECTION")
                if int(cls) not in self.adapter.allowed:
                    non_allowlist += 1
                    continue
                if view_index and interior_edge(box, region, (w, h)):
                    edge_rejected += 1
                    continue
                native = (box[0]+x1, box[1]+y1, box[2]+x1, box[3]+y1)
                selected.append(Detection(native, float(conf), int(cls), f"view-{view_index}-detection-{idx}"))
        before = len(selected)
        if len(views) > 1:
            selected = native_nms(selected)
        self.last_diagnostics = {
            "post_nms_boxes": post_nms, "allowlist_boxes": len(selected),
            "non_allowlist_boxes": non_allowlist, "tile_edge_rejected": edge_rejected,
            "native_fusion_removed": before-len(selected), "views": len(views),
            "model_confidence_floor": self.confidence_floor,
            "below_model_floor": "NOT_OBSERVABLE_AFTER_NMS",
            "input_encoding": "bgr8", "result_original_shape_hw": [h, w],
            "coordinate_space": "native_xyxy", "inverse_letterbox_applied": False,
            "inference_profile": self.inference_settings,
            "inference_settings_sha256": self.inference_settings_sha256,
            "inference_wall_s": time.monotonic()-start,
        }
        return selected
