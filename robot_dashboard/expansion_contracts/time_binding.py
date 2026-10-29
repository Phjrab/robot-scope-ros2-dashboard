"""The sole D3 source-clock -> C1 host-clock boundary. No inferred clock binding."""

from dataclasses import dataclass
import copy
import re

from .messages import CollisionAssessment, ContractError, host_ns, integer, token


def upgrade_observation(payload):
    """Lossless envelope migration only; does not translate clocks or restart TTL."""
    out = copy.deepcopy(payload)
    version = out.get("schema_version")
    if version not in {"0.1", "0.2"}:
        raise ContractError("unsupported observation version")
    out["received_monotonic_ns"] = str(host_ns(out["received_monotonic_ns"], version))
    out["schema_version"] = "0.2"
    return out


@dataclass(frozen=True)
class ClockBinding:
    source_clock_domain: str
    source_epoch: str
    host_clock_id: str
    offset_ns: int
    uncertainty_ns: int
    binding_id: str

    def __post_init__(self):
        for value in (
            self.source_clock_domain,
            self.source_epoch,
            self.host_clock_id,
            self.binding_id,
        ):
            token(value)
        integer(self.offset_ns, "clock offset", -(2**63 - 1), 2**63 - 1)
        integer(self.uncertainty_ns, "clock uncertainty", 0, 2**63 - 1)


def normalize_collision_assessment(
    payload, *, binding=None, max_validity_ns=500_000_000
):
    """Normalize a D3 interval only with an explicitly supplied, epoch-bound mapping.

    Conservative uncertainty shrinks both ends. The original interval and binding
    remain in freshness. UNKNOWN, coverage, references and receipt time are retained.
    C4 command authorization is deliberately not manufactured by this conversion.
    """
    integer(max_validity_ns, "validity policy", 1, 2**63 - 1)
    out = upgrade_observation(payload)
    interval = payload.get("validity_interval")
    if not isinstance(interval, dict):
        raise ContractError("validity interval required")
    if not interval:
        return CollisionAssessment.from_dict(out).to_dict()
    if set(interval) == {"host_clock_id", "start_monotonic_ns", "end_monotonic_ns"}:
        start = host_ns(interval["start_monotonic_ns"], payload["schema_version"])
        end = host_ns(interval["end_monotonic_ns"], payload["schema_version"])
        host = interval["host_clock_id"]
    elif set(interval) == {"clock_domain", "from_ns", "until_ns"}:
        if not isinstance(binding, ClockBinding) or (
            interval["clock_domain"] != binding.source_clock_domain
            or payload["clock_domain"] != binding.source_clock_domain
            or payload["source_epoch"] != binding.source_epoch
            or payload["host_clock_id"] != binding.host_clock_id
        ):
            raise ContractError(
                "explicit matching source/epoch/host clock binding required"
            )
        for key in ("from_ns", "until_ns"):
            token(
                interval[key],
                "D3 decimal time",
                re.compile(r"(?:0|[1-9][0-9]{0,24})\Z"),
            )
        original_start, original_end = (
            int(interval["from_ns"]),
            int(interval["until_ns"]),
        )
        if not 0 <= original_end - original_start <= max_validity_ns:
            raise ContractError("invalid original validity duration")
        start = original_start + binding.offset_ns + binding.uncertainty_ns
        end = original_end + binding.offset_ns - binding.uncertainty_ns
        host = binding.host_clock_id
        if "time_conversion" in out["freshness"]:
            raise ContractError("duplicate time conversion")
        out["freshness"]["time_conversion"] = {
            "original_interval": copy.deepcopy(interval),
            "binding_id": binding.binding_id,
            "source_epoch": binding.source_epoch,
            "offset_ns": str(binding.offset_ns),
            "uncertainty_ns": str(binding.uncertainty_ns),
        }
    else:
        raise ContractError("unknown or conflicting interval keys")
    if host != out["host_clock_id"] or not 0 <= end - start <= max_validity_ns:
        raise ContractError("invalid host binding or validity duration")
    out["validity_interval"] = {
        "host_clock_id": host,
        "start_monotonic_ns": str(start),
        "end_monotonic_ns": str(end),
    }
    return CollisionAssessment.from_dict(out).to_dict()
