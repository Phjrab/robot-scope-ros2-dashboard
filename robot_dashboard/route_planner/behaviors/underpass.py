"""Underpass clearance advisory; special gait remains operator-owned."""

from __future__ import annotations

from typing import Any, Mapping

from .models import BehaviorContractError, finite, make_advisory_snapshot, uint64


class UnderpassAdvisor:
    def __init__(self) -> None:
        self._last_sequence = -1
        self._recovery_after_sequence = -1
        self._confirmation_epoch = 0

    def invalidate_confirmation(self) -> None:
        self._confirmation_epoch += 1

    @property
    def confirmation_epoch(self) -> int:
        return self._confirmation_epoch

    def _result(
        self,
        *,
        state: str,
        advisory: str,
        now_ns: int,
        reasons: list[str],
        requirements: Mapping[str, bool | int | str | None],
        manual_ready: bool = False,
    ) -> dict[str, Any]:
        return make_advisory_snapshot(
            behavior="UNDERPASS",
            state=state,
            advisory=advisory,
            ready_for_manual_proceed=manual_ready,
            autonomous_edge_ready=False,
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
        operator_confirmed: bool = False,
        service_robot_clear: bool | None = None,
        distance_to_entry_m: float | None = None,
        pose_fresh: bool = True,
        revisions_current: bool = True,
        traversing: bool = False,
        exit_observed: bool = False,
        confirmation_epoch: int = 0,
    ) -> dict[str, Any]:
        now = uint64(now_ns, "now_ns")
        if not isinstance(segment, Mapping) or segment.get("type") != "UNDERPASS":
            return self._result(
                state="IDLE", advisory="HOLD", now_ns=now, reasons=[], requirements={}
            )
        try:
            sequence = uint64(perception.get("sequence"), "perception sequence")
            distance = (
                None
                if distance_to_entry_m is None
                else finite(distance_to_entry_m, "entry distance", 0.0, 1_000.0)
            )
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
            self.invalidate_confirmation()
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
            self.invalidate_confirmation()
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
            self.invalidate_confirmation()
            return self._result(
                state="WAIT_CLEAR",
                advisory="HOLD",
                now_ns=now,
                reasons=["PERCEPTION_STALE"],
                requirements={},
            )
        if sequence <= self._recovery_after_sequence:
            return self._result(
                state="WAIT_CLEAR",
                advisory="HOLD",
                now_ns=now,
                reasons=["NEW_EVIDENCE_REQUIRED"],
                requirements={},
            )
        if service_robot_clear is not None and not isinstance(
            service_robot_clear, bool
        ):
            return self._result(
                state="FAULT",
                advisory="FAULT",
                now_ns=now,
                reasons=["SERVICE_ROBOT_STATE_INVALID"],
                requirements={},
            )
        blocked = perception.get("underpass_blocked")
        person_states = [item.get("occupancy") for item in perception.get("people", [])]
        person_clear = bool(person_states) and all(
            item == "CLEAR" for item in person_states
        )
        person_blocked = any(item == "OCCUPIED" for item in person_states)
        requirements = {
            "underpass_clear": blocked is False,
            "person_clear": person_clear,
            "service_robot_clear": service_robot_clear,
            "operator_confirmed": operator_confirmed
            and confirmation_epoch == self._confirmation_epoch,
            "special_gait_operator_owned": True,
        }
        if blocked is True or person_blocked or service_robot_clear is False:
            reasons = []
            if blocked is True:
                reasons.append("UNDERPASS_BLOCKED")
            if person_blocked:
                reasons.append("PERSON_OCCUPIED")
            if service_robot_clear is False:
                reasons.append("SERVICE_ROBOT_BLOCKED")
            return self._result(
                state="BLOCKED",
                advisory="HOLD",
                now_ns=now,
                reasons=reasons,
                requirements=requirements,
            )
        if blocked is not False or not person_clear or service_robot_clear is None:
            return self._result(
                state="WAIT_CLEAR",
                advisory="WAIT",
                now_ns=now,
                reasons=["CLEARANCE_UNKNOWN"],
                requirements=requirements,
            )
        if distance is not None and distance > 1.0:
            return self._result(
                state="APPROACH",
                advisory="HOLD",
                now_ns=now,
                reasons=["APPROACHING_UNDERPASS"],
                requirements=requirements,
            )
        if exit_observed:
            return self._result(
                state="EXIT",
                advisory="COMPLETE",
                now_ns=now,
                reasons=[],
                requirements=requirements,
            )
        if traversing:
            return self._result(
                state="TRAVERSING_OBSERVE",
                advisory="PROCEED_RECOMMENDED",
                now_ns=now,
                reasons=["OBSERVE_WHILE_TRAVERSING"],
                requirements=requirements,
                manual_ready=True,
            )
        if not requirements["operator_confirmed"]:
            return self._result(
                state="WAIT_CLEAR",
                advisory="WAIT",
                now_ns=now,
                reasons=["OPERATOR_CONFIRMATION_REQUIRED"],
                requirements=requirements,
            )
        return self._result(
            state="READY",
            advisory="PROCEED_RECOMMENDED",
            now_ns=now,
            reasons=["SPECIAL_GAIT_OPERATOR_OWNED"],
            requirements=requirements,
            manual_ready=True,
        )


__all__ = ["UnderpassAdvisor"]
