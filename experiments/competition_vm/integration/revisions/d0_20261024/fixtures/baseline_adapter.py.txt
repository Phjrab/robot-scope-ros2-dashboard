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
    def __init__(self, run_id, step_id, generation, owners=('traffic_vm',), max_ttl=.25):
        if not all(isinstance(x,str) and x for x in (run_id,step_id)) or type(generation) is not int or generation<0:
            raise ValueError('invalid session')
        if not owners or any(not isinstance(x,str) or not x for x in owners) or len(set(owners))!=len(owners):
            raise ValueError('invalid owners')
        if not finite_number(max_ttl) or max_ttl<=0: raise ValueError('invalid TTL')
        self.identity=(run_id,step_id,generation)
        self.owners=frozenset(owners); self.max_ttl=max_ttl
        self.entries={}; self.owner_seq={}; self.last_command=-1
        self.release_barrier=-1; self.arbiter=avoidance.CommandArbiter()
        self.last_now=None

    def ingest(self, constraint, *, sequence, receipt_s, now):
        owner=constraint.get('owner_id') if isinstance(constraint,dict) else None
        if not isinstance(owner,str) or owner not in self.owners:
            self.entries.clear(); return False
        self.entries.pop(owner,None)
        try:
            ttl=constraint['validity']['receipt_ttl_s']
            valid=(finite_number(now) and finite_number(receipt_s) and finite_number(ttl)
                   and 0<ttl<=self.max_ttl and 0<=now-receipt_s<=ttl
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
        self.entries[owner]=(mode,receipt_s,ttl)
        if mode=='RELEASE': self.release_barrier=self.last_command
        return True

    def apply(self, v, w, sequence, *, receipt_s, now, sensor_fresh, tf_fresh, estop=False, collision=False):
        # Clock rollback requires new evidence and command; no old RELEASE survives.
        valid_time=finite_number(now) and finite_number(receipt_s)
        rollback=valid_time and self.last_now is not None and now<self.last_now
        if rollback: self.entries.clear()
        if valid_time: self.last_now=now
        valid_command=(type(sequence) is int and 0<=sequence<2**63 and sequence>self.last_command
                       and sequence>self.release_barrier and valid_time and 0<=now-receipt_s<=self.max_ttl)
        if type(sequence) is int and 0<=sequence<2**63: self.last_command=max(self.last_command,sequence)
        fresh_release=(valid_time and all(owner in self.entries and self.entries[owner][0]=='RELEASE'
                          and 0<=now-self.entries[owner][1]<=self.entries[owner][2]
                          and receipt_s>=self.entries[owner][1] for owner in self.owners))
        bool_valid=all(type(x) is bool for x in (sensor_fresh,tf_fresh,estop,collision))
        if not valid_command or not bool_valid or rollback:
            return 0.,0.,'INVALID_OR_OLD_COMMAND'
        return self.arbiter.apply(v,w,sequence,sensor_fresh=sensor_fresh,tf_fresh=tf_fresh,
                                  estop=estop,collision=collision,signal_hold=not fresh_release)
