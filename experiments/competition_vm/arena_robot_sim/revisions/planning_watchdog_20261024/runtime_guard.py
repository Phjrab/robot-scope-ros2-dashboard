"""VM real-clock harness only. Never connects to an actuator or native ROS.
Separate planning process + independently ticking command lease gate.
Not a hard-real-time or physical braking guarantee.
"""
import math,multiprocessing as mp,threading,time
from dataclasses import dataclass

@dataclass(frozen=True)
class Identity:
 epoch:str='run-1'
 map_revision:str='corridor-parallel-20261024-v1'
 generation:int=1

class CommandGate:
 def __init__(self,identity=Identity(),period=.01,receiver_ttl=.25,source_age=.25,observation_gap=.50,command_lease=.10):
  self.identity=identity;self.period=period;self.receiver_ttl=receiver_ttl;self.source_age=source_age;self.observation_gap=observation_gap;self.command_lease=command_lease
  self.lock=threading.Lock();self.last_sequence=-1;self.receipt=-math.inf;self.source=-math.inf;self.observation=-math.inf;self.command_time=-math.inf;self.command=(0.,0.,0.);self.planning=False;self.closed=False;self.records=[];self.thread=None
 def observe(self,source_time,observation_time,receipt_time=None):
  now=time.monotonic();receipt_time=now if receipt_time is None else receipt_time
  if not all(math.isfinite(x) and 0<=now-x<=limit for x,limit in [(receipt_time,self.receiver_ttl),(source_time,self.source_age),(observation_time,self.observation_gap)]):return False
  with self.lock:
   if source_time<=self.source or observation_time<=self.observation:return False
   self.receipt=receipt_time;self.source=source_time;self.observation=observation_time
  return True
 def submit(self,sequence,command,identity):
  now=time.monotonic()
  with self.lock:
   if identity!=self.identity or type(sequence)is not int or sequence<=self.last_sequence or len(command)!=3 or not all(math.isfinite(x) for x in command):return False
   self.last_sequence=sequence;self.command=tuple(command);self.command_time=now
  return True
 def set_planning(self,value):
  with self.lock:
   self.planning=value
   # A completed/cancelled planner cannot revive the pre-planning command.
   self.command=(0.,0.,0.);self.command_time=-math.inf
 def change_identity(self,identity):
  with self.lock:
   self.identity=identity;self.command=(0.,0.,0.);self.command_time=-math.inf;self.last_sequence=-1;self.receipt=-math.inf;self.source=-math.inf;self.observation=-math.inf
 def tick(self):
  now=time.monotonic()
  with self.lock:
   reason='FOLLOWING'
   for invalid,label in [(self.closed,'CLOSED'),(self.planning,'PLANNING_HOLD'),(now-self.receipt>self.receiver_ttl,'RECEIVER_STALE'),(now-self.source>self.source_age,'SOURCE_STALE'),(now-self.observation>self.observation_gap,'OBSERVATION_GAP'),(now-self.command_time>self.command_lease,'COMMAND_EXPIRED')]:
    if invalid:reason=label;break
   cmd=self.command if reason=='FOLLOWING' else (0.,0.,0.)
   row={'wall_time':now,'command':list(cmd),'reason':reason};self.records.append(row)
  return row
 def start(self):
  def loop():
   while not self.closed:self.tick();time.sleep(self.period)
   self.tick()
  self.thread=threading.Thread(target=loop,daemon=True);self.thread.start();return self
 def close(self):
  self.closed=True
  if self.thread:self.thread.join(.5)
  return self.thread is None or not self.thread.is_alive()

def _worker(conn,fn,args,identity,source_time):
 try:conn.send({'identity':identity,'source_time':source_time,'result':fn(*args),'error':None})
 except BaseException as e:conn.send({'identity':identity,'source_time':source_time,'result':None,'error':type(e).__name__+': '+str(e)})
 finally:conn.close()

class PlannerProcess:
 def __init__(self,gate,budget=.1):
  self.gate=gate;self.budget=budget;self.process=None;self.conn=None;self.status='IDLE';self.result=None;self.lock=threading.RLock();self.token=0
 def launch(self,fn,args,source_time):
  with self.lock:
   if self.process and self.process.is_alive():raise RuntimeError('one pending planner only')
   if not math.isfinite(source_time) or not 0<=time.monotonic()-source_time<=self.gate.source_age:raise ValueError('stale or invalid snapshot source time')
   self.gate.set_planning(True);self.result=None;self.identity=self.gate.identity;self.started=time.monotonic();self.token+=1
   self.conn,child=mp.get_context('fork').Pipe(duplex=False)
   self.process=mp.get_context('fork').Process(target=_worker,args=(child,fn,args,self.identity,source_time),daemon=True);self.process.start();child.close();self.status='PENDING'
 def cancel(self,reason='CANCELLED'):
  with self.lock:
   if self.status!='PENDING':return
   self.status=reason;self.result=None;self.token+=1;self.gate.set_planning(False)
   if self.process and self.process.is_alive():self.process.terminate()
   # No blocking join on the command/watchdog path.
 def poll(self):
  with self.lock:
   if self.status!='PENDING':return None
   token=self.token;conn=self.conn
   if self.gate.identity!=self.identity:self.cancel('IDENTITY_CHANGED');return None
   if time.monotonic()-self.started>self.budget:self.cancel('TIMEOUT');return None
  # Never hold planner lock over receive: cancel must be able to invalidate it.
  if conn.poll():
   try:data=conn.recv()
   except (EOFError,OSError):
    with self.lock:
     if self.status=='PENDING' and token==self.token:self.cancel('WORKER_EXITED')
    return None
   with self.lock:
    if self.status!='PENDING' or token!=self.token:return None
    if time.monotonic()-self.started>self.budget:self.cancel('TIMEOUT');return None
    # Gate identity commit is atomic with identity changes.
    with self.gate.lock:
     invalid_identity=data['identity']!=self.gate.identity
     if not invalid_identity and 0<=time.monotonic()-data['source_time']<=self.gate.source_age and not data['error']:
      self.result=data['result'];self.status='READY';self.gate.planning=False;self.gate.command=(0.,0.,0.);self.gate.command_time=-math.inf
      return self.result
    self.cancel('IDENTITY_CHANGED' if invalid_identity else 'WORKER_ERROR' if data['error'] else 'STALE_RESULT');return None
  with self.lock:
   if self.status=='PENDING' and token==self.token and not self.process.is_alive():self.cancel('WORKER_EXITED')
  return None
 def cleanup(self):
  self.cancel()
  if self.process:
   self.process.join(.2)
   if self.process.is_alive():self.process.kill();self.process.join(.2)
  if self.conn:self.conn.close()
  return not self.process or not self.process.is_alive()
