"""Bounded image-space association, not a camera pose or crossing calibration."""
from experiments.competition_vm.traffic_signals.detector import iou


class BoundedAssociation:
    def __init__(self, min_iou=.2, margin=.15, continuity_iou=.25):
        self.min_iou, self.margin, self.continuity_iou = min_iou, margin, continuity_iou
        self.identity = None
        self.last = self.pending = None
        self.reconfirm = False
        self.generation = 0
        self.reason = "NO_TRACK"

    def invalidate(self, reason="OCCLUDED"):
        self.last = self.pending = None
        self.reconfirm = True
        self.reason = reason

    def select(self, detections, expected_roi, identity):
        if identity != self.identity:
            self.last = self.pending = None
            self.reconfirm = self.identity is not None
            self.identity = identity
        ranked = sorted(((iou(d.bbox, expected_roi), d) for d in detections), key=lambda x: x[0], reverse=True)
        if not ranked or ranked[0][0] < self.min_iou:
            self.invalidate("NO_EXPECTED_REGION_MATCH")
            return None, "DETECTOR_MISSING"
        eligible = [d for score, d in ranked if score >= self.min_iou]
        if len(ranked) > 1 and ranked[0][0]-ranked[1][0] < self.margin:
            self.invalidate("MULTIPLE_EXPECTED_REGION_MATCHES")
            return None, "ASSOCIATION_UNCERTAIN"
        chosen = ranked[0][1]
        previous = self.last if self.last is not None else self.pending
        if previous is not None:
            continuity = sorted(((iou(d.bbox, previous.bbox), d) for d in eligible), key=lambda x: x[0], reverse=True)
            if len(continuity) > 1 and continuity[0][0]-continuity[1][0] < self.margin:
                self.invalidate("MULTIPLE_CONTINUITY_MATCHES")
                return None, "ASSOCIATION_UNCERTAIN"
            if continuity[0][0] < self.continuity_iou:
                self.invalidate("GEOMETRY_JUMP")
                self.pending = chosen
                return None, "TRACK_RESET"
            chosen = continuity[0][1]
        if self.reconfirm and self.pending is None:
            self.pending = chosen
            self.reason = "WAIT_SECOND_FRESH_DETECTION"
            return None, "ASSOCIATION_REACQUIRING"
        if self.last is None:
            self.generation += 1
        self.last, self.pending, self.reconfirm = chosen, None, False
        self.reason = "UNIQUE_IMAGE_SPACE_MATCH"
        return chosen, None

    def snapshot(self):
        return {"status": "associated" if self.last is not None else "unassociated",
                "reason": self.reason, "track_generation": self.generation,
                "external_detection_ids_used": False, "crossing_geometry_verified_by_tracker": False,
                "min_expected_iou": self.min_iou, "min_continuity_iou": self.continuity_iou,
                "ambiguity_margin": self.margin, "reconfirmation_frames_after_loss": 2}
