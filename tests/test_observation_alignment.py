"""Synthetic observation-only checks. No ROS, robot connections or motion."""
import asyncio
import copy
import json
import inspect
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI

from robot_dashboard.api.routers.observation_alignment import router
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.relocalization.experimental_se3 import (
    _nearest, from_translation_rpy, inverse, transform_points,
)
from robot_dashboard.relocalization.observation_alignment import (
    ObservationAligner, ObservationAlignmentError, RadiusGrid, project_query,
)
from robot_dashboard.ros.observation_identity import ObservationIdentity, wrap_observation_callback
from robot_dashboard.ros.telemetry import TelemetryHub

MAP_ID, REVISION = 'a' * 24, 'b' * 64


def observation(epoch='c', received=None):
    return dict(observer_id='d' * 32, publisher_epoch=epoch * 32,
                publisher_gid='e' * 32, publisher_count=1,
                identity_status='OBSERVED_PUBLISHER', source_stamp_ns='1792309179130175352',
                receipt_clock='OBSERVER_HOST_MONOTONIC', source_clock='ROS_HEADER_UNVERIFIED',
                received_monotonic_s=time.monotonic() if received is None else received)


def inputs(points=None):
    if points is None:
        points = np.random.default_rng(7).uniform(-2, 2, (180, 3))
    now = time.monotonic()
    cloud = dict(topic='/cloud_registered', pipeline_stage='registered', frame_id='odom', seq=1, units='m',
                 points_bytes=np.asarray(points, dtype='<f4').tobytes(), observation=observation(received=now))
    pose = dict(topic='/odom', frame_id='odom', child_frame_id='base_link', seq=2, state='ok',
                age_s=0.0, position=dict(x=2, y=3, z=4), orientation=dict(x=0, y=0, z=0, w=1),
                observation=observation('f', now))
    return cloud, pose


def request_body():
    return dict(map_id=MAP_ID, map_revision=REVISION, observer_id='d' * 32,
                cloud_epoch='c' * 32, pose_epoch='f' * 32, T_map_odom_seed=np.eye(4).tolist())


class Catalog:
    def __init__(self, points):
        self.points = points
        self.revision = REVISION
        self.reads = 0
        self.capped = False

    def metadata(self, _):
        return dict(kind='pointcloud3d', revision=self.revision, point_count=len(self.points))

    def data(self, identifier, limit):
        assert identifier == MAP_ID and limit is None
        self.reads += 1
        return dict(points=self.points, source_points=len(self.points), revision=self.revision,
                    frame_id='map', display_capped=self.capped)


class Agent:
    def __init__(self, cloud, pose):
        self.cloud, self.pose = cloud, pose

    def pointcloud_binary_snapshot(self):
        return copy.deepcopy(self.cloud)

    def observation_pose_near(self, _):
        return copy.deepcopy(self.pose)

    def pose_snapshot(self):
        return copy.deepcopy(self.pose)


