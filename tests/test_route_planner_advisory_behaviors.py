from __future__ import annotations

import ast
import copy
import inspect
import json
import unittest
from pathlib import Path

from robot_dashboard.route_planner.behaviors import (
    AdvisoryBehaviorCoordinator,
    BehaviorContractError,
    CrosswalkAdvisor,
    DeliveryWorkflow,
    DockingAdvisor,
    UnderpassAdvisor,
    make_advisory_snapshot,
)
from robot_dashboard.route_planner.orders import normalize_order
from robot_dashboard.route_planner.perception import normalize_perception_snapshot
from robot_dashboard.route_planner.replay import SCENARIO_ROOT, replay_scenario_file


BASE_NS = 10_000_000_000
PUBLIC_KEYS = {
    "behavior",
    "state",
    "advisory",
    "ready_for_manual_proceed",
    "autonomous_edge_ready",
    "reason_codes",
    "requirements",
    "updated_at_ns",
}
FORBIDDEN_KEYS = {
    "linear_x",
    "linear_y",
    "angular_z",
    "cmd_vel",
    "sport_request",
    "navigation_goal",
}


def order() -> dict:
    return normalize_order(
        {
            "label": "Behavior order",
            "destination_id": "COEX",
            "lines": [
                {
                    "sequence": 1,
                    "restaurant_id": "HANSOT",
                    "menu_id": "CHICKEN_MAYO",
                    "quantity": 2,
                },
                {
                    "sequence": 2,
                    "restaurant_id": "EDIYA",
                    "menu_id": "AMERICANO",
                    "quantity": 1,
                },
            ],
            "order_started_at": None,
            "locked": False,
        },
        order_id="1" * 32,
    )


def perception(
    *,
    sequence: int = 1,
    observed_at_ns: int = BASE_NS,
    now_ns: int = BASE_NS,
    signal: str = "GREEN",
    consecutive_frames: int = 3,
    occupancy: str = "CLEAR",
    lateral: float = 0.02,
    heading: float = 0.01,
    underpass_blocked: bool | None = False,
    aruco: list[dict] | None = None,
) -> dict:
    raw = {
        "schema_version": 1,
        "source": "behavior-test",
        "frame_id": "base_link",
        "observed_at_ns": observed_at_ns,
        "sequence": sequence,
        "state": "READY",
        "confidence": 0.95,
        "traffic": [
            {
                "crosswalk_id": "NORTH",
                "signal": signal,
                "consecutive_frames": consecutive_frames,
            }
        ],
        "crosswalks": [
            {
                "crosswalk_id": "NORTH",
                "visible": True,
                "lateral_offset_m": lateral,
                "heading_error_rad": heading,
                "left_boundary_distance_m": 0.3,
                "right_boundary_distance_m": 0.3,
            }
        ],
        "people": [{"crosswalk_id": "NORTH", "occupancy": occupancy}],
        "aruco": aruco
        if aruco is not None
        else [
            {
                "venue_id": "COEX",
                "zone_id": "ZONE_1",
                "docking_ready": True,
                "marker_ids": [10],
                "target_pose": {"x": 0.1, "y": 0.01, "z": 0.0, "yaw": 0.01},
                "confidence": 0.95,
            }
        ],
        "underpass_blocked": underpass_blocked,
    }
    return normalize_perception_snapshot(raw, now_ns=now_ns)


def crosswalk_segment() -> dict:
    return {
        "type": "CROSSWALK",
        "distance_m": 1.0,
        "requirements": [
            {"id": "TRAFFIC_GREEN"},
            {"id": "PEDESTRIAN_CLEAR"},
            {"id": "CROSSWALK_ALIGNMENT"},
            {"id": "LANE_BOUNDARY_VALID"},
        ],
        "allow_autonomous": True,
        "to_node_id": "CROSSWALK_EXIT",
    }


def docking_segment() -> dict:
    return {
        "type": "DOCKING_APPROACH",
        "distance_m": 1.0,
        "requirements": [{"id": "ARUCO_DOCKING"}],
        "allow_autonomous": True,
        "to_node_id": "COEX_DOCK",
    }


def underpass_segment() -> dict:
    return {
        "type": "UNDERPASS",
        "distance_m": 1.0,
        "requirements": [{"id": "SPECIAL_GAIT"}],
        "allow_autonomous": True,
        "to_node_id": "EDIYA_DOCK",
    }


def normal_segment() -> dict:
    return {
        "type": "NORMAL_WALKWAY",
        "distance_m": 1.0,
        "requirements": [],
        "allow_autonomous": True,
        "to_node_id": "HANSOT_DOCK",
    }


def guidance(segment: dict, *, progress: float = 0.5, deviation: float = 0.0) -> dict:
    return {
        "current_segment": segment,
        "segment_progress": progress,
        "cross_track_error_m": deviation,
    }


