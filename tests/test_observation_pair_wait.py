"""Callback ordering regression; exact stamps and existing limits stay intact."""
import copy
import unittest
from unittest.mock import patch

from test_observation_alignment import Agent, inputs, request_body
from robot_dashboard.relocalization.observation_alignment import (
    ObservationAligner, ObservationAlignmentError, paired_pose, project_query,
)


class PairWaitTests(unittest.TestCase):
    def fixture(self, arrival=.052, change=None, subscription=False):
        cloud, pose = inputs()
        cloud['frame_id'] = 'camera_init'
        pose.update(topic='/Odometry', frame_id='camera_init', child_frame_id='body')
        if subscription:
            from test_observation_subscription_alignment import evidence
            for value, kind in [(cloud, 'sensor_msgs/msg/PointCloud2'), (pose, 'nav_msgs/msg/Odometry')]:
                value['observation'].update(identity_status='UNAVAILABLE', publisher_gid=None,
                    subscription_evidence=evidence(value['topic'], kind, session='1',
                        at=value['observation']['received_monotonic_s']))
        start = cloud['observation']['received_monotonic_s']
        clock = [start]
        matching = copy.deepcopy(pose)
        matching['observation']['received_monotonic_s'] = start + arrival
        pose['observation']['source_stamp_ns'] = str(int(cloud['observation']['source_stamp_ns']) - 1)
        agent = Agent(cloud, pose)
        def lookup(_, **kwargs):
            if subscription:
                self.assertEqual(kwargs.get('provenance_mode'), 'subscription_observation')
            if change:
                change(agent, clock[0] - start)
            return copy.deepcopy(matching) if clock[0] >= start + arrival else None
        agent.observation_pose_near = lookup
        return agent, clock, start

    def run_pair(self, agent, clock, deadline, mode="native_publisher"):
        with patch('robot_dashboard.relocalization.observation_alignment.time.monotonic', side_effect=lambda: clock[0]), \
                patch('robot_dashboard.relocalization.observation_alignment.time.sleep', side_effect=lambda d: clock.__setitem__(0, clock[0] + d)):
            return paired_pose(agent, agent.cloud, dict(request_body(), provenance_mode=mode), deadline)

    def test_cloud_first_pose_52ms_later_pairs_original_stamp_without_replacing_cloud(self):
        agent, clock, start = self.fixture()
        result = self.run_pair(agent, clock, start + .6)
        self.assertEqual(result['observation']['source_stamp_ns'], agent.cloud['observation']['source_stamp_ns'])
        self.assertLessEqual(clock[0] - start, .061)
        _, _, source = project_query(agent.cloud, result, clock[0])
        self.assertEqual(source['pair_method'], 'FASTLIO_OUTPUT_STAMP_EXACT')
        self.assertEqual(source['source_delta_ns'], '0')

    def test_wait_never_extends_receipt_window_or_remaining_compute_budget(self):
        for budget, limit in [(.6, .15), (.035, .035)]:
            agent, clock, start = self.fixture(arrival=.2)
            self.assertIsNone(self.run_pair(agent, clock, start + budget))
            self.assertAlmostEqual(clock[0] - start, limit)

    def test_dropped_exact_stamp_and_non_fastlio_fail_without_waiting(self):
        for kind in ['newer_pose', 'raw_cloud', 'wrong_frame']:
            agent, clock, start = self.fixture()
            if kind == 'newer_pose':
                agent.pose['observation']['source_stamp_ns'] = str(int(agent.cloud['observation']['source_stamp_ns']) + 1)
            elif kind == 'raw_cloud':
                agent.cloud.update(topic='/lidar_points', pipeline_stage='raw')
            else:
                agent.pose['frame_id'] = 'odom'
            self.assertIsNone(self.run_pair(agent, clock, start + .6))
            self.assertEqual(clock[0], start)

    def test_pose_or_cloud_replacement_during_wait_is_rejected(self):
        for kind in ['pose', 'cloud']:
            def change(agent, elapsed):
                if elapsed >= .02:
                    getattr(agent, kind)['observation']['publisher_epoch'] = '1' * 32
            agent, clock, start = self.fixture(change=change)
            with self.assertRaisesRegex(ObservationAlignmentError, 'SOURCE_CHANGED'):
                self.run_pair(agent, clock, start + .6)

    def test_server_retry_duration_uses_only_monotonic_limiter(self):
        aligner = ObservationAligner()
        aligner.last_started = 8000
        with patch('robot_dashboard.relocalization.observation_alignment.time.monotonic', return_value=8000.25):
            self.assertEqual(aligner.retry_after_ms(), 750)
        with patch('robot_dashboard.relocalization.observation_alignment.time.monotonic', return_value=8002):
            self.assertEqual(aligner.retry_after_ms(), 0)
        self.assertEqual(aligner.last_started, 8000)

    def test_subscription_wait_preserves_explicit_unverified_mode_and_graph_gate(self):
        agent, clock, start = self.fixture(subscription=True)
        result = self.run_pair(agent, clock, start + .6, mode='subscription_observation')
        _, _, source = project_query(agent.cloud, result, clock[0], provenance_mode='subscription_observation')
        self.assertEqual(source['pair_method'], 'FASTLIO_OUTPUT_STAMP_EXACT')
        self.assertFalse(source['per_message_publisher_verified'])
        agent, clock, start = self.fixture(subscription=True)
        agent.pose['observation']['subscription_evidence']['graph']['observed_monotonic_s'] = start - 4
        with self.assertRaisesRegex(ObservationAlignmentError, 'SUBSCRIPTION_EVIDENCE_UNAVAILABLE'):
            self.run_pair(agent, clock, start + .6, mode='subscription_observation')
