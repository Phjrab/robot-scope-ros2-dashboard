"""Real private-process and completion-fence regressions; no ROS or robot."""
import copy
import os
import socket
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from test_observation_alignment import Agent, Catalog, inputs, request_body, REVISION, MAP_ID
from robot_dashboard.relocalization.observation_alignment import (
    ObservationAligner, ObservationAlignmentError, ReferenceIndex, solve_prepared,
)
from robot_dashboard.relocalization.observation_worker import Channel, RegistrationWorker


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.reference = np.random.default_rng(17).uniform(-3, 3, (1000, 3))
        self.points = self.reference[::5].copy()
        self.worker = RegistrationWorker()
        self.addCleanup(self.worker.close)

    def solve(self, *, key=('map', 'revision'), deadline=None):
        return self.worker.solve(key, self.reference, 'map', self.points, 'odom', 123456789,
                                 np.eye(4), time.monotonic() + 3 if deadline is None else deadline)

    def test_real_child_matches_inline_and_is_reused_for_fresh_scan(self):
        expected, transform = solve_prepared(self.reference, ReferenceIndex(self.reference), 'map',
            self.points, 'odom', 123456789, np.eye(4), time.monotonic() + 3)
        actual, actual_transform = self.solve()
        self.assertNotEqual(self.worker.process.pid, os.getpid())
        pid = self.worker.process.pid
        self.assertEqual(actual['status'], expected['status'])
        for key, value in expected['metrics'].items():
            if key != 'runtime_ms': self.assertEqual(actual['metrics'][key], value)
        np.testing.assert_allclose(actual_transform, transform, atol=1e-12)
        self.solve(key=('map', 'changed-revision'))
        self.assertEqual(self.worker.process.pid, pid)
        self.worker.close()
        self.assertIsNone(self.worker.process)

    def test_cold_preparation_timeout_never_retains_scan_result(self):
        with self.assertRaisesRegex(ObservationAlignmentError, 'BUDGET'):
            self.solve(deadline=time.monotonic())
        self.assertEqual(self.worker.phase, 'starting')
        self.assertEqual(self.worker.sequence, 0)
        result, _ = self.solve()
        self.assertEqual(result['query_stamp_ns'], 123456789)
        self.assertEqual(self.worker.sequence, 1)

    def test_timeout_after_request_send_discards_child_and_late_result(self):
        self.solve()
        old = self.worker.process
        with patch.object(self.worker.channel, 'receive', side_effect=TimeoutError):
            with self.assertRaisesRegex(ObservationAlignmentError, 'BUDGET'):
                self.solve()
        self.assertIsNotNone(old.poll())
        self.assertIsNone(self.worker.process)
        self.solve()
        self.assertNotEqual(self.worker.process.pid, old.pid)

    def test_dead_child_fails_closed_then_can_be_replaced(self):
        self.solve()
        self.worker.process.kill(); self.worker.process.wait()
        with self.assertRaisesRegex(ObservationAlignmentError, 'UNAVAILABLE'):
            self.solve()
        self.solve()

    def test_wrong_response_identity_is_never_returned(self):
        self.solve()
        with patch.object(self.worker.channel, 'receive', return_value=('result', ('wrong', 'map'), 2, None, {})):
            with self.assertRaisesRegex(ObservationAlignmentError, 'UNAVAILABLE'):
                self.solve()
        self.assertIsNone(self.worker.process)

    def test_partial_ipc_response_retained_only_until_complete(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close); self.addCleanup(right.close)
        reader, writer = Channel(left), Channel(right)
        with self.assertRaises(TimeoutError): reader.receive(time.monotonic() + .005)
        payload = {'data': b'x' * 300000}
        task = threading.Thread(target=writer.send, args=(payload, time.monotonic() + 2))
        task.start()
        self.assertEqual(reader.receive(time.monotonic() + 2), payload)
        task.join(2); self.assertFalse(task.is_alive())

    def test_backpressured_send_obeys_deadline(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close); self.addCleanup(right.close)
        left.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        writer = Channel(left)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            writer.send(b'x' * 3000000, started + .05)
        self.assertLess(time.monotonic() - started, .5)


