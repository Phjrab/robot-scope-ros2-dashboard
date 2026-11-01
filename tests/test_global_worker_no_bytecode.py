"""Regression for both global-worker launch paths; no real systemd or hardware."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from robot_dashboard.relocalization import external_global_observation as subject
from robot_dashboard.relocalization import native_observation_scope_admission as admission
import test_external_global_observation as fixtures


class BytecodeLaunchTests(unittest.TestCase):
    def test_direct_launch_runs_worker_without_writing_adapter_cache(self):
        fixture = fixtures.ExternalGlobalObservationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        worker_dir = fixture.root / 'dashboard_worker'
        worker_dir.mkdir()
        worker = worker_dir / 'global_observation_worker.py'
        shutil.copy2(subject._WORKER, worker)
        shutil.copy2(subject._WORKER.with_name('v031_observation_compat.py'), worker_dir)
        with mock.patch.object(subject, '_WORKER', worker):
            result = fixture.run_one(fixture.runner())
        self.assertTrue(result['execution']['worker_reaped'])
        self.assertEqual(result['input_points'], 2)
        self.assertEqual(list(worker_dir.rglob('*.pyc')), [])

    def test_scoped_admission_reexecs_global_worker_with_no_bytecode(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            folder.chmod(0o700)
            worker = folder / 'global_observation_worker.py'
            worker.write_text('# synthetic executable identity only\n')
            nonce = 'a' * 32
            unit = f'robot-scope-global-{nonce}.scope'
            argv = ['admission', '--unit', unit, '--nonce', nonce, '--kind', 'global',
                    '--worker', str(worker), '--worker-sha256', hashlib.sha256(worker.read_bytes()).hexdigest(),
                    '--workdir', str(folder)]
            boundary = {'fixture': 'unchanged'}
            def create_proof(_path, proof):
                ack = {'schema': 'robot-scope.native-scope-ack.v1', 'unit': unit,
                       'nonce': nonce, 'pid': proof['pid'], 'pgid': proof['pgid']}
                path = folder / ('resource-ack-' + nonce + '.json')
                path.write_text(json.dumps(ack))
                path.chmod(0o600)
            original_lstat = Path.lstat
            for owner in (1001, 1000):
                def fixture_lstat(path):
                    info = original_lstat(path)
                    if path == folder:
                        return SimpleNamespace(st_mode=info.st_mode, st_uid=owner)
                    return info
                with self.subTest(workdir_owner=owner), \
                     mock.patch.object(Path, 'lstat', autospec=True, side_effect=fixture_lstat), \
                     mock.patch.object(sys, 'argv', argv), mock.patch.object(admission.os, 'getuid', return_value=1000), \
                     mock.patch.object(admission.os, 'geteuid', return_value=1000), \
                     mock.patch.object(admission, 'read_boundary', return_value=boundary), \
                     mock.patch.object(admission, 'private_json', side_effect=create_proof) as publish, \
                     mock.patch.object(admission, 'read_private_json', side_effect=lambda p: json.loads(p.read_text())), \
                     mock.patch.object(admission.os, 'execv', side_effect=RuntimeError('intercepted')) as execv:
                    if owner != 1000:
                        with self.assertRaisesRegex(ValueError, 'SCOPE_PRIVATE_WORKDIR_REQUIRED'):
                            admission.main()
                        publish.assert_not_called()
                        execv.assert_not_called()
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'intercepted'):
                            admission.main()
                        executable, command = execv.call_args.args
                        self.assertEqual(executable, sys.executable)
                        self.assertEqual(command, [sys.executable, '-I', '-B', str(worker), str(folder)])


if __name__ == '__main__':
    unittest.main()
