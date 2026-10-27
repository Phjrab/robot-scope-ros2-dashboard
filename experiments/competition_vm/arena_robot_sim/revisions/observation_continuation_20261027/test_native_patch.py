"""Execute the actual patched runner loop with mocks, not a replacement loop.

Set C3_SOURCE_CHECKOUT to a read-only pinned source checkout to run these cases.
No ROS import/init, native process, sensor, socket, goal or actuator is executed.
"""
import ast
import importlib.util
import math
import os
from pathlib import Path
import shutil
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from apply_patch import apply
from observation import Observer, Sample

SOURCE = os.environ.get('C3_SOURCE_CHECKOUT')


@unittest.skipUnless(SOURCE, 'C3_SOURCE_CHECKOUT required for exact-source patch tests')
class NativePatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        target = self.root / 'experiments/competition_nav2/native_runner.py'
        target.parent.mkdir(parents=True)
        shutil.copyfile(Path(SOURCE) / 'experiments/competition_nav2/native_runner.py', target)
        self.patched = apply(self.root)
        self.source = self.patched.read_text()

    def tearDown(self): self.temp.cleanup()

    def run_loop(self, status=6, fault=None, contact=False, goal=False, shutdown_after=None, done_after=2):
        node = SimpleNamespace(sim_t=0., goal_start=0., pose=(0., 0., 0.),
            boundary=SimpleNamespace(fault=fault), raw_contact_observed=contact,
            collision_count=int(fault == 'FOOTPRINT_CONTACT'), boundary_count=0,
            previous_output=(0., 0., 0.), audit_graph=lambda: None)
        clock = SimpleNamespace(value=10.)
        calls = []
        def spin(*args, **kwargs):
            clock.value += .05
            node.sim_t += .05
            calls.append('observation_tick')
        future = SimpleNamespace(done=lambda: len(calls) >= done_after,
                                 result=lambda: SimpleNamespace(status=status))
        fixture = dict(timeout_s=.5, goal=(0., 0., 0.) if goal else (5., 0., 0.))
        scope = dict(node=node, fixture=fixture, time=SimpleNamespace(monotonic=lambda: clock.value),
            rclpy=SimpleNamespace(spin_once=spin, ok=lambda: shutdown_after is None or len(calls) < shutdown_after), executor=None, math=math, omni=True,
            result_future=future, deadline=26., report={}, Observer=Observer, Sample=Sample)
        start = self.source.index('        observation_started =')
        end = self.source.index('        if not result_future.done():', start)
        exec(compile(textwrap.dedent(self.source[start:end]), str(self.patched), 'exec'), scope)
        return scope['report']['observation_lifecycle'], len(calls), node

    def test_actual_abort_loop_observes_to_budget_without_restart(self):
        r, ticks, _ = self.run_loop()
        self.assertGreaterEqual(ticks, 10)
        self.assertEqual(r['terminal_reason'], 'OBSERVATION_TIMEOUT')
        self.assertGreater(r['post_action_observation_s'], .3)
        self.assertIsNotNone(r['action_terminal_observed_elapsed_s'])
        self.assertNotIn('send_goal_async', self.source[self.source.index('        observation_started ='):self.source.index('        if not result_future.done():', self.source.index('        observation_started ='))].replace('client.send_goal_async(request)', 'existing_recovery_probe'))

    def test_padded_fault_latch_preserved_but_observer_continues(self):
        r, ticks, node = self.run_loop(fault='FOOTPRINT_CONTACT')
        self.assertGreaterEqual(ticks, 10)
        self.assertEqual(node.boundary.fault, 'FOOTPRINT_CONTACT')
        self.assertEqual(r['safety_evaluation'], 'FAIL_PADDED_ENVELOPE')
        self.assertGreater(r['sample_count'], 2)
        self.assertEqual(r['terminal_reason'], 'OBSERVATION_TIMEOUT')

    def test_raw_contact_terminates(self):
        r, ticks, _ = self.run_loop(contact=True)
        self.assertEqual(ticks, 1)
        self.assertEqual(r['terminal_reason'], 'RAW_CONTACT')

    def test_infrastructure_fault_terminates(self):
        r, ticks, _ = self.run_loop(fault='SENSOR_STALE')
        self.assertEqual(ticks, 1)
        self.assertEqual(r['terminal_reason'], 'INFRASTRUCTURE_ERROR')

    def test_goal_success_terminates(self):
        r, ticks, _ = self.run_loop(status=4, goal=True)
        self.assertEqual(ticks, 2)
        self.assertEqual(r['terminal_reason'], 'GOAL_REACHED')

    def test_success_at_sim_deadline_is_not_goal_reached(self):
        r, ticks, _ = self.run_loop(status=4, goal=True, done_after=11)
        self.assertEqual(r["terminal_reason"], "OBSERVATION_TIMEOUT")
        self.assertFalse(r["goal_reached"])

    def test_cancelled_action_does_not_restart(self):
        r, ticks, _ = self.run_loop(status=5)
        self.assertGreaterEqual(ticks, 10)
        self.assertEqual(r['terminal_reason'], 'OBSERVATION_TIMEOUT')

    def test_ros_shutdown_ends_observation_distinctly(self):
        r, ticks, _ = self.run_loop(shutdown_after=3, contact=None)
        self.assertEqual(ticks, 3)
        self.assertEqual(r['terminal_reason'], 'OPERATOR_CANCEL')
        self.assertEqual(r['safety_evaluation'], 'INPUT_REQUIRED')

    def test_raw_body_geometry_not_padded_counter(self):
        import sys
        sys.path.insert(0, str(Path(SOURCE) / 'experiments/competition_nav2'))
        try:
            from core import rectangle
            tree = ast.parse(self.source)
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'raw_body_contact')
            scope = {}
            exec(compile(ast.Module(body=[function], type_ignores=[]), 'raw-contact', 'exec'), scope)
            world = SimpleNamespace(raw_body=rectangle(-.405, -.28, .405, .28),
                boundary=rectangle(-1., -1., 1., 1.), forbidden=[], obstacles=lambda t: [])
            contact = scope['raw_body_contact']
            # Padded half-width .31 crosses y=1 here; raw half-width .28 does not.
            self.assertFalse(contact(world, [(0., .70, 0.)], 0.))
            self.assertTrue(contact(world, [(0., .73, 0.)], 0.))
            world.obstacles = lambda t: [rectangle(.39, -.1, .5, .1)]
            self.assertTrue(contact(world, [(0., 0., 0.)], 0.))
        finally:
            sys.path.pop(0)

    def test_source_drift_or_existing_helper_rejected(self):
        with self.assertRaises(ValueError): apply(self.root)

    def test_original_safety_and_actuation_blocks_byte_preserved(self):
        original=(Path(SOURCE) / 'experiments/competition_nav2/native_runner.py').read_text()
        for begin, end in [('            if any(self.world.collision(p, scene_time)', '            self.pose ='),
                           ('        def receive_command(', '        def tick(')]:
            self.assertIn(begin, original)
            self.assertEqual(original[original.index(begin):original.index(end, original.index(begin))],
                    self.source[self.source.index(begin):self.source.index(end, self.source.index(begin))])

    def test_raw_contact_unknown_on_unsupported_world(self):
        tree=ast.parse(self.source)
        function=next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='raw_body_contact')
        scope={}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'raw-contact', 'exec'), scope)
        self.assertIsNone(scope['raw_body_contact'](SimpleNamespace(), [], 0.))


if __name__ == '__main__': unittest.main()