class AlignmentTests(unittest.TestCase):
    def test_grid_exact_within_original_gate_and_ties(self):
        rng = np.random.default_rng(20)
        target = np.vstack((rng.uniform(-8, 8, (5000, 3)), [[0, 0, 0], [0, 0, 0]]))
        query = np.vstack((rng.uniform(-8, 8, (140, 3)), [[0, 0, 0], [100, 0, 0]]))
        actual, d = RadiusGrid(target).nearest(query)
        expected, full = _nearest(query, target)
        inside = full <= .75 ** 2
        np.testing.assert_array_equal(actual[inside], expected[inside])
        np.testing.assert_allclose(d[inside], full[inside], atol=1e-12)
        self.assertTrue(np.isinf(d[~inside]).all())
        _, boundary = RadiusGrid(np.array([[.75, 0, 0]])).nearest(np.array([[0., 0, 0]]))
        self.assertEqual(boundary[0], .75 ** 2)

    def test_grid_and_dense_search_budget(self):
        points = np.zeros((100_000, 3))
        with self.assertRaisesRegex(ObservationAlignmentError, 'BUDGET'):
            RadiusGrid(points, deadline=time.monotonic() - 1)
        grid = RadiusGrid(points)
        with self.assertRaisesRegex(ObservationAlignmentError, 'BUDGET'):
            grid.nearest(points[:2], deadline=time.monotonic() - 1)

    def test_registered_cloud_is_not_transformed_twice_and_raw_uses_inverse(self):
        cloud, pose = inputs()
        raw = np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3)
        query, _, provenance = project_query(cloud, pose, time.monotonic())
        np.testing.assert_allclose(query, raw)
        self.assertEqual(provenance['pair_method'], 'HOST_RECEIPT_NEAREST')
        self.assertFalse(provenance['deskew_verified'])
        cloud.update(topic='/velodyne_points', pipeline_stage='converted', frame_id='hesai_lidar',
                     robot_pose_in_frame=dict(x=0, y=.25, z=.1, roll=.1, pitch=.2, yaw=-np.pi/2,
                                              frame_id='hesai_lidar', source='configured_sensor_extrinsic'))
        pose['orientation'] = dict(x=0, y=0, z=np.sin(.4), w=np.cos(.4))
        actual, _, _ = project_query(cloud, pose, time.monotonic())
        extrinsic = from_translation_rpy([0, .25, .1], [.1, .2, -np.pi/2])
        body = from_translation_rpy([2, 3, 4], [0, 0, .8])
        np.testing.assert_allclose(actual, transform_points(body @ inverse(extrinsic), raw))

    def test_stale_pair_missing_identity_and_body_frame_fail_closed(self):
        for change, expected in [
            (lambda c, p: c['observation'].update(received_monotonic_s=time.monotonic()-3), 'MISMATCH'),
            (lambda c, p: p.update(child_frame_id='camera'), 'INVALID_INPUT'),
            (lambda c, p: c['observation'].update(publisher_count=2), 'IDENTITY'),
            (lambda c, p: c.update(units='mm'), 'INVALID_INPUT'),
            (lambda c, p: c.update(points_bytes=b'bad'), 'buffer'),
        ]:
            cloud, pose = inputs(); change(cloud, pose)
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                project_query(cloud, pose, time.monotonic())
        cloud, pose = inputs()
        cloud['observation']['received_monotonic_s'] -= 2
        pose['observation']['received_monotonic_s'] -= 2
        with self.assertRaisesRegex(ObservationAlignmentError, 'STALE'):
            project_query(cloud, pose, time.monotonic())

    def test_full_reference_candidate_and_server_rate_and_busy(self):
        reference = np.random.default_rng(4).uniform(-4, 4, (5001, 3))
        cloud, pose = inputs(reference[::25])
        catalog, aligner = Catalog(reference), ObservationAligner()
        result = aligner.estimate(catalog, Agent(cloud, pose), request_body())
        self.assertEqual(result['status'], 'CANDIDATE')
        self.assertEqual(result['reference_points'], 5001)
        self.assertEqual(result['operational_application'], 'NOT_RUN')
        self.assertIsNone(result['absolute_accuracy_m'])
        self.assertFalse(result['body_pose_verified'])
        self.assertLess(result['metrics']['rmse_m'], .0001)
        with self.assertRaisesRegex(ObservationAlignmentError, 'RATE_LIMIT'):
            aligner.estimate(catalog, Agent(cloud, pose), request_body())
        with aligner.lock, self.assertRaisesRegex(ObservationAlignmentError, 'BUSY'):
            aligner.estimate(catalog, Agent(cloud, pose), request_body())

    def test_local_plane_cannot_be_qualified_by_full_3d_reference(self):
        plane = np.array([[x, y, 0] for x in np.linspace(-1, 1, 12) for y in np.linspace(-1, 1, 12)])
        reference = np.vstack((plane, np.random.default_rng(2).uniform(5, 8, (180, 3))))
        cloud, pose = inputs(plane)
        result = ObservationAligner().estimate(Catalog(reference), Agent(cloud, pose), request_body())
        self.assertEqual(result['reason'], 'DEGENERATE_MATCHED_GEOMETRY')
        self.assertEqual(result['status'], 'REJECTED')

    def test_source_and_map_change_during_worker_never_publish_candidate(self):
        cloud, pose = inputs()
        reference = np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3)
        from robot_dashboard.relocalization.observation_alignment import register_se3
        for kind in ('map', 'cloud', 'pose'):
            catalog, agent = Catalog(reference), Agent(*copy.deepcopy((cloud, pose)))
            def changed(*args, **kwargs):
                result = register_se3(*args, **kwargs)
                if kind == 'map': catalog.revision = '0' * 64
                else: getattr(agent, kind)['observation']['publisher_epoch'] = '0' * 32
                return result
            with self.subTest(kind=kind), patch('robot_dashboard.relocalization.observation_alignment.register_se3', side_effect=changed):
                with self.assertRaisesRegex(ObservationAlignmentError, 'CHANGED'):
                    ObservationAligner().estimate(catalog, agent, request_body())
        catalog = Catalog(reference); catalog.capped = True
        with self.assertRaisesRegex(ObservationAlignmentError, 'INCOMPLETE'):
            ObservationAligner().estimate(catalog, Agent(cloud, pose), request_body())

    def test_worker_holds_lock_until_computation_returns_and_releases_on_failure(self):
        cloud, pose = inputs()
        catalog = Catalog(np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3))
        aligner = ObservationAligner()
        def fail(*args, **kwargs):
            self.assertTrue(aligner.lock.locked())
            with self.assertRaisesRegex(ObservationAlignmentError, 'BUSY'):
                aligner.estimate(catalog, Agent(cloud, pose), request_body())
            raise ValueError('fixture-failure')
        with patch('robot_dashboard.relocalization.observation_alignment.register_se3', side_effect=fail):
            with self.assertRaisesRegex(ObservationAlignmentError, 'fixture-failure'):
                aligner.estimate(catalog, Agent(cloud, pose), request_body())
        self.assertFalse(aligner.lock.locked())


