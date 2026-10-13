"""Offline checks preventing false map-success claims; ROS integration is separate."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiments.isaac_vslam.save_map import map_inventory, mapping_evidence, save_run_map


class SavedMapEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / 'current-run'
        self.run.mkdir()
        self.env = patch.dict(os.environ, {
            'ROS_DOMAIN_ID': '71', 'ROS_LOCALHOST_ONLY': '1',
            'CYCLONEDDS_URI': '', 'FASTRTPS_DEFAULT_PROFILES_FILE': '',
            'FASTDDS_DEFAULT_PROFILES_FILE': '',
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.launch = {'mode': 'slam_vo', 'ros_domain_id': '71',
                       'requested_parameters': {'enable_localization_n_mapping': True}}
        self.events = [
            {'event': 'run_start', 'run_id': self.run.name, 'ros_domain_id': '71',
             'evidence_type': 'official_bag'},
            {'event': 'sample', 'stream': 'slam_path', 'path_poses': 3},
        ]
        self.write_evidence()

    def write_evidence(self):
        (self.run / 'vslam_launch.json').write_text(json.dumps(self.launch))
        (self.run / 'metrics.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in self.events))

    def test_vo_or_odometry_alone_cannot_prove_mapping(self):
        self.launch['mode'] = 'vo'
        self.write_evidence()
        with self.assertRaises(ValueError):
            mapping_evidence(self.run)
        self.launch['mode'] = 'slam_vo'
        self.events[1] = {'event': 'sample', 'stream': 'odom', 'pose': {}}
        self.write_evidence()
        with self.assertRaises(RuntimeError):
            mapping_evidence(self.run)

    def test_other_run_or_domain_is_rejected(self):
        self.events[0]['run_id'] = 'old-run'
        self.write_evidence()
        with self.assertRaises(ValueError):
            mapping_evidence(self.run)
        self.events[0]['run_id'] = self.run.name
        self.launch['ros_domain_id'] = '72'
        self.write_evidence()
        with self.assertRaises(ValueError):
            mapping_evidence(self.run)

    def test_path_evidence_retains_sample_provenance(self):
        evidence = mapping_evidence(self.run)
        self.assertEqual(evidence['max_path_poses'], 3)
        self.assertEqual(evidence['evidence_type'], 'official_bag')

    def test_empty_map_cannot_pass_and_file_hash_is_checked(self):
        directory = self.run / 'map'
        directory.mkdir()
        (directory / 'empty').touch()
        with self.assertRaises(RuntimeError):
            map_inventory(directory)
        (directory / 'database').write_bytes(b'test map data')
        files = map_inventory(directory)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['sha256'], hashlib.sha256(b'test map data').hexdigest())

    def test_existing_map_is_preserved_and_failure_recorded(self):
        directory = self.run / 'map'
        directory.mkdir()
        (directory / 'original').write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):
            save_run_map(self.run)
        self.assertEqual((directory / 'original').read_bytes(), b'preserve')
        report = (self.run / 'map-save.json').read_text()
        self.assertEqual(json.loads(report)['status'], 'FAILED')
        with self.assertRaises(FileExistsError):
            save_run_map(self.run)
        self.assertEqual((self.run / 'map-save.json').read_text(), report)


if __name__ == '__main__':
    unittest.main()
