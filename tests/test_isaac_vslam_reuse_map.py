import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest

CODE = Path(__file__).resolve().parents[1] / 'experiments/isaac_vslam'
sys.path.insert(0, str(CODE))
try:
    helper = runpy.run_path(str(CODE / 'reuse_map.py'))
finally:
    sys.path.remove(str(CODE))


class ReuseMapTests(unittest.TestCase):
    def test_map_is_verified_against_saved_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            (run / 'map').mkdir()
            data = run / 'map/data.mdb'
            data.write_bytes(b'map')
            files = helper['map_inventory'](run / 'map')
            (run / 'map-save.json').write_text(json.dumps({
                'status': 'SAVED_NOT_RELOCALIZATION_TESTED', 'files': files}))
            self.assertEqual(helper['checked_map'](run), files)
            data.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                helper['checked_map'](run)

    def test_hint_requires_finite_normalized_pose_and_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'hint.json'
            good = {'position': [0, 0, 0], 'quaternion_xyzw': [0, 0, 0, 1],
                    'evidence': 'stationary hypothesis'}
            path.write_text(json.dumps(good))
            self.assertEqual(helper['checked_hint'](path), good)
            for field, value in [('evidence', ''), ('position', [float('nan'), 0, 0]),
                                 ('quaternion_xyzw', [0, 0, 0, 0])]:
                invalid = dict(good, **{field: value})
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    helper['checked_hint'](path)
