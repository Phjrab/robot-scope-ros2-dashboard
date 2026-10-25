"""Join a C4 signal fragment with independent, trusted component observations.

No feet, stop, pose, path or goal evidence originates in the image pipeline.
The caller is trusted binding code, not a public JSON endpoint.
"""
from dataclasses import replace
import re

from .observations import ComponentStamp, FIELDS, ObservationRejected


class CompetitionIngress:
    def __init__(self, adapter, *, traffic_config_hash, inference_settings_sha256, signal_binding=None):
        if not isinstance(inference_settings_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', inference_settings_sha256):
            raise ValueError('EXPLICIT_INFERENCE_SETTINGS_PIN_REQUIRED')
        self.adapter = adapter
        self.traffic_config_hash = traffic_config_hash
        self.signal_binding = signal_binding
        self.inference_settings_sha256 = inference_settings_sha256

    @staticmethod
    def review(sample, *, now, inference_settings_sha256):
        """Read-only C4 projection diagnostics; never create independent facts."""
        from ...competition_traffic.projection import signal_fragment
        observation = sample.observation
        matches = observation.context.get('inference_settings_sha256') == inference_settings_sha256
        reasons = [] if matches else ['C4_INFERENCE_SETTINGS_MISMATCH']
        try:
            signal_fragment(observation, now_s=now, received_s=sample.frame.received_s)
        except ValueError as exc:
            reasons.append(str(exc))
        return {'inference_binding_matches': matches, 'projection_reasons': reasons,
                'departure_authorized': False, 'complete_mission_evidence': False,
                'independent_facts': {'feet': None, 'physical_stop': None, 'path': None, 'departure': None}}

    def join(self, packet, sample, *, now):
        from ...competition_traffic.projection import signal_fragment
        scope, action = self.adapter.scope, self.adapter.action
        if any(packet.evidence.get(key) != value for key, value in vars(scope).items()):
            raise ObservationRejected('INGRESS_SCOPE_MISMATCH')
        frame, observation = sample.frame, sample.observation
        context = observation.context
        if context.get('inference_settings_sha256') != self.inference_settings_sha256:
            raise ObservationRejected('C4_INFERENCE_SETTINGS_MISMATCH')
        if context.get('observation_mode') != 'mission':
            raise ObservationRejected('C4_MISSION_OBSERVATION_REQUIRED')
        binding = self.adapter.bindings['signal']
        if ((frame.source_id, frame.producer_epoch, frame.source_clock) !=
                (binding.producer_id, binding.epoch, binding.source_clock)
                or any(context.get(name) != getattr(frame, name) for name in
                       ('source_id', 'producer_epoch', 'source_clock', 'sequence', 'source_stamp_ns', 'binding_id'))
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
            from .fragments import join_signal
            if self.signal_binding is None:
                raise ObservationRejected('EXPLICIT_SIGNAL_BINDING_REQUIRED')
            fragment = signal_fragment(observation, now_s=now, received_s=frame.received_s)
            return join_signal(packet, fragment=fragment, context=context,
                binding=self.signal_binding, first_received_s=frame.received_s,
                processed_s=context['processed_s'], source_age_at_first_receipt_s=frame.source_age_s, now_s=now,
                receiver_clock_id=self.adapter.receiver_clock_id)
        data = dict(packet.evidence)
        data.update({name: fragment[name] for name in FIELDS['signal']})
        stamps = dict(packet.components)
        stamps['signal'] = ComponentStamp(scope, frame.source_id, frame.producer_epoch,
            frame.sequence, frame.source_stamp_ns, frame.source_age_s, frame.source_clock,
            first_received_s=frame.received_s, receiver_clock_id=self.adapter.receiver_clock_id, validity_s=.25)
        return replace(packet, evidence=data, components=stamps)
