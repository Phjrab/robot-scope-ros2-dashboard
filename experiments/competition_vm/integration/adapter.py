"""Synthetic in-process adapter only. No ROS, publisher, or actuator access.
Transport receipt time and sequence must come from a trusted local receiver.
"""
import importlib.util
import math
from pathlib import Path
import sys

def load_core(name, relative):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / relative / 'core.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

avoidance = load_core('integration_avoidance_core', 'avoidance')
traffic = load_core('integration_traffic_core', 'traffic_signals')

def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)

class ConstraintAdapter:
    """A session-bound, fail-closed constraint collector, never a controller.

    Every expected owner must provide fresh RELEASE to allow a new command.
    Invalid input invalidates that owner's prior release. Unidentified input
    invalidates all owners. Owner allowlisting is not authentication.
    Command sequence/receipt are receiver-assigned, not producer-controlled.
    New session/generation requires a new adapter; never reuse old packets.
    """
    def __init__(self, run_id, step_id, generation, owners=('traffic_vm',), max_ttl=.25, max_source_age=.25):
        if not all(isinstance(x,str) and x for x in (run_id,step_id)) or type(generation) is not int or generation<0:
            raise ValueError('invalid session')
        if not owners or any(not isinstance(x,str) or not x for x in owners) or len(set(owners))!=len(owners):
            raise ValueError('invalid owners')
        if not finite_number(max_ttl) or max_ttl<=0: raise ValueError('invalid TTL')
        if not finite_number(max_source_age) or max_source_age<=0: raise ValueError('invalid source age bound')
        self.max_source_age=max_source_age
        self.identity=(run_id,step_id,generation)
        self.owners=frozenset(owners); self.max_ttl=max_ttl
        self.entries={}; self.owner_seq={}; self.last_command=-1
        self.release_barrier=-1; self.arbiter=avoidance.CommandArbiter()
        self.last_now=None
        self.owner_epoch={}; self.retired_epochs={owner:set() for owner in self.owners}
        self.source_seq={}; self.source_stamp={}; self.closed=False
        self.goal_identity=None; self.retired_goals=set()

    def ingest(self, constraint, *, sequence, receipt_s, now, source_age_s=0.,
               producer_epoch="in_process", source_sequence=None, source_stamp_ns=None):
        owner=constraint.get('owner_id') if isinstance(constraint,dict) else None
        if not isinstance(owner,str) or owner not in self.owners:
            self.entries.clear(); return False
        self.entries.pop(owner,None)
        if self.closed: return False
        # Legacy callers are receiver-local in-process producers. Network adapters
        # MUST supply the producer envelope; receipt stamping alone is not freshness.
        source_sequence=sequence if source_sequence is None else source_sequence
        if not isinstance(producer_epoch,str) or not producer_epoch or producer_epoch in self.retired_epochs[owner]:
            return False
        if not finite_number(source_age_s) or source_age_s<0: return False
        if type(source_sequence) is not int or not 0<=source_sequence<2**63: return False
        current_epoch=self.owner_epoch.get(owner)
        if current_epoch is not None and current_epoch!=producer_epoch:
            # Restart is fail-closed. A new mission generation/adapter is required;
            # never silently restamp an old session as a restarted producer.
            self.retired_epochs[owner].add(current_epoch)
            self.retired_epochs[owner].add(producer_epoch)
            self.closed=True; self.entries.clear(); return False
        if source_sequence<=self.source_seq.get(owner,-1): return False
        if source_stamp_ns is not None:
            if type(source_stamp_ns) is not int or source_stamp_ns<0 or source_stamp_ns<=self.source_stamp.get(owner,-1): return False
        try:
            ttl=constraint['validity']['receipt_ttl_s']
            valid=(finite_number(now) and finite_number(receipt_s) and finite_number(ttl)
                   and 0<ttl<=self.max_ttl and 0<=now-receipt_s<=ttl
                   and source_age_s+now-receipt_s<=self.max_source_age
                   and (self.last_now is None or now>=self.last_now)
                   and type(sequence) is int and 0<=sequence<2**63
                   and sequence>self.owner_seq.get(owner,-1)
                   and (constraint['run_id'],constraint['step_id'],constraint['generation'])==self.identity
                   and type(constraint['generation']) is int
                   and isinstance(constraint['request_id'],str) and bool(constraint['request_id'])
                   and constraint['mode'] in ('HOLD','RELEASE'))
            if not valid: return False
            mode=constraint['mode']
            caps=tuple(constraint[k] for k in ('max_vx','max_vy','max_wz'))
            if mode=='HOLD' and not all(finite_number(x) and x==0 for x in caps): return False
            if mode=='RELEASE' and caps!=(None,None,None): return False
        except (KeyError,TypeError): return False
        self.last_now=now
        self.owner_seq[owner]=sequence
        self.owner_epoch[owner]=producer_epoch
        self.source_seq[owner]=source_sequence
        if source_stamp_ns is not None: self.source_stamp[owner]=source_stamp_ns
        self.entries[owner]=(mode,receipt_s,ttl,source_age_s)
        if mode=='RELEASE': self.release_barrier=self.last_command
        return True

    def apply(self, v, w, sequence, *, receipt_s, now, sensor_fresh, tf_fresh, estop=False, collision=False,
              goal_id=None, goal_generation=None):
        # Clock rollback requires new evidence and command; no old RELEASE survives.
        valid_time=finite_number(now) and finite_number(receipt_s)
        rollback=valid_time and self.last_now is not None and now<self.last_now
        if rollback: self.entries.clear()
        if valid_time: self.last_now=now
        valid_goal=(self.goal_identity is None or
                    (type(goal_generation) is int and (goal_id,goal_generation)==self.goal_identity))
        valid_command=(valid_goal and type(sequence) is int and 0<=sequence<2**63 and sequence>self.last_command
                       and sequence>self.release_barrier and valid_time and 0<=now-receipt_s<=self.max_ttl)
        if type(sequence) is int and 0<=sequence<2**63: self.last_command=max(self.last_command,sequence)
        fresh_release=(not self.closed and valid_time and all(owner in self.entries and self.entries[owner][0]=='RELEASE'
                          and 0<=now-self.entries[owner][1]<=self.entries[owner][2]
                          and now-self.entries[owner][1]+self.entries[owner][3]<=self.max_source_age
                          and receipt_s>=self.entries[owner][1] for owner in self.owners))
        bool_valid=all(type(x) is bool for x in (sensor_fresh,tf_fresh,estop,collision))
        if not valid_command or not bool_valid or rollback:
            return 0.,0.,'INVALID_OR_OLD_COMMAND'
        return self.arbiter.apply(v,w,sequence,sensor_fresh=sensor_fresh,tf_fresh=tf_fresh,
                                  estop=estop,collision=collision,signal_hold=not fresh_release)

    def close(self):
        """Cancel/restart barrier. This session cannot be revived by queued RELEASE."""
        self.closed=True
        self.entries.clear()

    def bind_goal(self, goal_id, goal_generation):
        """Explicit action owner binding; changing goal creates a command barrier.

        This is not an action ACK and must only follow the lifecycle owner's
        accepted terminal/exit-ACK event. No robot goal is submitted here.
        """
        if self.closed or not isinstance(goal_id,str) or not goal_id or type(goal_generation) is not int or goal_generation<0:
            return False
        identity=(goal_id,goal_generation)
        if identity==self.goal_identity: return True
        if identity in self.retired_goals or (self.goal_identity is not None and goal_generation<=self.goal_identity[1]):
            self.entries.clear(); return False
        if self.goal_identity is not None: self.retired_goals.add(self.goal_identity)
        self.goal_identity=identity
        self.entries.clear(); self.release_barrier=self.last_command
        return True

