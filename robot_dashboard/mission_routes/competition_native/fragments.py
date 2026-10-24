"""Join C4's partial signal projection; never invent independent robot facts."""
from dataclasses import dataclass
import math

from .observations import ComponentStamp, FIELDS, ObservationRejected, Packet


@dataclass(frozen=True)
class SignalBinding:
    producer_id: str
    epoch: str
    source_clock: str
    config_hash: str  # C4 configuration hash, distinct from the mission config
    binding_id: str
    model_sha256: str
    signal_id: str
    crossing_id: str
    receiver_clock_id: str


def join_signal(packet: Packet, *, fragment, context, binding: SignalBinding,
                first_received_s, processed_s, now_s, receiver_clock_id):
    """C4 exact e2e9c50 projection output + trusted SAME-HOST arrival metadata.

    Call C4 signal_fragment(observation, now_s=now, received_s=processed_s).
    C4 context.source_age_s already includes processing residence. Recover age
    at the ORIGINAL arrival, so C2 adds that residence exactly once. Cross-host
    callers must supply a locally revalidated clock/age envelope instead; remote
    monotonic subtraction is never allowed here.
    """
    def reject(reason):
        raise ObservationRejected(reason)

    if (receiver_clock_id != binding.receiver_clock_id
            or binding.source_clock not in {"synchronized_ros", "synchronized_utc"}
            or context.get("schema_version") != "traffic-observation-sidecar.v0.1"
            or context.get("clock_verified") is not True
            or context.get("association_verified") is not True
            or context.get("complete_mission_evidence") is not False
            or context.get("departure_authorized") is not False):
        reject("C4_CLOCK_OR_PARTIAL_CONTRACT_MISMATCH")
    expected = {"source_id": binding.producer_id, "producer_epoch": binding.epoch,
                "source_clock": binding.source_clock, "config_hash": binding.config_hash,
                "binding_id": binding.binding_id, "receipt_ttl_s": .25}
    if any(context.get(k) != v for k, v in expected.items()):
        reject("C4_SOURCE_OR_ASSOCIATION_MISMATCH")
    if any(fragment.get(k) != getattr(binding, k) for k in ("signal_id", "crossing_id", "model_sha256")):
        reject("C4_SIGNAL_OR_MODEL_MISMATCH")
    age, residence = context.get("source_age_s"), context.get("receiver_age_s")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
           for v in (first_received_s, processed_s, now_s, age, residence)):
        reject("C4_INVALID_TIME")
    if (not first_received_s <= processed_s <= now_s
            or not math.isclose(processed_s - first_received_s, residence, abs_tol=1e-9, rel_tol=0)
            or age < residence):
        reject("C4_AGE_ANCHOR_MISMATCH")
    initial_age = age - residence
    if now_s - first_received_s > .25 or initial_age + now_s - first_received_s > .25:
        reject("C4_SIGNAL_EXPIRED")
    fields = FIELDS["signal"]
    if any(k not in fragment for k in fields):
        reject("C4_SIGNAL_FRAGMENT_INCOMPLETE")
    signal = {k: fragment[k] for k in fields}
    if signal["quality_flags"]:
        signal["stable_state"] = "UNKNOWN"
    data = dict(packet.evidence)
    data.update(signal)
    from .contracts import Scope
    scope = Scope(**{k: data[k] for k in Scope.__dataclass_fields__})
    stamp = ComponentStamp(scope, binding.producer_id, binding.epoch,
                           context["sequence"], context["source_stamp_ns"], initial_age,
                           binding.source_clock, first_received_s, receiver_clock_id, .25)
    components = {**packet.components, "signal": stamp}
    return Packet(data, components, packet.extras, packet.receiver_session_id)
