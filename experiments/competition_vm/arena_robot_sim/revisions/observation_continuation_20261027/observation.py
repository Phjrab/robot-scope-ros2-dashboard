"""Pure observation lifecycle contract; NEVER emits or modifies robot commands.

Not wired into C3. Times are elapsed seconds in one monotonic observer clock.
An action terminal status does not itself terminate observation or restart a goal.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Sample:
    elapsed_s: float
    action_status: str = "EXECUTING"
    predicted_collision: bool = False
    raw_contact: bool | None = None
    padded_violation: bool = False
    goal_verified: bool = False
    infrastructure_error: str | None = None
    cancelled_by_operator: bool = False
    translation_speed_mps: float = 0.0


class Observer:
    """Finite-lifetime, sticky terminal decision independent of motion control."""
    def __init__(self, max_observation_s: float):
        if not math.isfinite(max_observation_s) or max_observation_s <= 0:
            raise ValueError("finite positive observation budget required")
        self.limit = max_observation_s
        self.previous = None
        self.terminal = None
        self.padding_ever = False
        self.contact_unknown = False
        self.prediction_samples = 0
        self.zero_speed_samples = 0
        self.samples = 0
        self.speed_integral = 0.0
        self.observed_duration = 0.0

    def step(self, sample: Sample):
        if self.terminal:
            return dict(self.terminal)
        if (not math.isfinite(sample.elapsed_s) or sample.elapsed_s < 0 or
            not math.isfinite(sample.translation_speed_mps) or sample.translation_speed_mps < 0):
            raise ValueError("invalid elapsed time or translation speed")
        if self.previous and sample.elapsed_s <= self.previous.elapsed_s:
            raise ValueError("one monotonic clock; strictly increasing samples required")
        if sample.action_status not in {"ACCEPTED", "EXECUTING", "CANCELING", "SUCCEEDED", "ABORTED", "CANCELED"}:
            raise ValueError("unsupported action status")
        if sample.raw_contact is not None and type(sample.raw_contact) is not bool:
            raise ValueError("raw_contact must be true, false or unknown")
        self.samples += 1
        self.padding_ever |= sample.padded_violation
        self.contact_unknown |= sample.raw_contact is None
        self.prediction_samples += int(sample.predicted_collision)
        self.zero_speed_samples += int(sample.translation_speed_mps == 0)
        if self.previous:
            dt = sample.elapsed_s - self.previous.elapsed_s
            self.observed_duration += dt
            self.speed_integral += dt * (self.previous.translation_speed_mps + sample.translation_speed_mps) / 2
        self.previous = sample
        reason = None
        if sample.raw_contact is True:
            reason = "RAW_CONTACT"
        elif sample.infrastructure_error:
            reason = "INFRASTRUCTURE_ERROR"
        elif sample.cancelled_by_operator:
            reason = "OPERATOR_CANCEL"
        elif sample.elapsed_s >= self.limit:
            reason = "OBSERVATION_TIMEOUT"
        elif sample.action_status == "SUCCEEDED":
            reason = "GOAL_REACHED" if sample.goal_verified else "GOAL_EVIDENCE_ERROR"
        result = dict(
            continue_observation=reason is None,
            terminal_reason=reason,
            action_status=sample.action_status,
            restart_goal=False,
            command_authority="NONE",
            predictive_stop_policy="UNCHANGED",
            safety_evaluation=("FAIL_RAW_CONTACT" if reason == "RAW_CONTACT" else
                               "FAIL_PADDED_ENVELOPE" if self.padding_ever else
                               "INPUT_REQUIRED" if self.contact_unknown else "NOT_QUALIFIED"),
            goal_reached=reason == "GOAL_REACHED",
            navigation_accepted=False,  # throughput/whole-path/hardware qualification is external
            prediction_samples=self.prediction_samples,
            zero_speed_samples=self.zero_speed_samples,
            sample_count=self.samples,
            mean_sampled_translation_speed_mps=(self.speed_integral / self.observed_duration
                                                if self.observed_duration else None),
            duration_between_samples_s=self.observed_duration,
        )
        if reason:
            self.terminal = dict(result)
        return result