class AdvisoryModelTests(unittest.TestCase):
    def test_common_snapshot_has_exact_public_fields(self) -> None:
        value = make_advisory_snapshot(
            behavior="NORMAL_GUIDANCE",
            state="READY",
            advisory="PROCEED_RECOMMENDED",
            ready_for_manual_proceed=True,
            autonomous_edge_ready=True,
            reason_codes=[],
            requirements={"pose_fresh": True},
            updated_at_ns=BASE_NS,
        )
        self.assertEqual(set(value), PUBLIC_KEYS)

    def test_common_snapshot_rejects_unknown_advisory(self) -> None:
        with self.assertRaises(BehaviorContractError):
            make_advisory_snapshot(
                behavior="NORMAL_GUIDANCE",
                state="READY",
                advisory="DRIVE",
                ready_for_manual_proceed=False,
                autonomous_edge_ready=False,
                reason_codes=[],
                requirements={},
                updated_at_ns=BASE_NS,
            )

    def test_common_snapshot_rejects_bad_reason_code(self) -> None:
        with self.assertRaises(BehaviorContractError):
            make_advisory_snapshot(
                behavior="FAULT",
                state="FAULT",
                advisory="FAULT",
                ready_for_manual_proceed=False,
                autonomous_edge_ready=False,
                reason_codes=["raw command"],
                requirements={},
                updated_at_ns=BASE_NS,
            )

    def test_common_snapshot_rejects_timestamp_overflow(self) -> None:
        with self.assertRaises(BehaviorContractError):
            make_advisory_snapshot(
                behavior="FAULT",
                state="FAULT",
                advisory="FAULT",
                ready_for_manual_proceed=False,
                autonomous_edge_ready=False,
                reason_codes=[],
                requirements={},
                updated_at_ns=1 << 64,
            )

    def test_common_snapshot_never_contains_control_fields(self) -> None:
        value = make_advisory_snapshot(
            behavior="FAULT",
            state="FAULT",
            advisory="FAULT",
            ready_for_manual_proceed=False,
            autonomous_edge_ready=False,
            reason_codes=[],
            requirements={},
            updated_at_ns=BASE_NS,
        )
        self.assertFalse(set(value) & FORBIDDEN_KEYS)


