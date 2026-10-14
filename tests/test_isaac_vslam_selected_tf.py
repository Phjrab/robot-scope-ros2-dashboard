"""Recorded official sample metadata tests; no VSLAM/GPU success is implied."""
import copy
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import Mock

CODE = Path(__file__).resolve().parents[1] / 'experiments/isaac_vslam'
API = runpy.run_path(str(CODE / 'selected_static_tf.py'))
GUARD = runpy.run_path(str(CODE / 'config/launch_contract.py'))


class ObservedSampleTests(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads((CODE / 'config/official_sample.inspection.json').read_text())
        self.contract = json.loads((CODE / 'config/official_sample.input.json').read_text())

    def test_exact_four_camera_chain_transforms_are_preserved(self):
        selected = API['load_selected'](CODE / 'config/official_sample.inspection.json',
                                        CODE / 'config/official_sample.input.json')
        self.assertEqual(len(selected), 4)
        children = {t['child_frame_id'] for t in selected}
        self.assertEqual(children, {'front_stereo_camera_left', 'front_stereo_camera_left_optical',
                                    'front_stereo_camera_right', 'front_stereo_camera_right_optical'})
        original = self.evidence['topics']['/tf_static']['first']['transforms']
        for transform in selected:
            self.assertIn(transform, original)
            self.assertNotIn(transform['header']['frame_id'], ('base_link', 'map', 'odom'))
        right = next(t for t in selected if t['child_frame_id'] == 'front_stereo_camera_right')
        self.assertEqual(right['transform']['translation']['y'], -.15)

    def test_missing_ambiguous_or_world_chains_fail(self):
        transforms = self.evidence['topics']['/tf_static']['first']['transforms']
        mutations = [
            lambda e: e['topics']['/tf_static'].update(count=2),
            lambda e: e['files'][0].update(sha256='0' * 64),
            lambda e: e['topics']['/tf_static']['first']['transforms'].append(copy.deepcopy(transforms[0])),
            lambda e: e['topics']['/tf_static']['first'].update(transforms=[]),
        ]
        for mutate in mutations:
            evidence = copy.deepcopy(self.evidence)
            mutate(evidence)
            with self.assertRaises(ValueError):
                API['selected_transforms'](evidence, self.contract)
        self.contract['base_frame'] = 'base_link'
        with self.assertRaisesRegex(ValueError, 'operational'):
            API['selected_transforms'](self.evidence, self.contract)

    def test_namespaced_recording_keeps_exact_original_camera_transforms(self):
        original = API['selected_transforms'](self.evidence, self.contract)
        self.evidence['topics']['/vslam_lab/tf_static'] = self.evidence['topics'].pop('/tf_static')
        self.contract['static_tf_source_topic'] = '/vslam_lab/tf_static'
        self.assertEqual(API['selected_transforms'](self.evidence, self.contract), original)
        self.contract['static_tf_source_topic'] = '/operational/tf_static'
        with self.assertRaises(ValueError):
            API['selected_transforms'](self.evidence, self.contract)

    def test_actual_source_contract_is_vo_compatible_and_no_imu_is_invented(self):
        parameters, _ = GUARD['validate_input'](self.contract, 'vo', True)
        self.assertFalse(parameters['rectified_images'])
        self.assertEqual(parameters['base_frame'], 'front_stereo_camera')
        with self.assertRaisesRegex(ValueError, 'VIO'):
            GUARD['validate_input'](self.contract, 'vio', True)
        spec = json.loads((CODE / 'config/official_sample.replay.json').read_text())
        self.assertEqual(len(spec['topics']), 4)
        self.assertTrue(all(t['source'] not in ('/tf', '/tf_static') for t in spec['topics']))

    def test_waits_for_clock_and_republishes_identical_observations_after_buffer_clear(self):
        broadcaster = Mock()
        messages = API['selected_transforms'](self.evidence, self.contract)
        original = copy.deepcopy(messages)
        timer, sent = API['publish_when_clock_ready'](broadcaster, messages, 0, 10., 0.)
        self.assertFalse(sent)
        broadcaster.sendTransform.assert_not_called()
        timer, sent = API['publish_when_clock_ready'](broadcaster, messages, 1707938733000000000, 10.1, timer)
        self.assertTrue(sent)
        timer, sent = API['publish_when_clock_ready'](broadcaster, messages, 1707938733000000000, 10.2, timer)
        self.assertFalse(sent)
        timer, sent = API['publish_when_clock_ready'](broadcaster, messages, 1707938733000000000, 10.7, timer)
        self.assertTrue(sent)
        self.assertEqual(broadcaster.sendTransform.call_count, 2)
        self.assertEqual(messages, original)
        self.assertTrue(all(call.args[0] is messages for call in broadcaster.sendTransform.call_args_list))


if __name__ == '__main__':
    unittest.main()
