"""Crosswalk advisory state machine; it never emits a motion command."""

from __future__ import annotations

from typing import Any, Mapping

from .models import BehaviorContractError, finite, make_advisory_snapshot, uint64


class CrosswalkAdvisor:
    def __init__(
        self, *, lateral_limit_m: float = 0.15, heading_limit_rad: float = 0.2
    ) -> None:
        self._lateral_limit_m = finite(lateral_limit_m, "lateral limit", 0.01, 1.0)
        self._heading_limit_rad = finite(heading_limit_rad, "heading limit", 0.01, 1.0)
        self._last_sequence = -1
        self._recovery_after_sequence = -1
        self._was_ready = False

    def _result(
        self,
        *,
        state: str,
        advisory: str,
        now_ns: int,
        reasons: list[str],
        requirements: Mapping[str, bool | int | str | None],
        manual_ready: bool = False,
        auto_ready: bool = False,
    ) -> dict[str, Any]:
        self._was_ready = state in {"READY", "CROSSING_OBSERVE"}
        return make_advisory_snapshot(
            behavior="CROSSWALK",
            state=state,
            advisory=advisory,
            ready_for_manual_proceed=manual_ready,
            autonomous_edge_ready=auto_ready,
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
        distance_to_entry_m: float | None = None,
        route_deviation_m: float = 0.0,
        pose_fresh: bool = True,
        revisions_current: bool = True,
        crossing: bool = False,
        exit_confirmed: bool = False,
        feet_outside_count: int | None = None,
        expected_crosswalk_id: str | None = None,
    ) -> dict[str, Any]:
        now = uint64(now_ns, "now_ns")
        if not isinstance(segment, Mapping) or segment.get("type") != "CROSSWALK":
            return self._result(
                state="IDLE", advisory="HOLD", now_ns=now, reasons=[], requirements={}
            )
        try:
            deviation = finite(route_deviation_m, "route deviation", 0.0, 1_000.0)
            distance = (
                None
                if distance_to_entry_m is None
                else finite(distance_to_entry_m, "entry distance", 0.0, 1_000.0)
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
        invalid_reasons = []
        if not revisions_current:
            invalid_reasons.append("REVISION_CHANGED")
        if not pose_fresh:
            invalid_reasons.append("POSE_STALE")
        if invalid_reasons:
            self._recovery_after_sequence = max(self._recovery_after_sequence, sequence)
            return self._result(
                state="FAULT",
                advisory="FAULT",
                now_ns=now,
                reasons=invalid_reasons,
                requirements={},
            )
        if perception.get("fresh") is not True:
            self._recovery_after_sequence = max(self._recovery_after_sequence, sequence)
            return self._result(
                state="HOLD",
                advisory="HOLD",
                now_ns=now,
                reasons=["PERCEPTION_STALE"],
                requirements={},
            )
        if sequence <= self._recovery_after_sequence:
            return self._result(
                state="HOLD",
                advisory="HOLD",
                now_ns=now,
                reasons=["NEW_EVIDENCE_REQUIRED"],
                requirements={},
            )
        traffic = [
            item
            for item in perception.get("traffic", [])
            if expected_crosswalk_id is None
            or item.get("crosswalk_id") == expected_crosswalk_id
        ]
        people = [
            item
            for item in perception.get("people", [])
            if expected_crosswalk_id is None
            or item.get("crosswalk_id") == expected_crosswalk_id
        ]
        crosswalks = [
            item
            for item in perception.get("crosswalks", [])
            if expected_crosswalk_id is None
            or item.get("crosswalk_id") == expected_crosswalk_id
        ]
        traffic_green = bool(traffic) and all(
            item.get("signal") == "GREEN"
            and int(item.get("consecutive_frames", 1)) >= 2
            for item in traffic
        )
        traffic_red = any(item.get("signal") == "RED" for item in traffic)
        person_clear = bool(people) and all(
            item.get("occupancy") == "CLEAR" for item in people
        )
        person_occupied = any(item.get("occupancy") == "OCCUPIED" for item in people)
        alignment_ready = bool(crosswalks) and all(
            item.get("visible") is True
            and abs(float(item.get("lateral_offset_m", 99.0))) <= self._lateral_limit_m
            and abs(float(item.get("heading_error_rad", 99.0)))
            <= self._heading_limit_rad
            for item in crosswalks
        )
        boundaries_ready = bool(crosswalks) and all(
            float(item.get("left_boundary_distance_m", -1.0)) >= 0.0
            and float(item.get("right_boundary_distance_m", -1.0)) >= 0.0
            for item in crosswalks
        )
        if feet_outside_count is not None and (
            isinstance(feet_outside_count, bool)
            or not isinstance(feet_outside_count, int)
            or not 0 <= feet_outside_count <= 4
        ):
            return self._result(
                state="FAULT",
                advisory="FAULT",
                now_ns=now,
                reasons=["FEET_COUNT_INVALID"],
                requirements={},
            )
        feet_boundary: bool | None = (
            None if feet_outside_count is None else feet_outside_count < 3
        )
        requirements = {
            "traffic_green": traffic_green,
            "person_clear": person_clear,
            "alignment_ready": alignment_ready,
            "boundaries_ready": boundaries_ready,
            "feet_boundary": feet_boundary,
        }
        if deviation > 1.5:
            return self._result(
                state="HOLD",
                advisory="REPLAN_RECOMMENDED",
                now_ns=now,
                reasons=["ROUTE_DEVIATION"],
                requirements=requirements,
            )
        if feet_boundary is False:
            return self._result(
                state="HOLD",
                advisory="HOLD",
                now_ns=now,
                reasons=["FOOT_BOUNDARY_VIOLATION"],
                requirements=requirements,
            )
        if self._was_ready and (not alignment_ready or not boundaries_ready):
            self._recovery_after_sequence = sequence
            return self._result(
                state="HOLD",
                advisory="HOLD",
                now_ns=now,
                reasons=["ALIGNMENT_LOST_AFTER_READY"],
                requirements=requirements,
            )
        if not traffic_green:
            reason = "TRAFFIC_RED" if traffic_red else "TRAFFIC_UNKNOWN_OR_UNSTABLE"
            state = (
                "STOP_LINE"
                if distance is not None and distance <= 0.3 and not traffic
                else "WAIT_SIGNAL"
            )
            return self._result(
                state=state,
                advisory="WAIT",
                now_ns=now,
                reasons=[reason],
                requirements=requirements,
            )
        if not person_clear:
            reason = "PERSON_OCCUPIED" if person_occupied else "PERSON_UNKNOWN"
            return self._result(
                state="WAIT_PERSON",
                advisory="WAIT",
                now_ns=now,
                reasons=[reason],
                requirements=requirements,
            )
        if not alignment_ready or not boundaries_ready:
            return self._result(
                state="ALIGN",
                advisory="ALIGN",
                now_ns=now,
                reasons=["CROSSWALK_ALIGNMENT_REQUIRED"],
                requirements=requirements,
            )
        if exit_confirmed:
            return self._result(
                state="EXIT_CONFIRMED",
                advisory="COMPLETE",
                now_ns=now,
                reasons=[],
                requirements=requirements,
            )
        if crossing:
            return self._result(
                state="CROSSING_OBSERVE",
                advisory="PROCEED_RECOMMENDED",
                now_ns=now,
                reasons=["OBSERVE_WHILE_CROSSING"],
                requirements=requirements,
                manual_ready=True,
                auto_ready=True,
            )
        if distance is not None and distance > 2.0:
            return self._result(
                state="APPROACH",
                advisory="HOLD",
                now_ns=now,
                reasons=["APPROACHING_CROSSWALK"],
                requirements=requirements,
            )
        return self._result(
            state="READY",
            advisory="PROCEED_RECOMMENDED",
            now_ns=now,
            reasons=[],
            requirements=requirements,
            manual_ready=True,
            auto_ready=True,
        )


__all__ = ["CrosswalkAdvisor"]
