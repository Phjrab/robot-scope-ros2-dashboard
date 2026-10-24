import unittest,time,json,threading
from pathlib import Path
from runtime_guard import CommandGate,PlannerProcess,Identity
REPORT=[]
def stall(seconds):time.sleep(seconds);return ['planned']
def cpu_stall(seconds):
 end=time.monotonic()+seconds;n=0
 while time.monotonic()<end:n+=1
 return n
class Runtime(unittest.TestCase):
 def setUp(self):self.g=CommandGate().start()
 def tearDown(self):self.assertTrue(self.g.close())
 def prime(self):
  now=time.monotonic();self.assertTrue(self.g.observe(now,now));self.assertTrue(self.g.submit(1,(.1,0,0),self.g.identity));self.assertEqual(self.g.tick()['command'],[.1,0,0])
 def test_command_lease_survives_controller_stall(self):
  self.prime();start=time.monotonic();time.sleep(.18);r=self.g.tick();self.assertEqual(r['command'],[0,0,0]);self.assertEqual(r['reason'],'COMMAND_EXPIRED')
  stop=next(x['wall_time'] for x in self.g.records if x['wall_time']>=start and x['command']==[0,0,0]);REPORT.append({'test':'controller_stall','first_zero_elapsed_s':stop-start,'elapsed_s':time.monotonic()-start});self.assertLess(stop-start,.15)
 def test_planner_timeout_does_not_replay(self):
  self.prime();p=PlannerProcess(self.g);start=time.monotonic();p.launch(stall,(.6,),start)
  while p.status=='PENDING':p.poll();time.sleep(.005)
  self.assertEqual(p.status,'TIMEOUT');self.assertEqual(self.g.tick()['command'],[0,0,0]);self.assertTrue(p.cleanup());REPORT.append({'test':'planner_timeout','elapsed_s':time.monotonic()-start,'status':p.status})
 def test_cpu_planner_gil_isolated(self):
  self.prime();p=PlannerProcess(self.g);start=time.monotonic();p.launch(cpu_stall,(.6,),start)
  while p.status=='PENDING':p.poll();time.sleep(.005)
  self.assertEqual(p.status,'TIMEOUT');self.assertTrue(p.cleanup());rows=[r for r in self.g.records if r['wall_time']>=start];self.assertGreater(len(rows),3);self.assertTrue(all(r['command']==[0,0,0] for r in rows));REPORT.append({'test':'cpu_busy_worker','elapsed_s':time.monotonic()-start,'zero_samples':len(rows)})
 def test_ready_still_requires_new_command(self):
  self.prime();p=PlannerProcess(self.g);p.launch(stall,(.01,),time.monotonic())
  while p.status=='PENDING':p.poll();time.sleep(.002)
  self.assertEqual(p.status,'READY');self.assertEqual(self.g.tick()['command'],[0,0,0]);self.assertTrue(p.cleanup())
 def test_duplicate_command_rejected(self):self.prime();self.assertFalse(self.g.submit(1,(.1,0,0),self.g.identity))
 def test_old_source_new_receipt_rejected(self):
  now=time.monotonic();self.assertFalse(self.g.observe(now-.30,now,now));self.assertEqual(self.g.tick()['command'],[0,0,0])
 def test_observation_gap_independent(self):
  now=time.monotonic();self.assertFalse(self.g.observe(now,now-.60,now))
 def test_receiver_expiry_even_command_new(self):
  self.prime();time.sleep(.28);self.g.submit(2,(.1,0,0),self.g.identity);self.assertEqual(self.g.tick()['reason'],'RECEIVER_STALE')
 def test_identity_change_cancels_worker(self):
  self.prime();p=PlannerProcess(self.g);p.launch(stall,(.5,),time.monotonic());self.g.change_identity(Identity(generation=2));p.poll();self.assertEqual(p.status,'IDENTITY_CHANGED');self.assertTrue(p.cleanup());self.assertEqual(self.g.tick()['command'],[0,0,0])
 def test_identity_invalidates_old_sensor(self):
  self.prime();self.g.change_identity(Identity(generation=2));self.g.submit(1,(.1,0,0),self.g.identity);self.assertEqual(self.g.tick()['reason'],'RECEIVER_STALE')
 def test_stale_snapshot_launch_rejected(self):
  p=PlannerProcess(self.g)
  with self.assertRaises(ValueError):p.launch(stall,(.01,),time.monotonic()-.3)
 def test_completed_but_source_stale_result_rejected(self):
  p=PlannerProcess(self.g,budget=.4);p.launch(stall,(.27,),time.monotonic())
  while p.status=='PENDING':p.poll();time.sleep(.005)
  self.assertEqual(p.status,'STALE_RESULT');self.assertTrue(p.cleanup());self.assertEqual(self.g.tick()['command'],[0,0,0])
 def test_receive_delay_cannot_commit_late_result(self):
  p=PlannerProcess(self.g);p.launch(stall,(.001,),time.monotonic());original=p.conn
  while not original.poll():time.sleep(.001)
  class Slow:
   def poll(self):return original.poll()
   def recv(self):time.sleep(.13);return original.recv()
   def close(self):original.close()
  p.conn=Slow();self.assertIsNone(p.poll());self.assertEqual(p.status,'TIMEOUT');self.assertIsNone(p.result);self.assertTrue(p.cleanup())
 def test_cancel_during_receive_not_overwritten(self):
  p=PlannerProcess(self.g,budget=.4);p.launch(stall,(.001,),time.monotonic());original=p.conn;entered=threading.Event();release=threading.Event()
  while not original.poll():time.sleep(.001)
  class Paused:
   def poll(self):return original.poll()
   def recv(self):entered.set();release.wait(.3);return original.recv()
   def close(self):original.close()
  p.conn=Paused();thread=threading.Thread(target=p.poll);thread.start();self.assertTrue(entered.wait(.1));p.cancel();release.set();thread.join(.4);self.assertFalse(thread.is_alive());self.assertEqual(p.status,'CANCELLED');self.assertIsNone(p.result);self.assertTrue(p.cleanup())
 def test_explicit_cancel(self):
  self.prime();p=PlannerProcess(self.g);p.launch(stall,(.5,),time.monotonic());p.cancel();self.assertEqual(p.status,'CANCELLED');self.assertTrue(p.cleanup());self.assertEqual(self.g.tick()['command'],[0,0,0])
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Runtime);r=unittest.TextTestRunner(verbosity=2).run(suite);Path('wall_clock_results.json').write_text(json.dumps(REPORT,indent=2));raise SystemExit(not r.wasSuccessful())
