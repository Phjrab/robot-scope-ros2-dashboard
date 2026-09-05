"""ArUco docking advisory state machine without visual-servo output."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .models import BehaviorContractError, finite, make_advisory_snapshot, token, uint64


class DockingAdvisor:
    def __init__(
        self,
        *,
        confidence_threshold: float = 0.8,
        target_jump_limit_m: float = 0.5,
        yaw_jump_limit_rad: float = 0.5,
    ) -> None:
        self._confidence_threshold = finite(
            confidence_threshold, "confidence threshold", 0.0, 1.0
        )
        self._target_jump_limit_m = finite(
            target_jump_limit_m, "target jump limit", 0.01, 5.0
        )
        self._yaw_jump_limit_rad = finite(
            yaw_jump_limit_rad, "yaw jump limit", 0.01, math.pi
        )
        self._last_sequence = -1
        self._last_target: tuple[float, float, float] | None = None
        self._last_target_sequence = -1
        self._recovery_after_sequence = -1

    def _result(
        self,
        *,
        state: str,
        advisory: str,
        now_ns: int,
        reasons: list[str],
        requirements: Mapping[str, bool | int | str | None],
        ready: bool = False,
    ) -> dict[str, Any]:
        return make_advisory_snapshot(
            behavior="DOCKING",
            state=state,
            advisory=advisory,
            ready_for_manual_proceed=ready,
            autonomous_edge_ready=ready,
            reason_codes=reasons,
            requirements=requirements,
            updated_at_ns=now_ns,
        )

    def evaluate(
        self,
        *,
        segment: Mapping[str, Any] | None,
        perception: Mapping[str, Any],
        now_ns: int,
        expected_venue_id: str | None,
        expected_zone_id: str | None = None,
        distance_to_dock_m: float | None = None,
        pose_fresh: bool = True,
        revisions_current: bool = True,
        dock_contact_confirmed: bool = False,
    ) -> dict[str, Any]:
        now = uint64(now_ns, "now_ns")
        if (
            not isinstance(segment, Mapping)
            or segment.get("type") != "DOCKING_APPROACH"
        ):
            return self._result(
                state="IDLE", advisory="HOLD", now_ns=now, reasons=[], requirements={}
            )
        try:
            venue = token(expected_venue_id, "expected venue")
            zone = (
                None
                if expected_zone_id is None
                else token(expected_zone_id, "expected zone")
            )
            distance = (
                None
                if distance_to_dock_m is None
                else finite(distance_to_dock_m, "dock distance", 0.0, 1_000.0)
            )
            sequence = uint64(perception.get("sequence"), "perception sequence")
        except BehaviorContractError:
            return self._result(
                state="FAULT",
                advisory="FAULT",
                now_ns=now,
                reasons=["INPUT_INVALID"],
                requirements={},
            )
        if sequence < self._last_sequence:
            self._recovery_after_sequence = max(
                self._recovery_after_sequence, self._last_sequence
            )
            return self._result(
                state="FAULT",
                advisory="FAULT",
                now_ns=now,
                reasons=["SEQUENCE_ROLLBACK"],
                requirements={},
            )
        self._last_sequence = max(self._last_sequence, sequence)
        if not revisions_current or not pose_fresh:
            self._recovery_after_sequence = max(self._recovery_after_sequence, sequence)
            reasons = ["REVISION_CHANGED"] if not revisions_current else ["POSE_STALE"]
            return self._result(
                state="FAULT",
                advisory="FAULT",
                now_ns=now,
                reasons=reasons,
                requirements={},
            )
        if perception.get("fresh") is not True:
            self._recovery_after_sequence = max(self._recovery_after_sequence, sequence)
            return self._result(
                state="LOST",
                advisory="HOLD",
                now_ns=now,
                reasons=["PERCEPTION_STALE"],
                requirements={},
            )
        if sequence <= self._recovery_after_sequence:
            return self._result(
                state="LOST",
                advisory="HOLD",
                now_ns=now,
                reasons=["NEW_EVIDENCE_REQUIRED"],
                requirements={},
            )
        observations = list(perception.get("aruco", []))
        candidates = [item for item in observations if item.get("venue_id") == venue]
        if observations and not candidates:
            self._recovery_after_sequence = max(self._recovery_after_sequence, sequence)
            return self._result(
                state="FAULT",
                advisory="FAULT",
                now_ns=now,
                reasons=["VENUE_MISMATCH"],
                requirements={"expected_venue": venue},
            )
        if not candidates:
            state = "LOST" if self._last_target is not None else "SEARCH_MARKER"
            return self._result(
                state=state,
                advisory="SEARCH_MARKER",
                now_ns=now,
                reasons=["MARKER_NOT_VISIBLE"],
                requirements={"expected_venue": venue, "marker_visible": False},
            )
        observation = candidates[0]
        if zone is not None and observation.get("zone_id") not in {None, zone}:
            self._recovery_after_sequence = max(self._recovery_after_sequence, sequence)
            return self._result(
                state="FAULT",
                advisory="FAULT",
                now_ns=now,
                reasons=["ZONE_MISMATCH"],
                requirements={"expected_venue": venue, "expected_zone": zone},
            )
        marker_ids = observation.get("marker_ids", [])
        marker_count = len(marker_ids) if isinstance(marker_ids, list) else 0
        confidence = observation.get("confidence")
        try:
            confidence_value = finite(confidence, "ArUco confidence", 0.0, 1.0)
        except BehaviorContractError:
            confidence_value = 0.0
        raw_target = observation.get("target_pose")
        target: tuple[float, float, float] | None = None
        if isinstance(raw_target, Mapping) and set(raw_target) == {
            "x",
            "y",
            "z",
            "yaw",
        }:
            try:
                target = (
                    finite(raw_target["x"], "target x", -1_000.0, 1_000.0),
                    finite(raw_target["y"], "target y", -1_000.0, 1_000.0),
                    finite(raw_target["yaw"], "target yaw", -math.pi, math.pi),
                )
            except BehaviorContractError:
                target = None
        requirements = {
            "expected_venue": venue,
            "expected_zone": zone,
            "marker_count": marker_count,
            "confidence_ready": confidence_value >= self._confidence_threshold,
            "target_pose_ready": target is not None,
            "docking_ready": observation.get("docking_ready") is True,
        }
        if (
            target is not None
            and self._last_target is not None
            and sequence > self._last_target_sequence
        ):
            translation_jump = math.hypot(
                target[0] - self._last_target[0], target[1] - self._last_target[1]
            )
            yaw_jump = abs(
                math.atan2(
                    math.sin(target[2] - self._last_target[2]),
                    math.cos(target[2] - self._last_target[2]),
                )
            )
            if (
                translation_jump > self._target_jump_limit_m
                or yaw_jump > self._yaw_jump_limit_rad
            ):
                self._recovery_after_sequence = sequence
                return self._result(
                    state="FAULT",
                    advisory="FAULT",
                    now_ns=now,
                    reasons=["TARGET_JUMP"],
                    requirements=requirements,
                )
        if target is not None:
            self._last_target = target
            self._last_target_sequence = sequence
        if distance is not None and distance > 1.0:
            return self._result(
                state="COARSE_APPROACH",
                advisory="HOLD",
                now_ns=now,
                reasons=["DOCK_APPROACH_DISTANCE"],
                requirements=requirements,
            )
        if marker_count < 1:
            return self._result(
                state="SEARCH_MARKER",
                advisory="SEARCH_MARKER",
                now_ns=now,
                reasons=["MARKER_NOT_VISIBLE"],
                requirements=requirements,
            )
        if confidence_value < self._confidence_threshold or target is None:
            return self._result(
                state="TRACK_MARKER",
                advisory="SEARCH_MARKER",
                now_ns=now,
                reasons=["MARKER_EVIDENCE_INSUFFICIENT"],
                requirements=requirements,
            )
        if (
            observation.get("docking_ready") is not True
            or abs(target[1]) > 0.15
            or abs(target[2]) > 0.2
        ):
            return self._result(
                state="ALIGN",
                advisory="ALIGN",
                now_ns=now,
                reasons=["DOCK_ALIGNMENT_REQUIRED"],
                requirements=requirements,
            )
        if dock_contact_confirmed:
            return self._result(
                state="DOCKED_CANDIDATE",
                advisory="HOLD",
                now_ns=now,
                reasons=["OPERATOR_CONFIRMATION_REQUIRED"],
                requirements=requirements,
            )
        return self._result(
            state="READY",
            advisory="DOCKING_READY",
            now_ns=now,
            reasons=[],
            requirements=requirements,
            ready=True,
        )


__all__ = ["DockingAdvisor"]
