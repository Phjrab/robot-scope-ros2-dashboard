"""Exact solver input preservation, entirely synthetic and hardware-free."""
import base64
import copy
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.relocalization.observation_alignment import ObservationAligner, project_query
from robot_dashboard.relocalization.observation_capture import (
    MAX_CAPTURE_BYTES, decode_capture, replay_capture,
)
from scripts import observation_capture as cli
from test_observation_alignment import Agent, Catalog, inputs, request_body


class CaptureTests(unittest.TestCase):
    def capture(self, *, raw=False, count=1200, include_sequence=True):
        reference = np.random.default_rng(71).uniform(-2, 2, (count, 3))
        cloud, pose = inputs(reference)
        if not include_sequence:
            pose.pop('seq')
        if raw:
            cloud.update(topic='/velodyne_points', pipeline_stage='converted', frame_id='sensor',
                         robot_pose_in_frame=dict(x=.1, y=0, z=0, roll=0, pitch=0, yaw=.2,
                                                  frame_id='sensor', source='configured_sensor_extrinsic'))
        query, _, _ = project_query(cloud, pose, time.monotonic())
        # Raw projection reference matches the actual projected query exactly.
        if raw:
            reference = query.copy()
        with closing(ObservationAligner()) as aligner:
            result = aligner.estimate(Catalog(reference), Agent(cloud, pose), request_body() | {'capture_inputs': True})
        return result, reference, query, cloud, pose

    def test_exact_f64_arrays_original_stamp_paired_pose_and_seed_survive_round_trip(self):
        for raw, include_sequence in ((False, True), (True, True), (False, False)):
            result, reference, query, cloud, pose = self.capture(raw=raw, include_sequence=include_sequence)
            stored = json.loads(json.dumps(result, allow_nan=False))
            value, actual_reference, actual_query, seed = decode_capture(stored)
            np.testing.assert_array_equal(actual_reference, reference)
            np.testing.assert_array_equal(actual_query, query)
            np.testing.assert_array_equal(seed, np.eye(4))
            self.assertLessEqual(len(actual_query), 512)
            self.assertEqual(value['source']['source_stamp_ns'], cloud['observation']['source_stamp_ns'])
            self.assertEqual(value['source']['pose_source_stamp_ns'], pose['observation']['source_stamp_ns'])
            self.assertEqual(value['paired_pose']['position'], pose['position'])
            self.assertEqual('seq' in value['paired_pose'], include_sequence)
            pose['position']['x'] = 999
            self.assertNotEqual(value['paired_pose']['position']['x'], 999)
            self.assertEqual(value['operational_application'], 'NOT_RUN')

    def test_default_path_does_not_encode_or_capture(self):
        cloud, pose = inputs()
        reference = np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3)
        with patch('robot_dashboard.relocalization.observation_capture.capture_inputs', side_effect=AssertionError('unexpected capture')):
            result = ObservationAligner().estimate(Catalog(reference), Agent(cloud, pose), request_body())
        self.assertNotIn('input_capture', result)

    def test_rejected_assessment_is_preserved_and_replay_never_changes_the_original(self):
        result, *_ = self.capture(count=180)
        from robot_dashboard.relocalization.observation_alignment import solve_prepared
        def nonconverged(*args, **kwargs):
            original, transform = solve_prepared(*args, **kwargs)
            original.update(status='REJECTED', reason='NOT_CONVERGED')
            original['metrics'].update(converged=False, iterations=40)
            return original, transform
        with patch('robot_dashboard.relocalization.observation_alignment.solve_prepared', side_effect=nonconverged):
            rejected, *_ = self.capture(count=180)
        self.assertEqual(rejected['reason'], 'NOT_CONVERGED')
        decode_capture(rejected)
        original = copy.deepcopy(rejected)
        replay = replay_capture(rejected)
        self.assertEqual(rejected, original)
        self.assertEqual(replay['original']['reason'], 'NOT_CONVERGED')
        self.assertEqual(replay['original'], {key: value for key, value in rejected.items() if key != 'input_capture'})
        self.assertFalse(replay['current_pose_valid'])
        self.assertEqual(replay['operational_application'], 'NOT_RUN')
        again = replay_capture(result)
        self.assertEqual(again['replay']['metrics']['iterations'], result['metrics']['iterations'])
        self.assertAlmostEqual(again['replay']['metrics']['rmse_m'], result['metrics']['rmse_m'], places=12)
        np.testing.assert_allclose(again['replay']['T_map_odom'], result['T_map_odom'], atol=1e-12)

    def test_corrupt_oversized_nonfinite_or_mismatched_records_are_refused(self):
        result, *_ = self.capture(count=180)
        variants = []
        for key, replacement in [('data', '!!!!'), ('sha256', '0' * 64), ('point_count', 100_001)]:
            value = copy.deepcopy(result); value['input_capture']['query'][key] = replacement; variants.append(value)
        value = copy.deepcopy(result); value['input_capture']['map']['revision'] = 'e' * 64; variants.append(value)
        value = copy.deepcopy(result); value['input_capture']['source']['source_stamp_ns'] = '1'; variants.append(value)
        value = copy.deepcopy(result)
        query = value['input_capture']['query']
        data = bytearray(base64.b64decode(query['data'])); data[:8] = np.asarray([float('nan')], dtype='<f8').tobytes()
        query.update(data=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest()); variants.append(value)
        for value in variants:
            with self.assertRaises(ValueError):
                decode_capture(value)

    def test_maximum_array_record_remains_bounded_without_running_large_icp(self):
        from robot_dashboard.relocalization.observation_capture import capture_inputs
        result, *_ = self.capture(count=180)
        value = result['input_capture']
        maximum = capture_inputs(identifier=result['map_id'], revision=result['map_revision'],
            reference=np.zeros((100_000, 3)), target_frame='map', points=np.zeros((512, 3)), frame='odom',
            seed=np.eye(4), pose=value['paired_pose'], source=result['source'])
        result.update(input_capture=maximum, reference_points=100_000, query_points=512)
        self.assertLess(len(json.dumps(result).encode()), MAX_CAPTURE_BYTES)
        decode_capture(result)

    def test_cli_replay_is_offline_and_refuses_overwrite_and_repository_output(self):
        result, *_ = self.capture(count=180)
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'input.json', Path(tmp)/'replay.json'
            cli.save(source, result)
            with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network used')):
                cli.main(['replay', str(source), '--output', str(output)])
            self.assertEqual(cli.read_json(output)['data_kind'], 'HISTORICAL_NUMERICAL_REPLAY')
            self.assertEqual(source.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, 'ALREADY_EXISTS'):
                cli.save(source, result)
            with self.assertRaisesRegex(ValueError, 'OUTSIDE_REPOSITORY'):
                cli.save(cli.REPO/'should-not-exist-capture.json', result)
            with self.assertRaisesRegex(ValueError, 'INPUT_SIZE_LIMIT'):
                cli.read_json(source, 10)

    def test_isolated_solver_capture_replays_the_same_reference_and_query(self):
        from test_observation_alignment import MAP_ID, REVISION
        reference = np.random.default_rng(8).uniform(-2, 2, (180, 3))
        with closing(ObservationAligner(isolated=True)) as aligner:
            aligner.worker.solve((MAP_ID, REVISION), reference, 'map', reference, 'odom', 123,
                                 np.eye(4), time.monotonic() + 3)
            cloud, pose = inputs(reference)
            result = aligner.estimate(Catalog(reference), Agent(cloud, pose), request_body() | {'capture_inputs': True})
        replay = replay_capture(result)
        self.assertEqual(result['metrics']['iterations'], replay['replay']['metrics']['iterations'])
        np.testing.assert_allclose(result['T_map_odom'], replay['replay']['T_map_odom'], atol=1e-12)

    def test_capture_client_makes_one_same_origin_request_and_does_not_change_seed(self):
        result, *_ = self.capture(count=180)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'request.json'; source.write_text(json.dumps(request_body()))
            with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(result).encode())) as opened:
                actual = cli.capture('http://127.0.0.1:8088', source)
            self.assertEqual(actual, result); self.assertEqual(opened.call_count, 1)
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:8088/api/v1/observations/map-alignment')
            self.assertEqual(request.get_header('Origin'), 'http://127.0.0.1:8088')
            self.assertEqual(json.loads(request.data), request_body() | {'provenance_mode': 'native_publisher', 'capture_inputs': True})
            with patch('urllib.request.OpenerDirector.open', side_effect=ValueError('409')) as opened:
                with self.assertRaisesRegex(ValueError, '409'):
                    cli.capture('http://127.0.0.1:8088', source)
                self.assertEqual(opened.call_count, 1)
