import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from robot_dashboard.mission_routes import competition_assets as assets


class EvidenceRevisionTests(unittest.TestCase):
    def test_current_and_historical_are_verified_without_native_claim(self):
        for revision in ('D0-20261024', 'publication-7f2a707'):
            result = assets.vm_evidence(revision)
            for value in result.values():
                self.assertEqual(value['scope'], 'SYNTHETIC_ONLY')
                self.assertEqual(value['stage'], 'VM_VERIFIED')
                self.assertFalse(value['native_connected'])
                self.assertTrue(value['verified_sha256'])
        self.assertIsNone(assets.vm_evidence('unknown')['traffic_signals']['stage'])

    def test_modified_source_missing_validation_and_modified_log_are_rejected(self):
        registry = json.loads(Path(assets.__file__).with_name('competition_evidence_revisions.json').read_text())
        files = registry['D0-20261024']['files']
        targets = ['experiments/competition_vm/traffic_signals/core.py',
                   'experiments/competition_vm/integration/revisions/d0_20261024/VALIDATION.json',
                   'experiments/competition_vm/integration/revisions/d0_20261024/tests.txt',
                   registry['D0-20261024']['manifest']]
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                for name in files:
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(assets.REPO / name, path)
                if target.endswith('VALIDATION.json'):
                    (root / target).unlink()
                else:
                    (root / target).write_text('changed source or evidence')
                with patch.object(assets, 'REPO', root):
                    self.assertIsNone(assets.vm_evidence()['traffic_signals']['stage'])