class LifecycleConstraintAdapter:
    """Actual D0 in-process wiring; lifecycle events remain external inputs.

    Never derives ACK from a returned constraint or from calling bind_goal.
    The supplied lifecycle is the traffic module's strict TrafficLifecycle.
    """
    def __init__(self, lifecycle):
        self.lifecycle=lifecycle
        self.adapter=ConstraintAdapter(lifecycle.run_id,lifecycle.step_id,lifecycle.generation,
                                       max_ttl=lifecycle.ttl,max_source_age=lifecycle.source_max_age)
        self.adapter.bind_goal(*lifecycle.approach)
        self.receiver_sequence=-1
        self.permission_snapshot=None

    def observe(self, observation, *, now, pose_age_s, **kwargs):
        result=self.lifecycle.observe(observation,now=now,pose_age_s=pose_age_s,**kwargs)
        if self.lifecycle.closed:
            self.adapter.close()
        elif self.lifecycle.exit_goal is not None and self.lifecycle.exit_ack_at is not None:
            self.adapter.bind_goal(*self.lifecycle.exit_goal)
        self.receiver_sequence+=1
        # A retained permission cannot outlive ANY evidence supporting it. GREEN
        # matters before departure, but not once this crossing is committed.
        ages=[getattr(observation,'observation_age_s',None),pose_age_s]
        if result.get('state')=='DEPART_PENDING':
            ages.append(getattr(observation,'signal_age_s',None))
        source_age=(max(ages)+max(0.,now-observation.receipt_s)
                    if all(finite_number(x) and x>=0 for x in ages)
                    and finite_number(now) and finite_number(getattr(observation,'receipt_s',None)) else float('inf'))
        self.adapter.ingest(result['motion_constraint'],sequence=self.receiver_sequence,
            receipt_s=now,now=now,source_age_s=source_age,
            producer_epoch=getattr(observation,'epoch',None),source_sequence=getattr(observation,'sequence',-1))
        self.permission_snapshot=self._lifecycle_snapshot()
        return result

    def _lifecycle_snapshot(self):
        f=self.lifecycle
        return (f.phase,f.closed,f.pending_fault,f.hold_request_id,f.hold_ack,
                f.exit_goal,f.exit_ack_at,f.exit_requested_at,f.core.state,f.core.start,
                f.event_epoch,f.event_sequence,f.core.seq,f.last_observation,f.last_now)

    def apply(self, *args, **kwargs):
        # Terminal/cancel/restart events take effect before the next sensor tick.
        # Revoke cached permission on any action-lifecycle transition, including
        # callers feeding the lifecycle directly. A new observation is required.
        if self.lifecycle.closed: self.adapter.close()
        if self.permission_snapshot!=self._lifecycle_snapshot(): self.adapter.entries.clear()
        return self.adapter.apply(*args,**kwargs)
