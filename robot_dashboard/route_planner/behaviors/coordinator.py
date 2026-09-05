"""Select exactly one active advisory behavior for the current route segment."""

from __future__ import annotations

from typing import Any, Mapping

from .crosswalk import CrosswalkAdvisor
from .delivery import DeliveryWorkflow
from .docking import DockingAdvisor
from .models import BehaviorContractError, finite, make_advisory_snapshot, uint64
from .underpass import UnderpassAdvisor


class AdvisoryBehaviorCoordinator:
    def __init__(self, *, delivery: DeliveryWorkflow | None = None) -> None:
        self.crosswalk = CrosswalkAdvisor()
        self.docking = DockingAdvisor()
        self.underpass = UnderpassAdvisor()
        self.delivery = delivery
        self._recovery_after_sequence = -1

    @staticmethod
    def _fault(now_ns: int, reason: str) -> dict[str, Any]:
        return make_advisory_snapshot(
            behavior="FAULT",
            state="FAULT",
            advisory="FAULT",
            ready_for_manual_proceed=False,
            autonomous_edge_ready=False,
            reason_codes=[reason],
            requirements={},
            updated_at_ns=now_ns,
        )

    def _invalidate_evidence(self, perception: Mapping[str, Any]) -> None:
        try:
            sequence = uint64(perception.get("sequence"), "perception sequence")
        except BehaviorContractError:
            return
        self._recovery_after_sequence = max(self._recovery_after_sequence, sequence)

    @staticmethod
    def _expected_venue(
        route: Mapping[str, Any] | None, segment: Mapping[str, Any]
    ) -> str | None:
        if not isinstance(route, Mapping):
            return None
        target = segment.get("to_node_id")
        for stop in route.get("stops", []):
            if (
                isinstance(stop, Mapping)
                and stop.get("node_id") == target
                and isinstance(stop.get("venue_id"), str)
            ):
                return str(stop["venue_id"])
        return None

    def evaluate(
        self,
        *,
        route: Mapping[str, Any] | None,
        guidance: Mapping[str, Any],
        perception: Mapping[str, Any],
        now_ns: int,
        pose_fresh: bool = True,
        revisions_current: bool = True,
        server_restarted: bool = False,
        external_fault: str | None = None,
        operator_confirmed: bool = False,
        service_robot_clear: bool | None = None,
        crossing: bool = False,
        exit_confirmed: bool = False,
        dock_contact_confirmed: bool = False,
        feet_outside_count: int | None = None,
    ) -> dict[str, Any]:
        now = uint64(now_ns, "now_ns")
        if server_restarted:
            self._invalidate_evidence(perception)
            return self._fault(now, "SERVER_RESTART")
        if external_fault:
            self._invalidate_evidence(perception)
            return self._fault(now, "EXTERNAL_INPUT_INVALID")
        if not revisions_current:
            self._invalidate_evidence(perception)
            return self._fault(now, "REVISION_CHANGED")
        if not pose_fresh:
            self._invalidate_evidence(perception)
            return self._fault(now, "POSE_STALE")
        segment = guidance.get("current_segment")
        if not isinstance(segment, Mapping):
            self._invalidate_evidence(perception)
            return self._fault(now, "CURRENT_SEGMENT_UNAVAILABLE")
        try:
            sequence = uint64(perception.get("sequence"), "perception sequence")
        except BehaviorContractError:
            self._invalidate_evidence(perception)
            return self._fault(now, "EXTERNAL_INPUT_INVALID")
        if sequence <= self._recovery_after_sequence:
            return self._fault(now, "NEW_EVIDENCE_REQUIRED")
        if guidance.get("off_route") is True:
            return make_advisory_snapshot(
                behavior="NORMAL_GUIDANCE",
                state="HOLD",
                advisory="REPLAN_RECOMMENDED",
                ready_for_manual_proceed=False,
                autonomous_edge_ready=False,
                reason_codes=["ROUTE_DEVIATION"],
                requirements={"pose_fresh": True, "revisions_current": True},
                updated_at_ns=now,
            )
        try:
            progress = finite(
                guidance.get("segment_progress", 0.0), "segment progress", 0.0, 1.0
            )
            segment_distance = finite(
                segment.get("distance_m", 0.0), "segment distance", 0.0, 1_000_000.0
            )
            deviation = finite(
                guidance.get("cross_track_error_m", 0.0),
                "cross track error",
                0.0,
                1_000_000.0,
            )
        except BehaviorContractError:
            self._invalidate_evidence(perception)
            return self._fault(now, "EXTERNAL_INPUT_INVALID")
        distance = segment_distance * (1.0 - progress)
        kind = segment.get("type")
        if kind == "DOCKING_APPROACH":
            venue = self._expected_venue(route, segment)
            if venue is None:
                return self._fault(now, "EXPECTED_VENUE_UNAVAILABLE")
            return self.docking.evaluate(
                segment=segment,
                perception=perception,
                now_ns=now,
                expected_venue_id=venue,
                distance_to_dock_m=distance,
                pose_fresh=pose_fresh,
                revisions_current=revisions_current,
                dock_contact_confirmed=dock_contact_confirmed,
            )
        if kind == "CROSSWALK":
            return self.crosswalk.evaluate(
                segment=segment,
                perception=perception,
                now_ns=now,
                distance_to_entry_m=distance,
                route_deviation_m=deviation,
                pose_fresh=pose_fresh,
                revisions_current=revisions_current,
                crossing=crossing,
                exit_confirmed=exit_confirmed,
                feet_outside_count=feet_outside_count,
            )
        if kind == "UNDERPASS":
            return self.underpass.evaluate(
                segment=segment,
                perception=perception,
                now_ns=now,
                operator_confirmed=operator_confirmed,
                service_robot_clear=service_robot_clear,
                distance_to_entry_m=distance,
                pose_fresh=pose_fresh,
                revisions_current=revisions_current,
                traversing=crossing,
                exit_observed=exit_confirmed,
                confirmation_epoch=self.underpass.confirmation_epoch,
            )
        if self.delivery is not None and self.delivery.state in {
            "PICKUP_CONFIRMATION_REQUIRED",
            "DROPOFF_CONFIRMATION_REQUIRED",
            "FAILED",
        }:
            return self.delivery.snapshot(now)
        if perception.get("fresh") is not True:
            return make_advisory_snapshot(
                behavior="NORMAL_GUIDANCE",
                state="HOLD",
                advisory="HOLD",
                ready_for_manual_proceed=False,
                autonomous_edge_ready=False,
                reason_codes=["PERCEPTION_STALE"],
                requirements={"pose_fresh": True, "revisions_current": True},
                updated_at_ns=now,
            )
        return make_advisory_snapshot(
            behavior="NORMAL_GUIDANCE",
            state="READY",
            advisory="PROCEED_RECOMMENDED",
            ready_for_manual_proceed=True,
            autonomous_edge_ready=bool(segment.get("allow_autonomous", True)),
            reason_codes=[],
            requirements={"pose_fresh": True, "revisions_current": True},
            updated_at_ns=now,
        )


__all__ = ["AdvisoryBehaviorCoordinator"]
