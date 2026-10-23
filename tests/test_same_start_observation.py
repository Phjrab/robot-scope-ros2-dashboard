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


class ObservationPreparationTests(unittest.TestCase):
    def test_slow_reference_is_retained_but_no_stale_pose_or_extended_budget(self):
        from unittest.mock import patch
        from test_observation_alignment import Catalog, Agent, request_body
        from robot_dashboard.relocalization.observation_alignment import ObservationAligner
        cloud, pose = inputs()
        catalog = Catalog(np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3))
        agent, aligner = Agent(cloud, pose), ObservationAligner()
        clock = [time.monotonic()]
        original_data = catalog.data
        def slow_data(*args):
            data = original_data(*args)
            clock[0] += .7
            return data
        with patch('robot_dashboard.relocalization.observation_alignment.time.monotonic', side_effect=lambda: clock[0]), \
                patch.object(catalog, 'data', side_effect=slow_data):
            with self.assertRaisesRegex(ObservationAlignmentError, 'COMPUTE_BUDGET_EXCEEDED'):
                aligner.estimate(catalog, agent, request_body())
            self.assertEqual(catalog.reads, 1)
            self.assertIsNone(aligner.cache[2])
            clock[0] += 1
            # Cached reference must not revive the original, now stale samples.
            with self.assertRaisesRegex(ObservationAlignmentError, 'STALE_INPUT'):
                aligner.estimate(catalog, agent, request_body())
            clock[0] += 1
            for sample in (agent.cloud, agent.pose):
                sample['observation']['received_monotonic_s'] = clock[0]
                sample['observation']['source_stamp_ns'] = '1792309182130175352'
            result = aligner.estimate(catalog, agent, request_body())
            self.assertEqual(result['status'], 'CANDIDATE')
            self.assertEqual(catalog.reads, 1)
            self.assertEqual(result['source']['source_stamp_ns'], '1792309182130175352')

    def test_selected_map_revalidates_without_rescanning_and_preserves_data(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from test_saved_maps import write_pcd
        from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapError
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'map.pcd'
            write_pcd(path, [(i / 10, i % 3, i % 7) for i in range(100)])
            catalog = SavedMapCatalog([root])
            meta = catalog.list_snapshot()['maps'][0]
            expected = catalog.data(meta['id'])
            self.assertEqual(catalog.observation_metadata(meta['id']), meta)
            with patch.object(catalog, '_scan', side_effect=AssertionError('unrelated map scan')):
                self.assertEqual(catalog.observation_data(meta['id']), expected)
                write_pcd(path, [(i / 9, i % 3, i % 7) for i in range(101)])
                self.assertNotEqual(catalog.observation_metadata(meta['id'])['revision'], meta['revision'])
                path.unlink()
                with self.assertRaises(SavedMapError):
                    catalog.observation_metadata(meta['id'])
                path.symlink_to(root / 'missing.pcd')
                with self.assertRaises(SavedMapError):
                    catalog.observation_metadata(meta['id'])

    def test_replacement_during_reference_read_is_rejected(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from test_saved_maps import write_pcd
        from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapConflict
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'map.pcd'
            write_pcd(path, [(i, i % 3, i % 7) for i in range(100)])
            catalog = SavedMapCatalog([root])
            meta = catalog.list_snapshot()['maps'][0]
            read = catalog._data_for_record
            def replaced(*args):
                result = read(*args)
                write_pcd(path, [(i, i % 3, i % 7) for i in range(101)])
                return result
            with patch.object(catalog, '_data_for_record', side_effect=replaced):
                with self.assertRaises(SavedMapConflict):
                    catalog.observation_data(meta['id'])
