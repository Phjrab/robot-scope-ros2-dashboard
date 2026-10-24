import os,sys,time,threading,json
sys.path.insert(0,'/workspace/scratch/b09eacf6919d/robot-scope-left-slalom-20261024/experiments/competition_vm/arena_robot_sim/revisions/planning_watchdog_20261024')
from runtime_guard import CommandGate,PlannerProcess

def quick(): return ['plan']
class DelayedReceive:
 def __init__(self,conn,delay=0,entered=None,resume=None): self.conn=conn;self.delay=delay;self.entered=entered;self.resume=resume
 def poll(self): return self.conn.poll()
 def recv(self):
  if self.entered:self.entered.set()
  if self.resume:self.resume.wait(1)
  time.sleep(self.delay)
  return self.conn.recv()
 def close(self):self.conn.close()

out={}
g=CommandGate().start();p=PlannerProcess(g,budget=.1);p.launch(quick,(),time.monotonic())
while not p.conn.poll():time.sleep(.001)
p.conn=DelayedReceive(p.conn,delay=.13);result=p.poll()
out['post_budget_receive']={'status':p.status,'elapsed_s':time.monotonic()-p.started,'budget_s':p.budget,'result':result,'output':g.tick()}
p.cleanup();g.close()
g=CommandGate().start();p=PlannerProcess(g,budget=.1);p.launch(quick,(),time.monotonic())
while not p.conn.poll():time.sleep(.001)
entered=threading.Event();resume=threading.Event();p.conn=DelayedReceive(p.conn,entered=entered,resume=resume)
t=threading.Thread(target=p.poll);t.start();assert entered.wait(1);p.cancel();before=p.status;resume.set();t.join(1)
out['cancel_during_receive']={'before_receive_resumes':before,'after_receive_resumes':p.status,'result':p.result,'output':g.tick()}
p.cleanup();g.close()
print(json.dumps(out,indent=2))
