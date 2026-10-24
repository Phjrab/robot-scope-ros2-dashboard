"""Join a C4 signal fragment with independent, trusted component observations.

No feet, stop, pose, path or goal evidence originates in the image pipeline.
The caller is trusted binding code, not a public JSON endpoint.
"""
from dataclasses import replace

from .observations import ComponentStamp, FIELDS, ObservationRejected


class CompetitionIngress:
    def __init__(self, adapter, *, traffic_config_hash):
        self.adapter = adapter
        self.traffic_config_hash = traffic_config_hash

    def join(self, packet, sample, *, now):
        from ...competition_traffic.projection import signal_fragment
        scope, action = self.adapter.scope, self.adapter.action
        if any(packet.evidence.get(key) != value for key, value in vars(scope).items()):
            raise ObservationRejected('INGRESS_SCOPE_MISMATCH')
        frame, observation = sample.frame, sample.observation
        context = observation.context
        binding = self.adapter.bindings['signal']
        if ((frame.source_id, frame.producer_epoch, frame.source_clock) !=
                (binding.producer_id, binding.epoch, binding.source_clock)
                or context['config_hash'] != self.traffic_config_hash
                or observation.signal['signal_id'] != action.signal_id
                or observation.signal['crossing_id'] != action.crossing_id):
            raise ObservationRejected('SIGNAL_BINDING_MISMATCH')
        if frame.source_clock == 'fixture':
            if (not self.adapter.activation.synthetic or not context['association_verified']
                    or frame.source_age_s is None or not 0 <= now - frame.received_s <= .25
                    or frame.source_age_s + now - frame.received_s > .25):
                raise ObservationRejected('OFFLINE_SIGNAL_EXPIRED_OR_NOT_ALLOWED')
            fragment = dict(observation.signal)
            if fragment['quality_flags']:
                fragment['stable_state'] = 'UNKNOWN'
        else:
            fragment = signal_fragment(observation, now_s=now, received_s=sample.processed_s)
        data = dict(packet.evidence)
        data.update({name: fragment[name] for name in FIELDS['signal']})
        stamps = dict(packet.components)
        stamps['signal'] = ComponentStamp(scope, frame.source_id, frame.producer_epoch,
            frame.sequence, frame.source_stamp_ns, frame.source_age_s, frame.source_clock,
            received_s=frame.received_s)
        return replace(packet, evidence=data, components=stamps)