class IsolatedFenceTests(unittest.TestCase):
    def test_parent_revalidates_after_isolated_success(self):
        cloud, pose = inputs()
        reference = np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3)
        # Prewarm using synthetic numerical inputs, then change actual parent
        # state during child work; no fixture timestamp is made into live data.
        aligner = ObservationAligner(isolated=True)
        self.addCleanup(aligner.close)
        worker = aligner.worker
        worker.solve((MAP_ID, REVISION), reference, 'map', reference, 'odom', 123,
                     np.eye(4), time.monotonic() + 3)
        for kind, reason in (('map', 'MAP_CHANGED'), ('cloud', 'SOURCE_CHANGED'),
                             ('pose', 'POSE_SOURCE_CHANGED'), ('stale', 'STALE_INPUT'),
                             ('deadline', 'BUDGET')):
            cloud, pose = inputs(reference)
            agent, catalog = Agent(cloud, pose), Catalog(reference)
            original_solve = worker.solve
            def changed(*args):
                result = original_solve(*args)
                if kind == 'map': catalog.revision = '0' * 64
                elif kind in ('cloud', 'pose'):
                    getattr(agent, kind)['observation']['publisher_epoch'] = '0' * 32
                elif kind == 'stale':
                    # The actual selected pair is copied, so advance the clock
                    # rather than mutating only the newest sample.
                    clock.return_value = time.monotonic() + 1.1
                elif kind == 'deadline': clock.return_value = time.monotonic() + .7
                return result
            aligner.last_started = float('-inf')
            real_clock = time.monotonic
            with patch.object(worker, 'solve', side_effect=changed), patch(
                'robot_dashboard.relocalization.observation_alignment.time.monotonic', wraps=real_clock) as clock:
                with self.subTest(kind=kind), self.assertRaisesRegex(ObservationAlignmentError, reason):
                    aligner.estimate(catalog, agent, request_body())
        aligner.close()
        with self.assertRaisesRegex(ObservationAlignmentError, 'CLOSED'):
            aligner.estimate(catalog, agent, request_body())


class ShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_failure_does_not_skip_dataset_cleanup(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from robot_dashboard.application.runtime import close_observation_resources
        worker, capture, logger = Mock(), Mock(), Mock()
        worker.close.side_effect = RuntimeError('synthetic-close-failure')
        await close_observation_resources(SimpleNamespace(observation_aligner=worker, dataset_capture=capture), logger)
        worker.close.assert_called_once_with()
        capture.close.assert_called_once_with()
        logger.exception.assert_called_once()


class PreparationTests(unittest.TestCase):
    def test_only_immutable_reference_survives_slow_preparation(self):
        worker = RegistrationWorker(); self.addCleanup(worker.close)
        reference = np.random.default_rng(22).uniform(-2, 2, (180, 3))
        worker._start()
        self.assertEqual(worker.channel.receive(time.monotonic() + 3), ('ready',))
        worker.phase = 'ready'
        with patch.object(worker.channel, 'receive', side_effect=TimeoutError):
            with self.assertRaisesRegex(ObservationAlignmentError, 'BUDGET'):
                worker.solve(('map', 'old'), reference, 'map', reference, 'odom', 101,
                             np.eye(4), time.monotonic() + .6)
        self.assertEqual(worker.phase, 'preparing')
        self.assertEqual(worker.sequence, 0)
        # A new map and source stamp must replace all old request inputs.
        result, _ = worker.solve(('map', 'new'), reference, 'map', reference, 'odom', 202,
                                 np.eye(4), time.monotonic() + 3)
        self.assertEqual(result['query_stamp_ns'], 202)
        self.assertEqual(worker.key, ('map', 'new'))
