"""Pure single-action decisions; the existing coordinator remains the run owner."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ActionState:
    phase: str = "NEW"
    reason: str = "EXPLICIT_START_REQUIRED"
    started_s: float = 0.0
    dwell_start: float | None = None
    last_valid_s: float | None = None
    dwell_source_start: tuple[tuple[str, int], ...] = ()
    departed: bool = False
    attempted_steps: tuple[str, ...] = ()
    traversed_segments: tuple[str, ...] = ()
    full_body_crossed: bool = False


@dataclass(frozen=True)
class Decision:
    state: ActionState
    effects: tuple[str, ...] = ()


TERMINAL = {"SUCCEEDED", "FAILED", "INTERRUPTED", "READY_TO_MOVE"}


def decide(state, action, frame, *, now, hold_ack, synthetic=False):
    """No timers, goals, hardware, task creation, or IO here."""
    def result(phase=None, reason=None, effects=(), **changes):
        return Decision(replace(state, phase=phase or state.phase,
                                reason=reason or state.reason, **changes), effects)

    def stop(reason, phase="FAILED"):
        return result(phase, reason, ("HOLD", "CANCEL"), dwell_start=None, last_valid_s=None)

    if state.phase in TERMINAL or state.phase == "NEW":
        return Decision(state)
    if frame is None or not frame.fresh("safety"):
        return stop("SAFETY_OBSERVATION_STALE")
    e, extra = frame.evidence, frame.extras
    if extra.estop or extra.collision:
        return stop("ESTOP" if extra.estop else "COLLISION")
    if now - state.started_s >= action.timeout_seconds:
        return stop("SIGNAL_WAIT_TIMEOUT" if state.phase in {"HOLD_ACK", "HOLD_SIGNAL"}
                    and action.type == "TRAFFIC_STOP_AND_GO" else "ACTION_TIMEOUT")
    if frame.fresh("coverage"):
        state = replace(state, attempted_steps=extra.attempted_steps,
                        traversed_segments=extra.traversed_segments)
    if state.phase == "APPROACH":
        if not frame.fresh("navigation", "pose", "path") or e.pose is None:
            return stop("NAVIGATION_OBSERVATION_STALE")
        if e.goal_state == "FAILED" or e.obstacle_state == "FAILED":
            return stop("NAVIGATION_PROGRESS_FAILED")
        if e.goal_state == "CANCELED":
            if not e.cancel_ack:
                return stop("CANCEL_ACK_REQUIRED")
            return stop("NAVIGATION_CANCELED")
        if e.obstacle_state == "SENSOR_UNAVAILABLE":
            return stop("NAVIGATION_SENSOR_STALE")
        if e.goal_state == "SUCCEEDED":
            if action.type == "NAVIGATE_ADAPTIVE":
                return result("SUCCEEDED", "NAVIGATION_SUCCEEDED", ("HOLD",))
            if action.type in {"TRAFFIC_STOP_AND_GO", "PARK_SIT_HOLD"}:
                return result("HOLD_ACK", "APPROACH_TERMINAL", ("HOLD",))
            if action.type == "TRAVERSE_TERRAIN":
                return result("TERRAIN", "TERRAIN_VALIDATION_REQUIRED", ("TERRAIN",))
            if action.type == "FINISH_CROSSING":
                return result("FINISH", "FULL_BODY_CROSSING_REQUIRED", ("HOLD",))
        # A stop-zone observation requests cancellation; it does not fake arrival.
        if (action.type == "TRAFFIC_STOP_AND_GO" and frame.fresh("feet")
                and e.zone_id == action.zone_id
                and e.front_left_status == e.front_right_status == "INSIDE"
                and e.feet_evidence_kind in (("SIM_GT", "KINEMATIC", "VISUAL") if synthetic
                                             else ("KINEMATIC", "VISUAL"))):
            return result("WAIT_CANCEL", "APPROACH_CANCEL_PENDING", ("CANCEL",))
        if e.obstacle_state == "WAIT_OBSTACLE" or not e.path_clear:
            return result(reason="WAIT_OBSTACLE", effects=("HOLD",))
        if e.obstacle_state == "REPLANNING":
            return result(reason="REPLANNING")
        return result(reason="NAVIGATION_ACTIVE", effects=("RELEASE_TRACKING",))
    if state.phase == "WAIT_CANCEL":
        if not frame.fresh("navigation"):
            return stop("CANCEL_RESULT_STALE")
        if e.goal_state == "FAILED":
            return stop("NAVIGATION_PROGRESS_FAILED")
        if e.goal_state == "SUCCEEDED" or (e.goal_state == "CANCELED" and e.cancel_ack):
            return result("HOLD_ACK", "APPROACH_TERMINAL_ACK", ("HOLD",))
        return result(reason="APPROACH_CANCEL_PENDING")
    if state.phase == "HOLD_ACK":
        if not hold_ack:
            return result(reason="HOLD_ACK_REQUIRED")
        if action.type == "PARK_SIT_HOLD":
            return result("PARK_HOLD", "POSTURE_EVIDENCE_REQUIRED", ("SIT",))
        return result("HOLD_SIGNAL", "HOLD_SIGNAL")
    if state.phase in {"HOLD_SIGNAL", "PARK_HOLD"}:
        needed = ("feet", "motion") if state.phase == "HOLD_SIGNAL" else ("body", "posture", "motion")
        physical = frame.fresh(*needed) and hold_ack and e.zone_id == action.zone_id and e.body_motion_status == "STOPPED"
        if state.phase == "HOLD_SIGNAL":
            physical = (physical and e.front_left_status == e.front_right_status == "INSIDE"
                        and e.feet_evidence_kind in (("SIM_GT", "KINEMATIC", "VISUAL") if synthetic
                                                   else ("KINEMATIC", "VISUAL")))
            duration = action.dwell_seconds
            invalid = "TWO_FEET_AND_PHYSICAL_STOP_REQUIRED"
        else:
            physical = (physical and e.full_body_inside and e.posture == "SIT"
                        and extra.posture_verified and bool(extra.validation_reference))
            duration = action.sit_seconds
            invalid = "FULL_CONTAINMENT_VERIFIED_SIT_AND_STOP_REQUIRED"
        if not physical:
            return result(reason=invalid, dwell_start=None, last_valid_s=None)
        sample_time = min(frame.components[name].receipt_s for name in needed)
        source_times = {name: int(frame.components[name].stamp.source_stamp_ns) for name in needed}
        start = state.dwell_start
        if start is None or state.last_valid_s is None or sample_time - state.last_valid_s > frame.policy.continuity_gap_s:
            start = sample_time
            source_start = source_times
        else:
            source_start = dict(state.dwell_source_start)
        # Compare deltas within each bound source clock, never across hosts.
        # Bursts of old frames/new polling envelopes cannot manufacture 2 s.
        source_supported = min((source_times[name] - source_start.get(name, source_times[name])) / 1e9
                               for name in needed)
        updated = replace(state, dwell_start=start, last_valid_s=sample_time,
                          dwell_source_start=tuple(source_start.items()))
        if min(sample_time - start, source_supported) < duration:
            return Decision(replace(updated, reason="DWELL_IN_PROGRESS"))
        if state.phase == "PARK_HOLD":
            return Decision(replace(updated, phase="SUCCEEDED", reason="PARK_EVIDENCE_COMPLETE"))
        eligible = (frame.fresh("signal", "pose", "path") and e.pose is not None
                    and e.signal_id == action.signal_id and e.crossing_id == action.crossing_id
                    and e.stable_state == "GREEN" and e.raw_state == "GREEN"
                    and not e.quality_flags and e.path_clear
                    and e.obstacle_state in {"FOLLOWING", "GOAL_REACHED"})
        if not eligible:
            return Decision(replace(updated, reason="FRESH_ASSOCIATED_GREEN_POSE_PATH_REQUIRED"))
        return Decision(replace(updated, phase="EXIT_PENDING", reason="NEW_EXIT_GENERATION_REQUIRED"),
                        ("EXIT",))
    if state.phase in {"EXIT_PENDING", "DEPARTING"}:
        if not frame.fresh("navigation", "pose", "path", "motion") or e.pose is None:
            return stop("EXIT_OBSERVATION_STALE")
        if e.goal_state in {"FAILED", "CANCELED"}:
            return stop("EXIT_GOAL_" + e.goal_state)
        if not e.path_clear or e.obstacle_state in {"WAIT_OBSTACLE", "SENSOR_UNAVAILABLE", "FAILED"}:
            return stop("EXIT_PATH_BLOCKED")
        if not state.departed:
            if (not frame.fresh("signal") or e.signal_id != action.signal_id
                    or e.crossing_id != action.crossing_id or e.stable_state != "GREEN"
                    or e.raw_state != "GREEN" or e.quality_flags):
                return stop("SIGNAL_LOST_BEFORE_DEPARTURE")
            if frame.fresh("departure") and extra.departure_observed:
                if e.body_motion_status != "MOVING":
                    return stop("CONTRADICTORY_DEPARTURE_EVIDENCE")
                return result("DEPARTING", "PHYSICAL_DEPARTURE_OBSERVED", departed=True)
            if e.goal_state == "SUCCEEDED":
                return stop("DEPARTURE_EVIDENCE_REQUIRED")
            return result("DEPARTING", "WAIT_PHYSICAL_DEPARTURE", ("RELEASE",))
        if e.goal_state == "SUCCEEDED":
            return result("SUCCEEDED", "EXIT_LEG_COMPLETE", ("HOLD",))
        return result(reason="CROSSING_IN_PROGRESS")
    if state.phase == "TERRAIN":
        if (frame.fresh("terrain") and e.terrain_complete and extra.terrain_verified
                and bool(extra.validation_reference)):
            return result("SUCCEEDED", "TERRAIN_VALIDATED", ("HOLD",))
        return result(reason="TERRAIN_VALIDATION_REQUIRED")
    if state.phase == "FINISH":
        if frame.fresh("body") and e.zone_id == action.zone_id and e.full_body_crossed:
            return result("SUCCEEDED", "FULL_BODY_OUT_OBSERVED", full_body_crossed=True)
        return result(reason="FULL_BODY_CROSSING_REQUIRED")
    if state.phase == "RISE_WAIT":
        if (frame.fresh("posture", "motion") and e.posture == "STAND"
                and extra.posture_verified and extra.validation_reference
                and e.body_motion_status == "STOPPED" and hold_ack):
            return result("READY_TO_MOVE", "STAND_VERIFIED_HOLD_RETAINED")
        return result(reason="STAND_COMPLETION_EVIDENCE_REQUIRED")
    return stop("UNKNOWN_ACTION_PHASE")
