"""Detector -> native ROI -> existing quality/color -> existing temporal filter."""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

import numpy as np

from experiments.competition_vm.traffic_signals.core import (
    ColorProfile, TemporalFilter, classify_roi, inverse_letterbox,
)
from experiments.competition_vm.traffic_signals.detector import Association, Detection, iou

from .config import finite


@dataclass
class Observation:
    """Sidecar plus canonical signal fragment, NOT complete mission Evidence."""
    signal: dict
    context: dict
    mask: object = None

    def json_record(self):
        return {"signal": self.signal, "context": self.context}


class TrafficPipeline:
    def __init__(self, config, detector=None, *, clock=time.monotonic, measure_wall_latency=False):
        self.config = config
        self.detector = detector
        self.clock = clock
        self.measure_wall_latency = measure_wall_latency
        self.last_valid_observation_s = None
        self.receiver_highwater = None
        self.detection_diagnostics = {}
        self.temporal = TemporalFilter()  # VM defaults: stability .4s, TTL .25s
        self.association = Association()
        self.epoch = None
        self.retired = set()
        self.last_seq = -1
        self.last_stamp = -1
        self.last_receipt = None
        self.last_handle = None
        self.last_source_age = None
        self.latest = None
        self.latest_receipt = None
        self.latest_age = None

    def _clock_gate(self, f, now):
        if not finite(now, 0, 1e16) or now < f.received_s:
            return ["RECEIVER_CLOCK_INVALID"]
        if self.receiver_highwater is not None and f.received_s <= self.receiver_highwater:
            return ["REPEATED_OR_REVERSED_FRAME"]
        key = (f.source_id, f.producer_epoch)
        if key in self.retired:
            return ["RETIRED_EPOCH"]
        if key != self.epoch:
            if self.epoch is not None:
                self.retired.add(self.epoch)
            self.epoch = key
            self.last_seq = self.last_stamp = -1
            self.last_receipt = self.last_handle = None
            self.temporal.reset()
            self.association = Association()
        stamp = int(f.source_stamp_ns)
        if (f.sequence <= self.last_seq or stamp <= self.last_stamp
                or (self.last_receipt is not None and f.received_s <= self.last_receipt)):
            return ["REPEATED_OR_REVERSED_FRAME"]
        flags = []
        if not f.identity_verified:
            flags.append("SOURCE_IDENTITY_UNVERIFIED")
        if self.last_seq >= 0 and f.sequence != self.last_seq + 1:
            flags.append("FRAME_SEQUENCE_GAP")
        if self.last_receipt is not None and f.received_s - self.last_receipt > .25:
            flags.append("FRAME_RECEIPT_GAP")
        # Keep replay protection even when the temporal filter rejects age.
        self.last_seq, self.last_stamp = f.sequence, stamp
        self.last_receipt, self.last_handle = f.received_s, f.image_handle
        self.receiver_highwater = f.received_s
        self.last_source_age = f.source_age_s
        if not f.clock_verified or f.source_age_s is None:
            flags.append("SOURCE_CLOCK_UNVERIFIED")
        elif f.source_age_s + now - f.received_s > .25:
            flags.append("SOURCE_STALE")
        if now - f.received_s > .25:
            flags.append("RECEIPT_EXPIRED")
        return flags

    def _detect(self, bgr, size):
        self.detection_diagnostics = {"status": "NOT_RUN"}
        if self.detector is None:
            return [], "MODEL_UNAVAILABLE"
        if getattr(self.detector, "sha256", None) != self.config.document["model"]["sha256"]:
            return [], "MODEL_IDENTITY_MISMATCH"
        names = getattr(self.detector, "names", {})
        if any(names.get(k) != v for k, v in self.config.document["class_map"].items()):
            return [], "MODEL_CLASS_NAME_MISMATCH"
        space = getattr(self.detector, "coordinate_space", None)
        if space not in ("native_xyxy", "letterbox_xyxy"):
            return [], "COORDINATE_SPACE_UNKNOWN"
        try:
            raw = list(self.detector.infer(bgr))
            self.detection_diagnostics = {
                **getattr(self.detector, "last_diagnostics", {}),
                "status": "RUN", "allowlist_boxes": len(raw),
                "config_confidence_rejected": 0,
            }
            if len(raw) > 100:
                return [], "TOO_MANY_DETECTIONS"
            result = []
            for d in raw:
                if (type(d.class_id) is not int or str(d.class_id) not in self.config.document["class_map"]
                        or not finite(d.confidence, 0, 1) or len(d.bbox) != 4
                        or not all(finite(n, -1e6, 1e6) for n in d.bbox)
                        or d.bbox[2] <= d.bbox[0] or d.bbox[3] <= d.bbox[1]):
                    return [], "DETECTION_INVALID"
                if d.confidence < self.config.document["min_confidence"]:
                    self.detection_diagnostics["config_confidence_rejected"] += 1
                    continue
                box = d.bbox
                if space == "letterbox_xyxy":
                    mw, mh = self.detector.model_size
                    w, h = size
                    ratio = min(mw / w, mh / h)
                    rw, rh = round(w * ratio), round(h * ratio)
                    left, top = (mw - rw) // 2, (mh - rh) // 2
                    # VM inverse_letterbox clamps; reject padding/truncation first.
                    if not (left <= box[0] < box[2] <= left + rw
                            and top <= box[1] < box[3] <= top + rh):
                        return [], "ROI_TRUNCATED"
                    box = inverse_letterbox(box, size, self.detector.model_size)
                else:
                    box = (math.floor(box[0]), math.floor(box[1]), math.ceil(box[2]), math.ceil(box[3]))
                result.append(Detection(tuple(box), d.confidence, d.class_id, d.track_id))
            return result, None
        except Exception:
            # Do not leak model internals or reuse previous GREEN after failure.
            return [], "MODEL_EXCEPTION"

    def process(self, f, *, now_s):
        if not finite(now_s, 0, 1e16):
            self.invalidate()
            raise ValueError("RECEIVER_CLOCK_INVALID")
        try:
            f.validate()
        except (ValueError, TypeError):
            self.invalidate()
            raise ValueError("FRAME_METADATA_INVALID") from None
        same_packet = ((f.source_id, f.producer_epoch) == self.epoch
                       and f.sequence == self.last_seq and int(f.source_stamp_ns) == self.last_stamp)
        first_receipt = self.last_receipt if same_packet else f.received_s
        first_age = self.last_source_age if same_packet else f.source_age_s
        same_content = f.image_handle == self.last_handle
        flags = self._clock_gate(f, now_s)
        clock_flags = list(flags)
        self.detection_diagnostics = {"status": "NOT_RUN"}
        a = self.config.document["association"]
        bgr = f.bgr
        valid_image = (isinstance(bgr, np.ndarray) and bgr.dtype == np.uint8
                       and bgr.ndim == 3 and bgr.shape[2] == 3
                       and 0 < bgr.shape[0] <= 8192 and 0 < bgr.shape[1] <= 8192)
        size = [bgr.shape[1], bgr.shape[0]] if valid_image else None
        if not valid_image:
            flags.append("IMAGE_DECODE_FAILED")
        elif size != a["native_image_size"]:
            flags.append("BINDING_IMAGE_SIZE_MISMATCH")
        if f.binding_id != a["binding_id"]:
            flags.append("SIGNAL_BINDING_MISMATCH")
        color = {"raw_state": "UNKNOWN", "quality_flags": [], "score": 0., "metrics": {}, "mask": None}
        chosen = None
        detections = []
        association_error = None
        if (valid_image and size == a["native_image_size"] and f.binding_id == a["binding_id"]
                and not {"REPEATED_OR_REVERSED_FRAME", "RETIRED_EPOCH", "RECEIVER_CLOCK_INVALID"}.intersection(flags)):
            detections, error = self._detect(bgr, size)
            if error:
                flags.append(error)
            else:
                chosen, error = self.association.select(
                    detections, a["expected_roi_native"],
                    (f.source_id, f.producer_epoch, f.binding_id),
                )
                if error == "DETECTOR_MISSING" and detections:
                    error = "EXPECTED_ROI_MISMATCH"
                elif error == "DETECTOR_MISSING" and self.detection_diagnostics.get("allowlist_boxes", 0):
                    error = "CONFIDENCE_REJECTED"
                association_error = error
                if error:
                    flags.append(error)
                else:
                    try:
                        color = classify_roi(bgr, chosen.bbox, exposure_settling=f.exposure_settling,
                                             association_verified=a["verified"] or f.source_clock == "fixture")
                        flags.extend(color["quality_flags"])
                    except Exception:
                        flags.append("COLOR_ANALYSIS_EXCEPTION")
        if not a["verified"]:
            flags.append("ASSOCIATION_UNVERIFIED")
        # Account for inference latency on the receiving host. Offline virtual
        # replay deliberately measures wall time separately from its schedule.
        if f.source_clock != "fixture" or self.measure_wall_latency:
            finished = self.clock()
            if not finite(finished, 0, 1e16) or finished < now_s:
                flags.append("RECEIVER_CLOCK_INVALID")
            else:
                now_s = finished
                if now_s - f.received_s > .25:
                    flags.append("RECEIPT_EXPIRED")
                if f.source_age_s is not None and f.source_age_s + now_s - f.received_s > .25:
                    flags.append("SOURCE_STALE")
        flags = list(dict.fromkeys(flags))
        age = None if first_age is None else first_age + max(0., now_s - first_receipt)
        stable = self.temporal.update(
            color["raw_state"], identity=(f.producer_epoch, f.source_id, f.binding_id),
            sequence=f.sequence, source_stamp_ns=f.source_stamp_ns,
            receipt_s=first_receipt, source_age_s=age if age is not None else 3600., flags=flags,
        )
        if flags:
            self.temporal.reset()
            stable = "UNKNOWN"
        signal = {
            "signal_id": a["signal_id"], "crossing_id": a["crossing_id"],
            "raw_state": color["raw_state"], "stable_state": stable,
            "confidence": chosen.confidence if chosen else None, "quality_flags": flags,
            "roi_xyxy_native": list(chosen.bbox) if chosen else None,
            "native_image_size": size, "exposure_metadata": dict(f.exposure_metadata),
            "model_sha256": getattr(self.detector, "sha256", None),
            "preprocess_profile": "vm-combined-" + ColorProfile().sha256[:16],
            "native_image": f.image_handle, "processed_image": None,
        }
        context = {
            "schema_version": "traffic-observation-sidecar.v0.1",
            "source_id": f.source_id, "producer_epoch": f.producer_epoch,
            "sequence": f.sequence, "source_stamp_ns": f.source_stamp_ns,
            "source_clock": f.source_clock, "clock_verified": f.clock_verified,
            "identity_verified": f.identity_verified,
            "first_received_s": first_receipt, "processed_s": now_s,
            "source_age_at_first_receipt_s": first_age,
            "source_age_s": age, "receiver_age_s": max(0., now_s - first_receipt),
            "config_hash": self.config.sha256, "binding_id": f.binding_id,
            "association_verified": a["verified"],
            "detection_candidates": [{"bbox_xyxy_native": list(d.bbox), "confidence": d.confidence,
                                      "class_id": d.class_id, "transient_index": d.track_id} for d in detections],
            "diagnostics": {
                "detector": self.detection_diagnostics,
                "expected_roi_native": a["expected_roi_native"],
                "candidate_ious": [iou(d.bbox, a["expected_roi_native"]) for d in detections],
                "association_rejection": association_error,
                "same_content_as_previous": same_content,
                "source_identity_rejections": clock_flags,
                "crop_selected": chosen is not None,
                "color_rejection": (color["quality_flags"] or
                                    (["COLOR_COMPONENT_TOO_SMALL"] if chosen and color["raw_state"] == "UNKNOWN" else
                                     ["COLOR_AMBIGUOUS"] if color["raw_state"] == "AMBIGUOUS" else [])),
                "temporal_rejection": flags or (["TEMPORAL_NOT_STABLE"] if stable == "UNKNOWN" else []),
                "terminal_rejection": ("INPUT_REJECTED" if not valid_image else
                                       "SOURCE_IDENTITY_REJECTED" if {"REPEATED_OR_REVERSED_FRAME", "RETIRED_EPOCH", "RECEIVER_CLOCK_INVALID"}.intersection(flags) else
                                       "BINDING_REJECTED" if {"BINDING_IMAGE_SIZE_MISMATCH", "SIGNAL_BINDING_MISMATCH"}.intersection(flags) else
                                       "DETECTION_REJECTED" if not detections else
                                       association_error if chosen is None else
                                       "COLOR_REJECTED" if color["raw_state"] not in ("RED", "GREEN") else
                                       "ASSOCIATION_UNVERIFIED" if not a["verified"] else
                                       "TEMPORAL_OR_FRESHNESS_REJECTED" if stable == "UNKNOWN" else None),
            },
            "provenance": f.provenance, "original_metadata": f.original_metadata,
            "color_metrics": color["metrics"], "color_score": color["score"],
            "receipt_ttl_s": .25, "stability_s": .4,
            "feet": None, "physical_stop": None, "posture": None, "path_clear": None,
            "complete_mission_evidence": False, "departure_authorized": False,
        }
        obs = Observation(signal, context, color["mask"])
        self.latest, self.latest_receipt, self.latest_age = obs, now_s, age
        if not flags and stable in ("RED", "GREEN") and f.source_clock != "fixture":
            self.last_valid_observation_s = f.received_s
        return obs

    def invalidate(self):
        self.temporal.reset()
        self.latest = None

    def current_state(self, *, now_s):
        """Watchdog read only: no new observation, stamp, or sequence is minted."""
        if (self.latest is None or self.latest_age is None or not finite(now_s, 0, 1e16)
                or now_s < self.latest_receipt
                or self.latest_age + now_s - self.latest_receipt > .25):
            self.temporal.reset()
            return "UNKNOWN"
        return self.temporal.current(now_s)