class CrosswalkTransitionTests(unittest.TestCase):
    def evaluate(
        self,
        advisor: CrosswalkAdvisor | None = None,
        snapshot: dict | None = None,
        **kwargs,
    ) -> dict:
        return (advisor or CrosswalkAdvisor()).evaluate(
            segment=crosswalk_segment(),
            perception=snapshot or perception(),
            now_ns=kwargs.pop("now_ns", BASE_NS),
            **kwargs,
        )

    def test_idle_on_non_crosswalk(self) -> None:
        value = CrosswalkAdvisor().evaluate(
            segment=normal_segment(), perception=perception(), now_ns=BASE_NS
        )
        self.assertEqual(value["state"], "IDLE")

    def test_approach_when_entry_is_far(self) -> None:
        self.assertEqual(self.evaluate(distance_to_entry_m=3.0)["state"], "APPROACH")

    def test_stop_line_without_signal_evidence(self) -> None:
        snap = perception()
        snap["traffic"] = []
        self.assertEqual(
            self.evaluate(snapshot=snap, distance_to_entry_m=0.2)["state"], "STOP_LINE"
        )

    def test_red_waits_signal(self) -> None:
        value = self.evaluate(snapshot=perception(signal="RED"))
        self.assertEqual(
            (value["state"], value["reason_codes"]), ("WAIT_SIGNAL", ["TRAFFIC_RED"])
        )

    def test_one_green_frame_is_not_ready(self) -> None:
        self.assertEqual(
            self.evaluate(snapshot=perception(consecutive_frames=1))["state"],
            "WAIT_SIGNAL",
        )

    def test_unknown_signal_is_not_ready(self) -> None:
        self.assertEqual(
            self.evaluate(snapshot=perception(signal="UNKNOWN"))["state"], "WAIT_SIGNAL"
        )

    def test_occupied_person_waits(self) -> None:
        self.assertEqual(
            self.evaluate(snapshot=perception(occupancy="OCCUPIED"))["state"],
            "WAIT_PERSON",
        )

    def test_unknown_person_waits(self) -> None:
        self.assertEqual(
            self.evaluate(snapshot=perception(occupancy="UNKNOWN"))["state"],
            "WAIT_PERSON",
        )

    def test_lateral_error_aligns(self) -> None:
        self.assertEqual(
            self.evaluate(snapshot=perception(lateral=0.4))["state"], "ALIGN"
        )

    def test_heading_error_aligns(self) -> None:
        self.assertEqual(
            self.evaluate(snapshot=perception(heading=0.4))["state"], "ALIGN"
        )

    def test_ready_recommends_proceed(self) -> None:
        value = self.evaluate()
        self.assertEqual(
            (value["state"], value["advisory"]), ("READY", "PROCEED_RECOMMENDED")
        )
        self.assertTrue(value["autonomous_edge_ready"])

    def test_crossing_observes(self) -> None:
        self.assertEqual(self.evaluate(crossing=True)["state"], "CROSSING_OBSERVE")

    def test_exit_confirmation_completes(self) -> None:
        self.assertEqual(self.evaluate(exit_confirmed=True)["state"], "EXIT_CONFIRMED")

    def test_route_deviation_recommends_replan(self) -> None:
        self.assertEqual(
            self.evaluate(route_deviation_m=2.0)["advisory"], "REPLAN_RECOMMENDED"
        )

    def test_three_feet_outside_holds(self) -> None:
        value = self.evaluate(feet_outside_count=3)
        self.assertIn("FOOT_BOUNDARY_VIOLATION", value["reason_codes"])

    def test_two_feet_outside_does_not_trigger_violation(self) -> None:
        self.assertEqual(self.evaluate(feet_outside_count=2)["state"], "READY")

    def test_missing_feet_input_is_unknown_but_not_fabricated(self) -> None:
        self.assertIsNone(self.evaluate()["requirements"]["feet_boundary"])

    def test_stale_after_ready_holds(self) -> None:
        advisor = CrosswalkAdvisor()
        self.evaluate(advisor, perception(sequence=1))
        stale = perception(
            sequence=2, observed_at_ns=BASE_NS, now_ns=BASE_NS + 1_000_000_001
        )
        self.assertEqual(
            self.evaluate(advisor, stale, now_ns=BASE_NS + 1_000_000_001)["state"],
            "HOLD",
        )

    def test_recovery_requires_new_sequence(self) -> None:
        advisor = CrosswalkAdvisor()
        self.evaluate(advisor, perception(sequence=1))
        stale = perception(
            sequence=2, observed_at_ns=BASE_NS, now_ns=BASE_NS + 1_000_000_001
        )
        self.evaluate(advisor, stale, now_ns=BASE_NS + 1_000_000_001)
        same = perception(
            sequence=2,
            observed_at_ns=BASE_NS + 2_000_000_000,
            now_ns=BASE_NS + 2_000_000_000,
        )
        self.assertIn(
            "NEW_EVIDENCE_REQUIRED",
            self.evaluate(advisor, same, now_ns=BASE_NS + 2_000_000_000)[
                "reason_codes"
            ],
        )

    def test_new_sequence_recovers_from_stale(self) -> None:
        advisor = CrosswalkAdvisor()
        self.evaluate(advisor, perception(sequence=1))
        stale = perception(
            sequence=2, observed_at_ns=BASE_NS, now_ns=BASE_NS + 1_000_000_001
        )
        self.evaluate(advisor, stale, now_ns=BASE_NS + 1_000_000_001)
        fresh = perception(
            sequence=3,
            observed_at_ns=BASE_NS + 2_000_000_000,
            now_ns=BASE_NS + 2_000_000_000,
        )
        self.assertEqual(
            self.evaluate(advisor, fresh, now_ns=BASE_NS + 2_000_000_000)["state"],
            "READY",
        )

    def test_sequence_rollback_faults(self) -> None:
        advisor = CrosswalkAdvisor()
        self.evaluate(advisor, perception(sequence=2))
        self.assertIn(
            "SEQUENCE_ROLLBACK",
            self.evaluate(advisor, perception(sequence=1))["reason_codes"],
        )

    def test_revision_change_faults(self) -> None:
        self.assertIn(
            "REVISION_CHANGED", self.evaluate(revisions_current=False)["reason_codes"]
        )

    def test_stale_pose_faults(self) -> None:
        self.assertIn("POSE_STALE", self.evaluate(pose_fresh=False)["reason_codes"])

    def test_alignment_loss_after_ready_holds_until_new_evidence(self) -> None:
        advisor = CrosswalkAdvisor()
        self.evaluate(advisor, perception(sequence=1))
        value = self.evaluate(advisor, perception(sequence=2, lateral=0.4))
        self.assertIn("ALIGNMENT_LOST_AFTER_READY", value["reason_codes"])