class IdentityTests(unittest.TestCase):
    def test_supported_callback_receives_message_info_and_fences_destroyed_subscription(self):
        active, calls = [True], []
        with patch('robot_dashboard.ros.observation_identity._supports_message_info', return_value=True):
            callback = wrap_observation_callback(lambda *a, **kw: calls.append((a, kw)), '/odom', 'nav_msgs/msg/Odometry', lambda: active[0])
        info = SimpleNamespace(publisher_gid=bytes([1])*16)
        with self.assertRaises(TypeError):
            inspect.signature(callback).bind('message')
        inspect.signature(callback).bind('message', info)
        callback('message', info)
        active[0] = False
        callback('late', info)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][1]['message_info'], info)

    def test_gid_reversal_gap_and_missing_metadata(self):
        identity = ObservationIdentity()
        def see(stamp, now, gid=1, count=1):
            return identity.observe(topic='/odom', frame='odom', child='base_link', stamp_ns=stamp,
                received=now, message_info=SimpleNamespace(publisher_gid=bytes([gid])*16), publisher_count=count)
        first = see(1792309179130175352, 10)
        self.assertEqual(first['source_stamp_ns'], '1792309179130175352')
        self.assertIsNone(first['native_session_id'])
        same = see(1792309179130175353, 10.1)
        self.assertEqual(same['publisher_epoch'], first['publisher_epoch'])
        for stamp, now, gid, reason in [(1, 10.2, 1, 'SOURCE_TIME_REVERSED'), (2, 12, 1, 'RECEIPT_GAP'), (3, 12.1, 2, 'SOURCE_CHANGED')]:
            new = see(stamp, now, gid)
            self.assertNotEqual(new['publisher_epoch'], same['publisher_epoch'])
            self.assertEqual(new['reset_reason'], reason); same = new
        self.assertEqual(see(4, 12.2, count=2)['identity_status'], 'UNAVAILABLE')
        self.assertEqual(see(5, 12.3, gid=0)['identity_status'], 'UNAVAILABLE')

    def test_stalled_source_does_not_stay_observed(self):
        identity = ObservationIdentity()
        kw = dict(topic='/odom', frame='odom', stamp_ns=100, message_info=SimpleNamespace(publisher_gid=bytes([1])*16), publisher_count=1)
        for now in [10, 10.5, 10.9]: identity.observe(**kw, received=now)
        self.assertEqual(identity.observe(**kw, received=11.1)['identity_status'], 'UNAVAILABLE')

    def test_invalid_replacement_and_inflight_pose_after_reset_clear_previous_origin(self):
        hub = TelemetryHub(threading.RLock(), joint_stale_after_s=1, pose_stale_after_s=1, pose_position_limit_m=1000)
        msg = SimpleNamespace(header=SimpleNamespace(frame_id='odom'), child_frame_id='base_link')
        parsed = dict(frame_id='odom', child_frame_id='base_link', position=dict(x=0,y=0,z=0), orientation=dict(x=0,y=0,z=0,w=1))
        def update(gid):
            hub.update_pose('/odom', 'nav_msgs/msg/Odometry', msg, time.monotonic(), selected_topic=lambda:'/odom', stamp_ns=lambda _:1,
                            message_info=SimpleNamespace(publisher_gid=bytes([gid])*16), publisher_count=1)
        with patch('robot_dashboard.ros.telemetry.extract_odometry_pose', return_value=parsed): update(1)
        epoch = hub.pose['observation']['publisher_epoch']
        with patch('robot_dashboard.ros.telemetry.extract_odometry_pose', return_value=None): update(2)
        self.assertIsNone(hub.pose['pose']); self.assertEqual(len(hub.pose_history), 0)
        self.assertNotEqual(epoch, hub.pose['observation']['publisher_epoch'])
        def resetting(*args, **kwargs): hub.reset_pose('/odom', 'nav_msgs/msg/Odometry'); return parsed
        with patch('robot_dashboard.ros.telemetry.extract_odometry_pose', side_effect=resetting): update(3)
        self.assertIsNone(hub.pose['pose']); self.assertEqual(len(hub.pose_history), 0)


class ObservationApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_origin_bounds_and_cached_only_numerical_request(self):
        app = FastAPI(); app.include_router(router)
        calls = []
        app.state.runtime = ApplicationRuntime(saved_maps=object(), agent=object(), observation_aligner=SimpleNamespace(
            estimate=lambda *args: calls.append(args) or dict(status='REJECTED')))
        async def request(body, origin='http://testserver'):
            messages = []
            async def receive(): return dict(type='http.request', body=json.dumps(body).encode(), more_body=False)
            async def send(message): messages.append(message)
            path = '/api/v1/observations/map-alignment'
            await app(dict(type='http', asgi={'version':'3.0'}, http_version='1.1', method='POST', scheme='http', path=path,
                raw_path=path.encode(), query_string=b'', root_path='', server=('testserver',80), client=('127.0.0.1',1),
                headers=[(b'host',b'testserver'),(b'origin',origin.encode()),(b'content-type',b'application/json')]), receive, send)
            return next(m['status'] for m in messages if m['type']=='http.response.start')
        self.assertEqual(await request(request_body(), 'http://evil.example'), 403)
        self.assertEqual(calls, [])
        for change in [dict(map_id='../secret'), dict(T_map_odom_seed=[[1]*4]*5), dict(extra=True)]:
            self.assertEqual(await request(request_body() | change), 422)
        self.assertEqual(await request(request_body()), 200)
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[-1][2]['capture_inputs'])
        self.assertEqual(await request(request_body() | {'capture_inputs': True}), 200)
        self.assertTrue(calls[-1][2]['capture_inputs'])
        self.assertEqual(await request(request_body() | {'capture_inputs': 'true'}), 422)
