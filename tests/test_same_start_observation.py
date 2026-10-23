"""Exact FAST-LIO output pairing and IMU semantics; synthetic, no robot I/O."""
import time
import unittest
import numpy as np
from test_observation_alignment import inputs
from robot_dashboard.relocalization.observation_alignment import project_query, ObservationAlignmentError


class SameStartObservationTests(unittest.TestCase):
    def test_registered_imu_cloud_is_already_in_odometry_frame(self):
        cloud, pose = inputs()
        cloud['frame_id'] = 'camera_init'
        pose.update(topic='/Odometry', frame_id='camera_init', child_frame_id='body')
        query, frame, source = project_query(cloud, pose, time.monotonic())
        np.testing.assert_allclose(query, np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3))
        self.assertEqual(frame, 'camera_init')
        self.assertEqual(source['pose_reference'], 'FASTLIO_IMU')
        self.assertEqual(source['pair_method'], 'FASTLIO_OUTPUT_STAMP_EXACT')
        self.assertEqual(source['tracked_frame'], 'body')
        self.assertFalse(source['body_extrinsic_verified'])

    def test_imu_rejects_receipt_near_but_different_source_stamp_and_raw_cloud(self):
        for raw in (False, True):
            cloud, pose = inputs()
            cloud['frame_id'] = 'camera_init'
            pose.update(topic='/Odometry', frame_id='camera_init', child_frame_id='body')
            if raw:
                cloud.update(topic='/velodyne_points', pipeline_stage='converted')
            else:
                pose['observation']['source_stamp_ns'] = str(int(cloud['observation']['source_stamp_ns']) + 1)
            with self.assertRaisesRegex(ObservationAlignmentError, 'FASTLIO_SOURCE_TIME_MISMATCH'):
                project_query(cloud, pose, time.monotonic())
