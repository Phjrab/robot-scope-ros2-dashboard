"""Consume existing PointCloudHub observation evidence, without subscribing."""
import math
from robot_dashboard.ros.observation_identity import subscription_evidence_key
from robot_dashboard.obstacle_runtime_adapter.messages import Identity, header_matches


def from_owner(message, observation, *, context, source_id, sequence, receipt_ns,
               clock_domain, evidence_kind):
    """Keep the owner's original integer receipt; float metadata is corroboration.

    ROS_HEADER_UNVERIFIED is never promoted to a known clock by this function.
    The caller supplies independent ClockMapping evidence to the runtime. GID or
    graph evidence labels identity only; neither grants transform/pose validity.
    """
    received = observation.get('received_monotonic_s')
    if (type(receipt_ns) is not int or type(received) not in (int,float)
            or not math.isfinite(received) or observation.get('invalidated')
            or observation.get('publisher_epoch') != context.source_epoch
            or observation.get('reset_reason') == 'SOURCE_STAMP_STALLED'
            or abs(receipt_ns-received*1e9) > max(1,math.ceil(math.ulp(float(received))*1e9))):
        raise ValueError('ORIGINAL_OWNER_OBSERVATION_REQUIRED')
    if (observation.get('identity_status') != 'OBSERVED_PUBLISHER'
            and subscription_evidence_key(observation,received) is None):
        raise ValueError('OWNER_SOURCE_IDENTITY_UNAVAILABLE')
    identity = Identity(source_id,context.source_epoch,sequence,observation['source_stamp_ns'],
        clock_domain,message.header.frame_id,receipt_ns,context.host_clock_id,context.tf_epoch,
        context.map_id,context.map_revision,evidence_kind,'c4.owner_handoff',context.map_generation)
    header_matches(message,identity)
    return identity
