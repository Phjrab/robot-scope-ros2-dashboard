"""Synthetic lifecycle tests: no ROS, robot, or native registration is run."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

from robot_dashboard.relocalization import sensor_tracking_process as subject
from robot_dashboard.relocalization.external_global_observation import ExternalGlobalObservationRunner
from robot_dashboard.relocalization.v031_observation_compat import REVIEWED_HASHES, SELECTION_POLICY


FAKE_WORKER = r'''
import json, os, struct, sys, time
from pathlib import Path

def read(sock, count):
    data = b''
    while len(data) < count:
        piece = os.read(sock, count-len(data))
        if not piece: raise EOFError()
        data += piece
    return data

def receive(sock):
    length = struct.unpack('!I', read(sock, 4))[0]
    return json.loads(read(sock, length))

def send(sock, value):
    data = json.dumps(value, separators=(',', ':')).encode()
    packet = memoryview(struct.pack('!I', len(data)) + data)
    while packet: packet = packet[os.write(sock, packet):]

folder = Path(sys.argv[1])
config = json.loads((folder/'config.json').read_text())
mode = os.environ.get('SENSOR_FAKE_MODE', 'normal')
sock = int(sys.argv[2])
try:
    if mode == 'slow-start': time.sleep(2)
    send(sock, {'ready': True, 'map_sha256': config['context']['map']['sha256'],
                'reference_points': config['context']['map']['point_count'],
                'source_pin_sha256': config['pin_sha256']})
    while True:
        request = receive(sock)
        if request['operation'] == 'close':
            send(sock, {'closed': True})
            break
        if mode == 'late': time.sleep(2)
        if mode == 'oversize':
            os.write(sock, struct.pack('!I', 65537))
            continue
        context = request['context']
        candidate = {'gate_reasons': [], 'map_from_scan': request['seed_matrix'],
                     'rmse_m': .14, 'overlap': .94, 'scan_count': context['scan']['point_count'],
                     'inlier_count': context['scan']['point_count'],
                     'full_scan_rmse_m': .2, 'capped_full_rmse_m': .15,
                     'distinct_inlier_voxel_count': 100,
                     'geometry_min_max_eigen_ratio': .1,
                     'inlier_geometry_min_max_eigen_ratio': .1,
                     'refinement_stationary': True}
        result = {'status': 'OBSERVATION_ONLY_UNVERIFIED',
                  'map_frame': context['map_frame'], 'scan_frame': context['source_frame'],
                  'frame_id': context['source_frame'], 'session_id': context['observer_epoch'],
                  'observer_id': context['observer_id'], 'source_stamp_ns': context['source_stamp_ns'],
                  'map_id': 'sha256:'+context['map']['sha256'],
                  'map_revision': context['map_revision'],
                  'input_points': context['scan']['point_count'],
                  'reference_points': context['map']['point_count'],
                  'selected_candidate': 0, 'gate_reasons': [], 'candidates': [candidate],
                  'selection_policy': %s, 'source_pin_sha256': config['pin_sha256'],
                  'tracking_verified': False, 'body_pose': None, 'current_pose': None,
                  'map_from_scan': request['seed_matrix'], 'rmse_m': .14, 'overlap': .94}
        send(sock, {'sequence': request['sequence'], 'result': result})
finally:
    os.close(sock)
'''


class StubRunner(ExternalGlobalObservationRunner):
    def __init__(self):
        super().__init__(sys.executable, "/unused", "/unused")
        self.pin_sha = "a" * 64

    def _configuration(self):
        return Path(sys.executable), Path("/unused"), {"files": dict(REVIEWED_HASHES)}, self.pin_sha


def blob(points):
    raw = np.asarray(points, dtype="<f8").tobytes()
    return raw, {"encoding": "float64_le_xyz", "point_count": len(points),
                 "sha256": hashlib.sha256(raw).hexdigest()}


class SensorTrackingProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        worker = Path(self.temp.name) / "fake_worker.py"
        worker.write_text(FAKE_WORKER % repr(SELECTION_POLICY))
        patcher = mock.patch.object(subject, "_WORKER", worker)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.map_bytes, map_metadata = blob([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self.scan_bytes, scan_metadata = blob([[.1, .1, .1], [.2, .2, .2], [.3, .3, .3]])
        self.context = dict(map_id="saved", map_revision="r1", map_frame="camera_init",
                            source_frame="hesai_lidar", map=map_metadata, scan=scan_metadata,
                            observer_id="observer", observer_epoch="epoch", source_stamp_ns="1000")
        self.seed = np.eye(4).tolist()
        self.cancel = threading.Event()
        self.process = subject.SensorTrackingProcess(StubRunner())
        self.addCleanup(self.process.close)

    def _start(self, mode="normal"):
        with mock.patch.dict(os.environ, {"SENSOR_FAKE_MODE": mode}):
            self.process.start(self.map_bytes, self.context, self.cancel)

    def _align(self, mode="normal", **changes):
        with mock.patch.dict(os.environ, {"SENSOR_FAKE_MODE": mode}):
            return self.process.align(self.scan_bytes, {**self.context, **changes}, self.seed, self.cancel)

    def test_full_array_identity_and_high_rmse_observation_not_promoted(self):
        self._start()
        folder = Path(self.process._folder.name)
        result = self._align()
        self.assertEqual(list(folder.glob("scan-*.f64")), [])
        self._align(source_stamp_ns="1001")
        self.assertEqual(list(folder.glob("scan-*.f64")), [])
        self.assertEqual(result["input_points"], 3)
        self.assertEqual(result["reference_points"], 4)
        self.assertEqual(result["rmse_m"], .14)
        self.assertEqual(result["residual_comparisons"], [[False, False]])
        self.assertEqual(result["residual_comparison_scope"],
                         "STORED_RMSE_ONLY_NO_LOCAL_RESELECTION")
        self.assertEqual(result["source_stamp_ns"], "1000")
        self.assertFalse(result["tracking_verified"])
        self.assertIsNone(result["body_pose"])
        self.assertFalse(result["selection_policy"]["rmse_selection_gate_enabled"])
        self.assertTrue(self.process.close())
        self.assertFalse(folder.exists())

    def test_duplicate_stamp_epoch_and_map_changes_fail_closed(self):
        self._start()
        self._align()
        with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_SOURCE_STAMP_NOT_ADVANCING"):
            self._align()
        self.assertTrue(self.process.close())
        for change, reason in [({"observer_epoch": "new", "source_stamp_ns": "1001"}, "SENSOR_SOURCE_EPOCH_CHANGED"),
                               ({"map_revision": "r2"}, "SENSOR_MAP_OR_FRAME_CHANGED")]:
            with self.subTest(change=change):
                process = subject.SensorTrackingProcess(StubRunner())
                self.addCleanup(process.close)
                process.start(self.map_bytes, self.context, self.cancel)
                process.align(self.scan_bytes, self.context, self.seed, self.cancel)
                with self.assertRaisesRegex(subject.SensorTrackingError, reason):
                    process.align(self.scan_bytes, {**self.context, **change}, self.seed, self.cancel)

    def test_bad_hash_and_nonrigid_seed_never_reach_worker(self):
        self._start()
        with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_INPUT_OR_RESULT_INVALID"):
            self.process.align(self.scan_bytes[:-8] + b"abcdefgh", self.context, self.seed, self.cancel)
        self.assertTrue(self.process.close())
        process = subject.SensorTrackingProcess(StubRunner())
        self.addCleanup(process.close)
        process.start(self.map_bytes, self.context, self.cancel)
        bad = np.eye(4); bad[0, 0] = 2
        with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_SEED_NOT_RIGID"):
            process.align(self.scan_bytes, self.context, bad, self.cancel)

    def test_pin_change_after_initialization_fails_closed(self):
        runner = StubRunner()
        process = subject.SensorTrackingProcess(runner)
        self.addCleanup(process.close)
        process.start(self.map_bytes, self.context, self.cancel)
        runner.pin_sha = "b" * 64
        with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_SOURCE_PIN_CHANGED"):
            process.align(self.scan_bytes, self.context, self.seed, self.cancel)
        self.assertTrue(process.close())

    def test_spawn_failure_closes_inherited_channel_descriptors(self):
        descriptors = Path("/proc/self/fd")
        if not descriptors.is_dir():
            self.skipTest("Linux fd inventory unavailable")
        before = len(list(descriptors.iterdir()))
        with mock.patch.object(subject.subprocess, "Popen", side_effect=OSError("synthetic spawn failure")):
            with self.assertRaises(OSError):
                self.process.start(self.map_bytes, self.context, self.cancel)
        self.assertEqual(len(list(descriptors.iterdir())), before)
        self.assertTrue(self.process.close())

    def test_late_response_and_oversize_result_kill_worker(self):
        for mode, code in (("late", "SENSOR_DEADLINE_EXCEEDED"),
                           ("oversize", "SENSOR_RESULT_LIMIT_NO_TRUNCATION")):
            with self.subTest(mode=mode), mock.patch.dict(os.environ, {"SENSOR_FAKE_MODE": mode}):
                process = subject.SensorTrackingProcess(StubRunner())
                self.addCleanup(process.close)
                process.start(self.map_bytes, self.context, self.cancel)
                started = time.monotonic()
                with self.assertRaisesRegex(subject.SensorTrackingError, code):
                    process.align(self.scan_bytes, self.context, self.seed, self.cancel)
                self.assertLess(time.monotonic() - started, 1.3)
                self.assertTrue(process.close())

    def test_cancel_and_start_deadline_reap_owned_worker(self):
        with mock.patch.dict(os.environ, {"SENSOR_FAKE_MODE": "late"}):
            self.process.start(self.map_bytes, self.context, self.cancel)
            timer = threading.Timer(.04, self.cancel.set)
            timer.start()
            try:
                with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_CANCELLED"):
                    self.process.align(self.scan_bytes, self.context, self.seed, self.cancel)
            finally:
                timer.join()
        self.assertTrue(self.process.close())
        with mock.patch.object(subject, "START_DEADLINE_S", .08), mock.patch.dict(os.environ, {"SENSOR_FAKE_MODE": "slow-start"}):
            process = subject.SensorTrackingProcess(StubRunner())
            self.addCleanup(process.close)
            with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_DEADLINE_EXCEEDED"):
                process.start(self.map_bytes, self.context, threading.Event())
            self.assertTrue(process.close())

    def test_close_during_late_alignment_rejects_the_late_result(self):
        with mock.patch.dict(os.environ, {"SENSOR_FAKE_MODE": "late"}):
            self.process.start(self.map_bytes, self.context, self.cancel)
            outcome = []
            worker = threading.Thread(target=lambda: self._record_alignment(outcome))
            worker.start()
            time.sleep(.04)
            self.assertTrue(self.process.close())
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(outcome), 1)
            self.assertIsInstance(outcome[0], subject.SensorTrackingError)

    def _record_alignment(self, outcome):
        try:
            outcome.append(self.process.align(self.scan_bytes, self.context, self.seed, self.cancel))
        except Exception as exc:
            outcome.append(exc)


if __name__ == "__main__":
    unittest.main()