class DockingTransitionTests(unittest.TestCase):
    def evaluate(
        self,
        advisor: DockingAdvisor | None = None,
        snapshot: dict | None = None,
        **kwargs,
    ) -> dict:
        return (advisor or DockingAdvisor()).evaluate(
            segment=docking_segment(),
            perception=snapshot or perception(),
            now_ns=kwargs.pop("now_ns", BASE_NS),
            expected_venue_id=kwargs.pop("expected_venue_id", "COEX"),
            **kwargs,
        )

    def test_idle_on_non_docking_segment(self) -> None:
        value = DockingAdvisor().evaluate(
            segment=normal_segment(),
            perception=perception(),
            now_ns=BASE_NS,
            expected_venue_id="COEX",
        )
        self.assertEqual(value["state"], "IDLE")

    def test_coarse_approach_when_far(self) -> None:
        self.assertEqual(
            self.evaluate(distance_to_dock_m=2.0)["state"], "COARSE_APPROACH"
        )

    def test_missing_marker_searches(self) -> None:
        self.assertEqual(
            self.evaluate(snapshot=perception(aruco=[]))["state"], "SEARCH_MARKER"
        )

    def test_marker_without_target_tracks(self) -> None:
        aruco = [
            {
                "venue_id": "COEX",
                "docking_ready": False,
                "marker_ids": [10],
                "confidence": 0.9,
            }
        ]
        self.assertEqual(
            self.evaluate(snapshot=perception(aruco=aruco))["state"], "TRACK_MARKER"
        )

    def test_low_confidence_tracks(self) -> None:
        aruco = copy.deepcopy(perception()["aruco"])
        aruco[0]["confidence"] = 0.5
        self.assertEqual(
            self.evaluate(snapshot=perception(aruco=aruco))["state"], "TRACK_MARKER"
        )

    def test_alignment_error_aligns(self) -> None:
        aruco = copy.deepcopy(perception()["aruco"])
        aruco[0]["target_pose"]["y"] = 0.3
        self.assertEqual(
            self.evaluate(snapshot=perception(aruco=aruco))["state"], "ALIGN"
        )

    def test_ready_reports_docking_ready(self) -> None:
        value = self.evaluate()
        self.assertEqual(
            (value["state"], value["advisory"]), ("READY", "DOCKING_READY")
        )

    def test_contact_is_only_a_docked_candidate(self) -> None:
        value = self.evaluate(dock_contact_confirmed=True)
        self.assertEqual(value["state"], "DOCKED_CANDIDATE")
        self.assertFalse(value["autonomous_edge_ready"])

    def test_wrong_venue_faults(self) -> None:
        aruco = copy.deepcopy(perception()["aruco"])
        aruco[0]["venue_id"] = "HANSOT"
        self.assertIn(
            "VENUE_MISMATCH",
            self.evaluate(snapshot=perception(aruco=aruco))["reason_codes"],
        )

    def test_wrong_zone_faults(self) -> None:
        aruco = copy.deepcopy(perception()["aruco"])
        aruco[0]["zone_id"] = "ZONE_2"
        self.assertIn(
            "ZONE_MISMATCH",
            self.evaluate(snapshot=perception(aruco=aruco), expected_zone_id="ZONE_1")[
                "reason_codes"
            ],
        )

    def test_target_loss_after_acquire_is_lost(self) -> None:
        advisor = DockingAdvisor()
        self.evaluate(advisor, perception(sequence=1))
        self.assertEqual(
            self.evaluate(advisor, perception(sequence=2, aruco=[]))["state"], "LOST"
        )

    def test_stale_marker_is_lost(self) -> None:
        stale = perception(observed_at_ns=BASE_NS, now_ns=BASE_NS + 1_000_000_001)
        self.assertEqual(
            self.evaluate(snapshot=stale, now_ns=BASE_NS + 1_000_000_001)["state"],
            "LOST",
        )

    def test_sequence_rollback_faults(self) -> None:
        advisor = DockingAdvisor()
        self.evaluate(advisor, perception(sequence=2))
        self.assertIn(
            "SEQUENCE_ROLLBACK",
            self.evaluate(advisor, perception(sequence=1))["reason_codes"],
        )

    def test_target_jump_faults(self) -> None:
        advisor = DockingAdvisor()
        self.evaluate(advisor, perception(sequence=1))
        aruco = copy.deepcopy(perception()["aruco"])
        aruco[0]["target_pose"]["x"] = 1.0
        value = self.evaluate(advisor, perception(sequence=2, aruco=aruco))
        self.assertIn("TARGET_JUMP", value["reason_codes"])

    def test_new_evidence_required_after_fault(self) -> None:
        advisor = DockingAdvisor()
        self.evaluate(advisor, perception(sequence=1), revisions_current=False)
        value = self.evaluate(advisor, perception(sequence=1))
        self.assertIn("NEW_EVIDENCE_REQUIRED", value["reason_codes"])


