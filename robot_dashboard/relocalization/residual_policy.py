"""Evaluate a stored RMSE only; never accept a candidate or change other gates.

The original 5 cm policy remains available.  The provisional 10 cm policy is an
explicit observation-only choice, not an accuracy claim or an operational gate.
No distances, transforms, or registration results are recomputed or modified.
"""

from dataclasses import asdict, dataclass, field
import math
from numbers import Real
from typing import Any


_ORIGINAL_POLICY_ID = "robot-scope.residual-policy.original-0.05m.v1"


@dataclass(frozen=True)
class ResidualPolicy:
    policy_id: str
    source_policy_id: str
    max_rmse_m: float
    provisional: bool
    qualifier: str
    original_max_rmse_m: float = field(default=0.05, init=False)
    unit: str = field(default="m", init=False)
    evaluation_scope: str = field(default="STORED_RMSE_ONLY", init=False)
    observation_only: bool = field(default=True, init=False)
    no_accuracy_claim: bool = field(default=True, init=False)
    accuracy_verified: bool = field(default=False, init=False)


ORIGINAL_RESIDUAL_POLICY = ResidualPolicy(
    policy_id=_ORIGINAL_POLICY_ID,
    source_policy_id=_ORIGINAL_POLICY_ID,
    max_rmse_m=0.05,
    provisional=False,
    qualifier="ORIGINAL_RESIDUAL_ONLY",
)
PROVISIONAL_RESIDUAL_POLICY = ResidualPolicy(
    policy_id="robot-scope.residual-policy.provisional-0.10m.v1",
    source_policy_id=_ORIGINAL_POLICY_ID,
    max_rmse_m=0.10,
    provisional=True,
    qualifier="PROVISIONAL_RESIDUAL_ONLY",
)


@dataclass(frozen=True)
class ResidualEvaluation:
    rmse_m: float
    residual_passed: bool
    original_residual_passed: bool
    policy: ResidualPolicy
    original_policy: ResidualPolicy = field(default=ORIGINAL_RESIDUAL_POLICY, init=False)
    overall_candidate_acceptance_evaluated: bool = field(default=False, init=False)
    overall_candidate_accepted: None = field(default=None, init=False)

    def as_dict(self) -> dict[str, Any]:
        """Return separate metadata; no existing result or gate list is accepted."""
        return asdict(self)


def evaluate_residual(
    rmse_m: Real, *, policy: ResidualPolicy, unit: str = "m"
) -> ResidualEvaluation:
    """Compare one finite, nonnegative stored RMSE with an explicit fixed policy.

    Values must already be in metres; this function does no unit conversion,
    rounding, or tolerance adjustment.  A residual pass evaluates only this
    numeric condition.  All other candidate and operational gates remain outside
    this API.  Only the two immutable policies defined above are supported.
    """
    if not isinstance(unit, str) or unit != "m":
        raise ValueError("stored RMSE unit must be 'm'; unit conversion is not performed")
    if policy is not ORIGINAL_RESIDUAL_POLICY and policy is not PROVISIONAL_RESIDUAL_POLICY:
        raise ValueError("an original or provisional fixed residual policy is required")
    if isinstance(rmse_m, bool) or not isinstance(rmse_m, Real):
        raise ValueError("stored RMSE must be a finite nonnegative real scalar")
    try:
        value = float(rmse_m)
    except (OverflowError, ValueError) as error:
        raise ValueError("stored RMSE must be finite and nonnegative") from error
    if not math.isfinite(value) or rmse_m < 0:
        raise ValueError("stored RMSE must be finite and nonnegative")
    if value != rmse_m:
        raise ValueError("stored RMSE must be representable without changing its numeric value")
    return ResidualEvaluation(
        rmse_m=value,
        residual_passed=value <= policy.max_rmse_m,
        original_residual_passed=value <= ORIGINAL_RESIDUAL_POLICY.max_rmse_m,
        policy=policy,
    )
