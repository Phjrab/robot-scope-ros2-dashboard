"""D0 strict VM lifecycle boundary. Never publishes or manufactures action ACKs.

Local dataclasses are NOT additions to competition-evidence.v0.1. A trusted
receiver supplies local receipt time and verifies event provenance. The legacy
StopGoFSM remains the zone/dwell core; use this boundary for mission integration.
"""
from dataclasses import dataclass, replace
import math
try:
    from .core import StopGoFSM, StopInput
except ImportError:
    from core import StopGoFSM, StopInput


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


@dataclass(frozen=True)
class ActionEvent:
    kind: str
    run_id: str
    step_id: str
    goal_id: str
    goal_generation: int
    epoch: str
    sequence: int
    receipt_s: float
    source_age_s: float = 0.
    status: str = ''
    request_id: str = ''
    cancel_ack: bool = False


class TrafficLifecycle:
    """Session-bound synthetic lifecycle, deliberately not a native action adapter.

    Departure assumption: a fresh adapter observation of non-stopped body motion,
    explicitly associated with the acknowledged NEW exit goal, after its ACK.
    No displacement/velocity threshold is inferred here. Hardware evidence remains
    INPUT_REQUIRED. A process restart requires a new, non-reused mission generation.
    """
    def __init__(self, run_id, step_id, crossing_id, visit_id, signal_id, generation,
                 zone_id, approach_goal_id, approach_generation, *, simulation=True,
                 receiver_ttl_s=.25, source_max_age_s=.25, stop_gap_s=.5):
        strings=(run_id,step_id,crossing_id,visit_id,signal_id,zone_id,approach_goal_id)
        if any(not isinstance(s,str) or not s for s in strings): raise ValueError('nonempty identity required')
        if any(type(g) is not int or g<0 for g in (generation,approach_generation)): raise ValueError('integer generation required')
        if not all(finite(t) and t>0 for t in (receiver_ttl_s,source_max_age_s,stop_gap_s)): raise ValueError('invalid timing contract')
        self.run_id=run_id;self.step_id=step_id;self.generation=generation
        self.approach=(approach_goal_id,approach_generation)
        self.ttl=receiver_ttl_s;self.source_max_age=source_max_age_s
        self.core=StopGoFSM(simulation=simulation,ttl_s=source_max_age_s,stop_gap_s=stop_gap_s)
        self.core.begin(run_id,step_id,crossing_id,visit_id,signal_id,generation,zone_id)
        self.phase='APPROACH';self.hold_request_id=None;self.hold_requested_at=None;self.hold_ack=False;self.hold_ack_at=None
        self.event_epoch=None;self.event_sequence=-1;self.retired_epochs=set();self.last_now=None
        self.last_observation=None;self.last_observation_result=None;self.exit_goal=None
        self.exit_ack_at=None;self.exit_requested_at=None;self.exit_generation_highwater=approach_generation
        self.pending_fault=None;self.closed=False;self.used_exit_ids=set();self.ready_until=None
        self.stop_gap=stop_gap_s;self.stop_first_receipt=None;self.last_supported_end=None;self.source_stop_bound=0.;self.zone_core_start=None

    def _reset_pending(self):
        self.core.start=None
        self.last_observation_result=None;self.ready_until=None
        self.stop_first_receipt=None;self.last_supported_end=None;self.source_stop_bound=0.;self.zone_core_start=None
        if self.core.state not in ('CROSSING_COMMITTED','CLEAR'):
            self.core.state='STOP_ZONE_ALIGN'
            self.exit_goal=None;self.exit_ack_at=None;self.exit_requested_at=None

    def _bad(self,reason):
        self._reset_pending();self.pending_fault=reason
        return False

    def _clock(self,now):
        if not finite(now) or (self.last_now is not None and now<self.last_now):
            self.closed=True;self._bad('RECEIVER_CLOCK_INVALID');return False
        self.last_now=now;return True

    def accept_event(self,e:ActionEvent,*,now):
        if not self._clock(now) or self.closed:return False
        if not isinstance(e,ActionEvent):return self._bad('INVALID_EVENT')
        if ((e.run_id,e.step_id)!=(self.run_id,self.step_id) or type(e.goal_generation) is not int
            or type(e.sequence) is not int or e.sequence<0 or type(e.cancel_ack) is not bool
            or not isinstance(e.epoch,str) or not e.epoch or not finite(e.receipt_s)
            or not finite(e.source_age_s) or not 0<=now-e.receipt_s<=self.ttl
            or not 0<=e.source_age_s<=self.source_max_age
            or e.source_age_s+(now-e.receipt_s)>self.source_max_age):return self._bad('INVALID_OR_STALE_EVENT')
        if e.epoch in self.retired_epochs:return self._bad('RETIRED_EVENT_EPOCH')
        if self.event_epoch is not None and e.epoch!=self.event_epoch:
            self.retired_epochs.add(self.event_epoch)
            self.event_epoch=e.epoch;self.event_sequence=-1
            # Restart destroys action ownership; do not accept replacement ACKs.
            self.closed=True;return self._bad('ACTION_RECEIVER_RESTART_REQUIRES_NEW_SESSION')
        if e.sequence<=self.event_sequence:return self._bad('REPEATED_EVENT')
        self.event_epoch=e.epoch;self.event_sequence=e.sequence
        if e.kind=='APPROACH_TERMINAL':
            if self.phase not in ('APPROACH','APPROACH_CANCEL_PENDING') or (e.goal_id,e.goal_generation)!=self.approach:
                return self._bad('WRONG_APPROACH_TERMINAL')
            if e.status=='CANCELED' and not e.cancel_ack:
                self.phase='APPROACH_CANCEL_PENDING'
                return self._bad('APPROACH_CANCEL_ACK_PENDING')
            if e.status=='FAILED':
                self.closed=True;return self._bad('APPROACH_FAILED')
            if not (e.status=='SUCCEEDED' or (e.status=='CANCELED' and e.cancel_ack)):
                return self._bad('APPROACH_NOT_TERMINAL_ACKNOWLEDGED')
            self.phase='HOLD_ACK_PENDING'
            self.hold_request_id=f'{self.run_id}:{self.step_id}:{self.generation}:hold:{e.epoch}:{e.sequence}'
            self.hold_requested_at=now;self.pending_fault=None
            return True
        if e.kind=='HOLD_ACK':
            if (self.phase!='HOLD_ACK_PENDING' or (e.goal_id,e.goal_generation)!=self.approach
                or e.request_id!=self.hold_request_id or e.status!='ACKNOWLEDGED'
                or e.receipt_s-e.source_age_s<=self.hold_requested_at):return self._bad('HOLD_ACK_MISMATCH_OR_PRE_REQUEST')
            self.hold_ack=True;self.hold_ack_at=e.receipt_s;self.phase='STOP_EVIDENCE';self.pending_fault=None;self._reset_pending()
            return True
        if e.kind=='EXIT_ACK':
            if (self.exit_goal is None or (e.goal_id,e.goal_generation)!=self.exit_goal
                or e.status!='ACTIVE' or e.receipt_s-e.source_age_s<=self.exit_requested_at):return self._bad('EXIT_ACK_MISMATCH_OR_PRE_REQUEST')
            self.exit_ack_at=e.receipt_s;self.pending_fault=None;return True
        return self._bad('UNSUPPORTED_EVENT')

    def request_exit(self,goal_id,generation,now):
        if not self._clock(now) or self.closed:return False
        r=self.last_observation_result
        if (not isinstance(goal_id,str) or not goal_id or goal_id==self.approach[0]
            or goal_id in self.used_exit_ids or self.core.state!='DEPART_PENDING'
            or type(generation) is not int or generation<=self.exit_generation_highwater
            or self.exit_goal is not None or self.phase!='STOP_EVIDENCE' or not r
            or not r.get('depart_intent') or self.ready_until is None or now>self.ready_until or self.last_observation is None
            or not 0<=now-self.last_observation<=self.ttl):return self._bad('EXIT_REQUEST_NOT_ELIGIBLE')
        self.used_exit_ids.add(goal_id)
        self.exit_generation_highwater=generation;self.exit_goal=(goal_id,generation)
        self.exit_requested_at=now;self.exit_ack_at=None
        return True

    def _output(self,i,reason,release=False,core_result=None):
        r=dict(core_result or {})
        r.update(state=self.core.state,lifecycle_state=self.phase,reason=reason,
            depart_intent=bool(release and self.core.state=='DEPART_PENDING'),
            hold_request_id=self.hold_request_id,exit_goal_required=bool(core_result and core_result.get('depart_intent') and self.exit_goal is None),
            exit_goal_id=self.exit_goal[0] if self.exit_goal else None,
            exit_generation=self.exit_goal[1] if self.exit_goal else None,
            active_goal_id=self.exit_goal[0] if self.exit_goal is not None and self.exit_ack_at is not None else self.approach[0],
            active_goal_generation=self.exit_goal[1] if self.exit_goal is not None and self.exit_ack_at is not None else self.approach[1],
            evidence_type='SYNTHETIC' if self.core.simulation else 'ADAPTER_INPUT',
            observed_stop_lower_bound_s=self.source_stop_bound)
        r['motion_constraint']={'owner_id':'traffic_vm','run_id':self.run_id,'step_id':self.step_id,
            'request_id':f'{self.generation}:{getattr(i,"epoch","invalid")}:{getattr(i,"sequence",-1)}',
            'generation':self.generation,'reason':reason,'mode':'RELEASE' if release else 'HOLD',
            'max_vx':None if release else 0.,'max_vy':None if release else 0.,'max_wz':None if release else 0.,
            'validity':{'receipt_ttl_s':self.ttl},'priority':60}
        return r

    def observe(self,i:StopInput,*,now,pose_age_s=None,observed_goal_id=None,observed_goal_generation=None):
        if not self._clock(now) or self.closed:return self._output(i,'SESSION_CLOSED')
        if not isinstance(i,StopInput):
            self.closed=True;self._reset_pending();return self._output(i,'INVALID_OBSERVATION')
        if (not finite(i.receipt_s) or not 0<=now-i.receipt_s<=self.ttl
            or not finite(pose_age_s) or not 0<=pose_age_s<=self.source_max_age
            or pose_age_s+(now-i.receipt_s)>self.source_max_age):
            self._reset_pending();return self._output(i,'RECEIPT_OR_POSE_EXPIRED')
        identity_fields=('run_id','step_id','crossing_id','visit_id','signal_id','zone_id','epoch')
        if (any(not isinstance(getattr(i,name),str) or not getattr(i,name) for name in identity_fields)
            or type(i.sequence) is not int or i.sequence<0 or type(i.generation) is not int or i.generation<0):
            self.closed=True;self._reset_pending();return self._output(i,'INVALID_INPUT_IDENTITY')
        bool_fields=('left_inside','right_inside','visual_zone','body_stopped','path_clear','localization_ready',
                     'safety_stop','approach_ack','departure_observed','fully_crossed','cancel')
        if any(type(getattr(i,name)) is not bool for name in bool_fields):
            self.closed=True;self._reset_pending();return self._output(i,'INVALID_INPUT_TYPES')
        if i.cancel:
            self.closed=True;self.core.state='CANCELLED';self._reset_pending()
            return self._output(i,'CANCELLED')
        # Core validates identity, source age, sequence, sensor epoch and safety,
        # even while traffic itself must not block the active approach goal.
        departure=i.departure_observed
        authorized_departure=(self.exit_goal is not None and self.exit_ack_at is not None
            and (observed_goal_id,observed_goal_generation)==self.exit_goal
            and type(observed_goal_generation) is int and finite(i.observation_age_s)
            and i.receipt_s-i.observation_age_s>self.exit_ack_at)
        residence=now-i.receipt_s
        ci=replace(i,approach_ack=self.hold_ack,departure_observed=departure and authorized_departure,
            fully_crossed=i.fully_crossed and authorized_departure,
            signal_age_s=i.signal_age_s+residence if finite(i.signal_age_s) else i.signal_age_s,
            observation_age_s=i.observation_age_s+residence if finite(i.observation_age_s) else i.observation_age_s)
        previous_epoch=self.core.epoch
        r=self.core.update(ci)
        self.last_observation=i.receipt_s;self.last_observation_result=r
        if previous_epoch is not None and self.core.epoch!=previous_epoch:
            self.closed=True;self._reset_pending();return self._output(i,'OBSERVATION_RESTART_REQUIRES_NEW_SESSION')
        if r['state'] in ('INTERRUPTED','CANCELLED'):
            self.closed=True;self._reset_pending();return self._output(i,r['reason'],core_result=r)
        if self.pending_fault:
            reason=self.pending_fault;self.pending_fault=None
            return self._output(i,reason,core_result=r)
        invalid_reasons={'INVALID_INPUT_TYPES','IDENTITY_MISMATCH','RETIRED_EPOCH','STALE_OR_REPEATED_INPUT',
                         'SAFETY_OR_OBSTACLE_OR_LOCALIZATION_HOLD','CONTRADICTORY_DEPARTURE_EVIDENCE'}
        if r['reason'] in invalid_reasons:
            self._reset_pending();return self._output(i,r['reason'],core_result=r)
        if self.phase=='APPROACH':
            if departure:return self._output(i,'UNEXPECTED_APPROACH_DEPARTURE')
            return self._output(i,'APPROACH_TRAFFIC_GATE_INACTIVE',True,r)
        if self.phase=='APPROACH_CANCEL_PENDING':return self._output(i,'WAIT_APPROACH_CANCEL_ACK',core_result=r)
        if self.phase=='HOLD_ACK_PENDING':return self._output(i,'WAIT_MATCHING_HOLD_ACK',core_result=r)
        if (departure or i.fully_crossed) and not authorized_departure:
            self._reset_pending();return self._output(i,'UNBOUND_DEPARTURE_EVIDENCE',core_result=r)
        if r['state'] in ('CROSSING_COMMITTED','CLEAR'):
            self.phase=r['state'];return self._output(i,r['reason'],r['motion_constraint']['mode']=='RELEASE',r)
        # Receiver duration is not physical observed duration when sensor delay
        # varies. Conservatively start at first valid receipt, end at latest
        # source-supported local instant. Never count residence as evidence.
        if self.core.start is None:
            self.stop_first_receipt=None;self.last_supported_end=None;self.source_stop_bound=0.;self.zone_core_start=None
        else:
            supported_end=i.receipt_s-i.observation_age_s
            if self.hold_ack_at is None or supported_end<=self.hold_ack_at:
                self._reset_pending();return self._output(i,'STOP_OBSERVATION_PRECEDES_HOLD_ACK',core_result={**r,'depart_intent':False})
            if self.zone_core_start!=self.core.start:
                self.stop_first_receipt=i.receipt_s;self.last_supported_end=None
                self.zone_core_start=self.core.start
            if self.last_supported_end is not None and (supported_end<=self.last_supported_end or supported_end-self.last_supported_end>self.stop_gap):
                self._reset_pending();return self._output(i,'SOURCE_STOP_SEQUENCE_OR_GAP_INVALID',core_result={**r,'depart_intent':False})
            self.last_supported_end=supported_end
            self.source_stop_bound=max(0.,supported_end-self.stop_first_receipt)
            if self.source_stop_bound<self.core.dwell:
                r={**r,'depart_intent':False,'reason':'OBSERVED_STOP_BOUND_INSUFFICIENT'}
                self.last_observation_result=r;self.ready_until=None
        if not r['depart_intent']:
            self.exit_goal=None;self.exit_ack_at=None;self.exit_requested_at=None
            return self._output(i,r['reason'],core_result=r)
        self.ready_until=min(i.receipt_s+self.ttl, i.receipt_s+self.source_max_age-i.signal_age_s,
            i.receipt_s+self.source_max_age-i.observation_age_s,i.receipt_s+self.source_max_age-pose_age_s)
        if self.exit_ack_at is None:return self._output(i,'FRESH_EXIT_GOAL_ACK_REQUIRED',core_result=r)
        return self._output(i,'EXIT_READY_AWAIT_OBSERVED_DEPARTURE',True,r)