class UnderpassTransitionTests(unittest.TestCase):
    def evaluate(
        self,
        advisor: UnderpassAdvisor | None = None,
        snapshot: dict | None = None,
        **kwargs,
    ) -> dict:
        return (advisor or UnderpassAdvisor()).evaluate(
            segment=underpass_segment(),
            perception=snapshot or perception(),
            now_ns=kwargs.pop("now_ns", BASE_NS),
            **kwargs,
        )

    def test_idle_on_normal_segment(self) -> None:
        value = UnderpassAdvisor().evaluate(
            segment=normal_segment(), perception=perception(), now_ns=BASE_NS
        )
        self.assertEqual(value["state"], "IDLE")

    def test_blocked_observation_holds(self) -> None:
        value = self.evaluate(
            snapshot=perception(underpass_blocked=True), service_robot_clear=True
        )
        self.assertEqual(value["state"], "BLOCKED")

    def test_occupied_person_blocks(self) -> None:
        value = self.evaluate(
            snapshot=perception(occupancy="OCCUPIED"), service_robot_clear=True
        )
        self.assertIn("PERSON_OCCUPIED", value["reason_codes"])

    def test_service_robot_blocks(self) -> None:
        self.assertIn(
            "SERVICE_ROBOT_BLOCKED",
            self.evaluate(service_robot_clear=False)["reason_codes"],
        )

    def test_unknown_underpass_waits(self) -> None:
        self.assertEqual(
            self.evaluate(
                snapshot=perception(underpass_blocked=None), service_robot_clear=True
            )["state"],
            "WAIT_CLEAR",
        )

    def test_unknown_service_robot_waits(self) -> None:
        self.assertEqual(self.evaluate(service_robot_clear=None)["state"], "WAIT_CLEAR")

    def test_approach_when_far(self) -> None:
        self.assertEqual(
            self.evaluate(service_robot_clear=True, distance_to_entry_m=2.0)["state"],
            "APPROACH",
        )

    def test_operator_confirmation_is_required(self) -> None:
        value = self.evaluate(service_robot_clear=True)
        self.assertIn("OPERATOR_CONFIRMATION_REQUIRED", value["reason_codes"])

    def test_ready_is_manual_only(self) -> None:
        advisor = UnderpassAdvisor()
        value = self.evaluate(
            advisor,
            service_robot_clear=True,
            operator_confirmed=True,
            confirmation_epoch=advisor.confirmation_epoch,
        )
        self.assertEqual(value["state"], "READY")
        self.assertFalse(value["autonomous_edge_ready"])

    def test_traversing_remains_observational(self) -> None:
        advisor = UnderpassAdvisor()
        value = self.evaluate(
            advisor,
            service_robot_clear=True,
            operator_confirmed=True,
            traversing=True,
            confirmation_epoch=advisor.confirmation_epoch,
        )
        self.assertEqual(value["state"], "TRAVERSING_OBSERVE")

    def test_exit_completes(self) -> None:
        advisor = UnderpassAdvisor()
        value = self.evaluate(
            advisor,
            service_robot_clear=True,
            operator_confirmed=True,
            exit_observed=True,
            confirmation_epoch=advisor.confirmation_epoch,
        )
        self.assertEqual(value["state"], "EXIT")

    def test_stale_perception_invalidates_confirmation(self) -> None:
        advisor = UnderpassAdvisor()
        epoch = advisor.confirmation_epoch
        stale = perception(observed_at_ns=BASE_NS, now_ns=BASE_NS + 1_000_000_001)
        self.evaluate(
            advisor,
            stale,
            now_ns=BASE_NS + 1_000_000_001,
            service_robot_clear=True,
            operator_confirmed=True,
            confirmation_epoch=epoch,
        )
        self.assertGreater(advisor.confirmation_epoch, epoch)

    def test_sequence_rollback_faults(self) -> None:
        advisor = UnderpassAdvisor()
        self.evaluate(advisor, perception(sequence=2), service_robot_clear=True)
        self.assertIn(
            "SEQUENCE_ROLLBACK",
            self.evaluate(advisor, perception(sequence=1), service_robot_clear=True)[
                "reason_codes"
            ],
        )

    def test_rollback_recovery_requires_new_evidence_and_confirmation(self) -> None:
        advisor = UnderpassAdvisor()
        epoch = advisor.confirmation_epoch
        self.evaluate(
            advisor,
            perception(sequence=2),
            service_robot_clear=True,
            operator_confirmed=True,
            confirmation_epoch=epoch,
        )
        self.evaluate(
            advisor,
            perception(sequence=1),
            service_robot_clear=True,
            operator_confirmed=True,
            confirmation_epoch=epoch,
        )
        held = self.evaluate(
            advisor,
            perception(sequence=2),
            service_robot_clear=True,
            operator_confirmed=True,
            confirmation_epoch=epoch,
        )
        self.assertIn("NEW_EVIDENCE_REQUIRED", held["reason_codes"])
        recovered = self.evaluate(
            advisor,
            perception(sequence=3),
            service_robot_clear=True,
            operator_confirmed=True,
            confirmation_epoch=advisor.confirmation_epoch,
        )
        self.assertEqual(recovered["state"], "READY")

    def test_revision_change_faults(self) -> None:
        self.assertIn(
            "REVISION_CHANGED", self.evaluate(revisions_current=False)["reason_codes"]
        )


