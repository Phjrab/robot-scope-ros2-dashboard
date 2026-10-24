from dataclasses import replace

import cv2
import numpy as np

from experiments.competition_vm.traffic_signals.detector import Detection
from robot_dashboard.competition_traffic.config import TrafficConfig
from robot_dashboard.competition_traffic.frames import Frame


def config(size=(64, 64), roi=None):
    return TrafficConfig.parse({
        "schema_version": "traffic-input-config.v0.1",
        "model": {"sha256": "a" * 64, "provenance": "synthetic test stub; not real weights",
                  "family": "ultralytics", "package_version": "8.0.0", "trusted_pickle": False},
        "class_map": {"0": "traffic_light"}, "min_confidence": .25,
        "association": {"signal_id": "signal_01", "crossing_id": "crossing_01",
                        "binding_id": "camera-heading-revision-1", "native_image_size": list(size), "verified": True,
                        "expected_roi_native": list(roi or (0, 0, *size))}})


def lamp(color=(0, 230, 0), size=(64, 64)):
    image = np.full((size[1], size[0], 3), 15, np.uint8)
    cv2.circle(image, (size[0] // 2, size[1] // 2), 12, color, -1)
    return image


def frame(n=0, image=None, **kwargs):
    return replace(Frame(lamp() if image is None else image, "camera-1", "epoch-1", n,
                         str(n * 100000000), "fixture", 0., n / 10., True,
                         "SYNTHETIC_TEST", f"frame-{n}", "camera-heading-revision-1"), **kwargs)


class Detector:
    sha256 = "a" * 64
    names = {"0": "traffic_light"}
    coordinate_space = "native_xyxy"
    model_size = None

    def __init__(self, detections=None):
        self.detections = detections
        self.calls = 0

    def infer(self, bgr):
        self.calls += 1
        if self.detections is not None:
            return self.detections
        h, w = bgr.shape[:2]
        return [Detection((0, 0, w, h), .9, 0, "transient-index")]
