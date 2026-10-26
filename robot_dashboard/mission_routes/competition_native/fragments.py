"""Join C4's partial signal projection; never invent independent robot facts."""
from dataclasses import dataclass
import math
import re

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
    inference_settings_sha256: str  # Required trusted-owner pin, never learned from a frame.

    def __post_init__(self):
        if not _settings_digest(self.inference_settings_sha256):
            raise ValueError("C4_EXPECTED_INFERENCE_SETTINGS_INVALID")


def _settings_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def join_signal(packet: Packet, *, fragment, context, binding: SignalBinding,
                now_s, receiver_clock_id, first_received_s=None,
                source_age_at_first_receipt_s=None, processed_s=None):
    """Join C4's owner-pinned inference and first-receipt contract on the SAME host.

    Optional time arguments can only confirm the context, never replace it.
    Legacy completed-age fields, when present, must agree with explicit first
    age. They are consistency checks, not the default source of first age.
    """
    def reject(reason):
        raise ObservationRejected(reason)

    settings = context.get("inference_settings_sha256")
    if settings is None:
        reject("C4_INFERENCE_SETTINGS_REQUIRED")
    if not _settings_digest(settings):
        reject("C4_INFERENCE_SETTINGS_INVALID")
    if settings != binding.inference_settings_sha256:
        reject("C4_INFERENCE_SETTINGS_MISMATCH")
    if context.get("observation_mode") != "mission":
        reject("C4_MISSION_OBSERVATION_REQUIRED")
    if (receiver_clock_id != binding.receiver_clock_id
            or binding.source_clock not in {"synchronized_ros", "synchronized_utc"}
            or context.get("schema_version") != "traffic-observation-sidecar.v0.1"
            or context.get("clock_verified") is not True
            or context.get("identity_verified") is not True
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
    supplied = {"first_received_s": first_received_s,
                "source_age_at_first_receipt_s": source_age_at_first_receipt_s,
                "processed_s": processed_s}
    times = {key: context.get(key) for key in supplied}
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
           for v in (*times.values(), now_s)):
        reject("C4_EXPLICIT_FIRST_RECEIPT_REQUIRED")
    for key, value in supplied.items():
        if value is not None and (type(value) not in (int, float) or value != times[key]):
            reject("C4_FIRST_RECEIPT_ARGUMENT_MISMATCH")
    first = times["first_received_s"]
    initial_age = times["source_age_at_first_receipt_s"]
    processed = times["processed_s"]
    if not first <= processed <= now_s:
        reject("C4_AGE_ANCHOR_MISMATCH")
    residence = processed - first
    for key, expected_age in (("receiver_age_s", residence), ("source_age_s", initial_age + residence)):
        if key in context:
            value = context[key]
            if (type(value) not in (int, float) or not math.isfinite(value) or value < 0
                    or not math.isclose(value, expected_age, abs_tol=1e-9, rel_tol=0)):
                reject("C4_CONTRADICTORY_AGE")
    sequence, stamp = context.get("sequence"), context.get("source_stamp_ns")
    if (type(sequence) is not int or sequence < 0 or not isinstance(stamp, str)
            or not stamp.isascii() or not stamp.isdigit() or not 1 <= len(stamp) <= 24):
        reject("C4_INVALID_SOURCE_IDENTITY")
    if now_s - first > .25 or now_s > first + .25 - initial_age:
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
                           binding.source_clock, first, receiver_clock_id, .25)
    components = {**packet.components, "signal": stamp}
    return Packet(data, components, packet.extras, packet.receiver_session_id)


def project_signal(packet, *, observation, projection, binding, now_s, receiver_clock_id,
                   first_received_s=None, source_age_at_first_receipt_s=None, processed_s=None):
    """Call the injected actual C4 signal_fragment, then join independent facts.

    Inject competition_traffic.projection.signal_fragment. Injection keeps this
    package importable without the optional C4 package or image dependencies.
    """
    fragment = projection(observation, now_s=now_s,
                          received_s=observation.context.get("first_received_s"))
    return join_signal(packet, fragment=fragment, context=observation.context,
                       binding=binding, now_s=now_s, receiver_clock_id=receiver_clock_id,
                       first_received_s=first_received_s, processed_s=processed_s,
                       source_age_at_first_receipt_s=source_age_at_first_receipt_s)