class DeliveryTransitionTests(unittest.TestCase):
    def test_initial_state_is_order_ready(self) -> None:
        self.assertEqual(DeliveryWorkflow(order()).snapshot()["state"], "ORDER_READY")

    def test_start_routes_to_first_pickup(self) -> None:
        self.assertEqual(
            DeliveryWorkflow(order()).transition("START", now_ns=1)["state"],
            "EN_ROUTE_PICKUP",
        )

    def test_wrong_first_venue_fails(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        self.assertIn(
            "PICKUP_SEQUENCE_MISMATCH",
            flow.transition("ARRIVE_PICKUP", now_ns=2, payload={"venue_id": "EDIYA"})[
                "reason_codes"
            ],
        )

    def test_arrival_requires_pickup_dock(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        self.assertEqual(
            flow.transition("ARRIVE_PICKUP", now_ns=2, payload={"venue_id": "HANSOT"})[
                "state"
            ],
            "PICKUP_DOCK_REQUIRED",
        )

    def test_docked_requires_operator_confirmation(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        flow.transition("ARRIVE_PICKUP", now_ns=2, payload={"venue_id": "HANSOT"})
        self.assertEqual(
            flow.transition("PICKUP_DOCKED", now_ns=3)["advisory"],
            "PICKUP_CONFIRMATION_REQUIRED",
        )

    def test_pickup_confirmation_updates_cargo(self) -> None:
        flow = self._first_confirmation()
        self.assertEqual(flow.cargo_count, 2)

    def test_duplicate_pickup_does_not_double_cargo(self) -> None:
        flow = self._first_confirmation()
        before = flow.cargo_count
        value = flow.transition(
            "CONFIRM_PICKUP", now_ns=5, payload={"venue_id": "HANSOT"}
        )
        self.assertEqual(flow.cargo_count, before)
        self.assertIn("DUPLICATE_PICKUP_CONFIRMATION", value["reason_codes"])

    def test_departure_routes_to_next_pickup(self) -> None:
        flow = self._first_confirmation()
        self.assertEqual(
            flow.transition("DEPART_PICKUP", now_ns=5)["state"], "EN_ROUTE_PICKUP"
        )

    def test_dropoff_before_all_pickups_fails(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        self.assertIn(
            "DROPOFF_BEFORE_PICKUP",
            flow.transition("ARRIVE_DESTINATION", now_ns=2)["reason_codes"],
        )

    def test_full_flow_reaches_destination(self) -> None:
        flow = self._all_pickups()
        self.assertEqual(flow.state, "EN_ROUTE_DESTINATION")

    def test_destination_arrival_requires_dock(self) -> None:
        flow = self._all_pickups()
        self.assertEqual(
            flow.transition(
                "ARRIVE_DESTINATION", now_ns=10, payload={"destination_id": "COEX"}
            )["state"],
            "DROPOFF_DOCK_REQUIRED",
        )

    def test_dropoff_docked_requires_confirmation(self) -> None:
        flow = self._all_pickups()
        flow.transition("ARRIVE_DESTINATION", now_ns=10)
        self.assertEqual(
            flow.transition("DROPOFF_DOCKED", now_ns=11)["advisory"],
            "DROPOFF_CONFIRMATION_REQUIRED",
        )

    def test_confirmed_dropoff_completes_and_empties_cargo(self) -> None:
        flow = self._all_pickups()
        flow.transition("ARRIVE_DESTINATION", now_ns=10)
        flow.transition("DROPOFF_DOCKED", now_ns=11)
        value = flow.transition(
            "CONFIRM_DROPOFF", now_ns=12, payload={"destination_id": "COEX"}
        )
        self.assertEqual((value["state"], flow.cargo_count), ("ORDER_COMPLETE", 0))

    def test_restart_pauses_without_resume(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        self.assertEqual(flow.transition("RESTART", now_ns=2)["state"], "PAUSED")

    def test_resume_requires_fresh_evidence_and_confirmation(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        flow.transition("RESTART", now_ns=2)
        self.assertEqual(
            flow.transition("RESUME", now_ns=3, payload={"fresh_evidence": True})[
                "state"
            ],
            "PAUSED",
        )

    def test_explicit_resume_restores_prior_state(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        flow.transition("RESTART", now_ns=2)
        value = flow.transition(
            "RESUME",
            now_ns=3,
            payload={"fresh_evidence": True, "operator_confirmed": True},
        )
        self.assertEqual(value["state"], "EN_ROUTE_PICKUP")

    def test_time_rollback_fails(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=2)
        self.assertIn(
            "TIME_ROLLBACK", flow.transition("PAUSE", now_ns=1)["reason_codes"]
        )

    def test_capacity_exceeded_order_is_rejected(self) -> None:
        invalid = order()
        invalid["total_quantity"] = 6
        with self.assertRaises(BehaviorContractError):
            DeliveryWorkflow(invalid)

    def test_audit_is_bounded(self) -> None:
        flow = DeliveryWorkflow(order())
        for index in range(40):
            flow.transition("PAUSE", now_ns=index + 1)
        self.assertLessEqual(len(flow.audit()), 32)

    @staticmethod
    def _first_confirmation() -> DeliveryWorkflow:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        flow.transition("ARRIVE_PICKUP", now_ns=2, payload={"venue_id": "HANSOT"})
        flow.transition("PICKUP_DOCKED", now_ns=3)
        flow.transition("CONFIRM_PICKUP", now_ns=4, payload={"venue_id": "HANSOT"})
        return flow

    @classmethod
    def _all_pickups(cls) -> DeliveryWorkflow:
        flow = cls._first_confirmation()
        flow.transition("DEPART_PICKUP", now_ns=5)
        flow.transition("ARRIVE_PICKUP", now_ns=6, payload={"venue_id": "EDIYA"})
        flow.transition("PICKUP_DOCKED", now_ns=7)
        flow.transition("CONFIRM_PICKUP", now_ns=8, payload={"venue_id": "EDIYA"})
        flow.transition("DEPART_PICKUP", now_ns=9)
        return flow


class CompositeBehaviorTests(unittest.TestCase):
    def test_all_gp1_scenarios_match_advisory_golden(self) -> None:
        golden_path = (
            Path(__file__).parent
            / "fixtures"
            / "route_planner"
            / "advisory-golden-v1.json"
        )
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        self.assertEqual(golden["schema_version"], 1)
        expected = golden["scenarios"]
        self.assertEqual(
            set(expected), {path.stem for path in SCENARIO_ROOT.glob("*.json")}
        )
        for scenario_id, projection in expected.items():
            result = replay_scenario_file(SCENARIO_ROOT / f"{scenario_id}.json")
            actual = result["advisory_behavior"]
            self.assertEqual(
                {key: actual[key] for key in ("behavior", "state", "advisory")},
                projection,
                scenario_id,
            )
            self.assertEqual(result["side_effect_count"], 0, scenario_id)
            self.assertTrue(
                all(value == 0 for value in result["side_effect_counters"].values()),
                scenario_id,
            )

    def test_behavior_package_has_no_runtime_control_calls(self) -> None:
        forbidden = {
            "ControlManager",
            "NavigationCoordinator",
            "NavigationRosGateway",
            "MissionCoordinator",
            "cmd_vel",
            "send_goal",
            "start_mission",
        }
        behavior_root = Path(__file__).parents[1] / "robot_dashboard" / "route_planner"
        for path in [
            *sorted((behavior_root / "behaviors").glob("*.py")),
            behavior_root / "replay.py",
        ]:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            symbols = {
                node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
            } | {
                node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
            }
            self.assertFalse(symbols & forbidden, path.name)

    def route(self) -> dict:
        return {"stops": [{"node_id": "COEX_DOCK", "venue_id": "COEX"}]}

    def test_server_restart_has_highest_fault_priority(self) -> None:
        value = AdvisoryBehaviorCoordinator().evaluate(
            route=self.route(),
            guidance=guidance(docking_segment()),
            perception=perception(),
            now_ns=BASE_NS,
            server_restarted=True,
        )
        self.assertEqual(value["behavior"], "FAULT")

    def test_revision_change_faults_before_segment_behavior(self) -> None:
        value = AdvisoryBehaviorCoordinator().evaluate(
            route=self.route(),
            guidance=guidance(crosswalk_segment()),
            perception=perception(),
            now_ns=BASE_NS,
            revisions_current=False,
        )
        self.assertIn("REVISION_CHANGED", value["reason_codes"])

    def test_stale_pose_faults(self) -> None:
        value = AdvisoryBehaviorCoordinator().evaluate(
            route=self.route(),
            guidance=guidance(normal_segment()),
            perception=perception(),
            now_ns=BASE_NS,
            pose_fresh=False,
        )
        self.assertIn("POSE_STALE", value["reason_codes"])

    def test_missing_segment_faults(self) -> None:
        value = AdvisoryBehaviorCoordinator().evaluate(
            route=self.route(), guidance={}, perception=perception(), now_ns=BASE_NS
        )
        self.assertIn("CURRENT_SEGMENT_UNAVAILABLE", value["reason_codes"])

    def test_global_fault_recovery_requires_new_perception_sequence(self) -> None:
        coordinator = AdvisoryBehaviorCoordinator()
        value = coordinator.evaluate(
            route=self.route(),
            guidance=guidance(normal_segment()),
            perception=perception(sequence=4),
            now_ns=BASE_NS,
            revisions_current=False,
        )
        self.assertIn("REVISION_CHANGED", value["reason_codes"])
        held = coordinator.evaluate(
            route=self.route(),
            guidance=guidance(normal_segment()),
            perception=perception(sequence=4),
            now_ns=BASE_NS,
        )
        self.assertIn("NEW_EVIDENCE_REQUIRED", held["reason_codes"])
        recovered = coordinator.evaluate(
            route=self.route(),
            guidance=guidance(normal_segment()),
            perception=perception(sequence=5),
            now_ns=BASE_NS,
        )
        self.assertEqual(recovered["state"], "READY")

    def test_docking_selected_before_delivery(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        flow.transition("ARRIVE_PICKUP", now_ns=2, payload={"venue_id": "HANSOT"})
        flow.transition("PICKUP_DOCKED", now_ns=3)
        value = AdvisoryBehaviorCoordinator(delivery=flow).evaluate(
            route=self.route(),
            guidance=guidance(docking_segment()),
            perception=perception(),
            now_ns=BASE_NS,
        )
        self.assertEqual(value["behavior"], "DOCKING")

    def test_crosswalk_selected(self) -> None:
        value = AdvisoryBehaviorCoordinator().evaluate(
            route=self.route(),
            guidance=guidance(crosswalk_segment()),
            perception=perception(signal="RED"),
            now_ns=BASE_NS,
        )
        self.assertEqual(value["behavior"], "CROSSWALK")

    def test_underpass_selected(self) -> None:
        value = AdvisoryBehaviorCoordinator().evaluate(
            route=self.route(),
            guidance=guidance(underpass_segment()),
            perception=perception(),
            now_ns=BASE_NS,
        )
        self.assertEqual(value["behavior"], "UNDERPASS")

    def test_delivery_confirmation_selected_on_normal_segment(self) -> None:
        flow = DeliveryWorkflow(order())
        flow.transition("START", now_ns=1)
        flow.transition("ARRIVE_PICKUP", now_ns=2, payload={"venue_id": "HANSOT"})
        flow.transition("PICKUP_DOCKED", now_ns=3)
        value = AdvisoryBehaviorCoordinator(delivery=flow).evaluate(
            route=self.route(),
            guidance=guidance(normal_segment()),
            perception=perception(),
            now_ns=BASE_NS,
        )
        self.assertEqual(value["behavior"], "DELIVERY")

    def test_normal_guidance_is_advisory_only(self) -> None:
        value = AdvisoryBehaviorCoordinator().evaluate(
            route=self.route(),
            guidance=guidance(normal_segment()),
            perception=perception(),
            now_ns=BASE_NS,
        )
        self.assertEqual(
            (value["behavior"], value["advisory"]),
            ("NORMAL_GUIDANCE", "PROCEED_RECOMMENDED"),
        )
        self.assertFalse(set(value) & FORBIDDEN_KEYS)

    def test_stale_normal_guidance_holds(self) -> None:
        stale = perception(observed_at_ns=BASE_NS, now_ns=BASE_NS + 1_000_000_001)
        value = AdvisoryBehaviorCoordinator().evaluate(
            route=self.route(),
            guidance=guidance(normal_segment()),
            perception=stale,
            now_ns=BASE_NS + 1_000_000_001,
        )
        self.assertEqual(value["advisory"], "HOLD")

    def test_gp1_replay_exposes_one_deterministic_behavior_snapshot(self) -> None:
        path = SCENARIO_ROOT / "traffic-red-to-green.json"
        first, second = replay_scenario_file(path), replay_scenario_file(path)
        self.assertEqual(first["advisory_behavior"], second["advisory_behavior"])
        self.assertEqual(first["advisory_behavior"]["state"], "READY")
        self.assertEqual(first["side_effect_count"], 0)

    def test_suite_contains_at_least_forty_explicit_transition_tests(self) -> None:
        classes = (
            CrosswalkTransitionTests,
            DockingTransitionTests,
            UnderpassTransitionTests,
            DeliveryTransitionTests,
            CompositeBehaviorTests,
        )
        count = sum(
            len(
                [
                    name
                    for name, _ in inspect.getmembers(cls, inspect.isfunction)
                    if name.startswith("test_")
                ]
            )
            for cls in classes
        )
        self.assertGreaterEqual(count, 40)


if __name__ == "__main__":
    unittest.main()
