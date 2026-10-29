import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('heading_overlay', ROOT / 'scripts/check_nav2_heading_overlay.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OverlayValidationTests(unittest.TestCase):
    def test_source_binary_base_and_extra_package_changes_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / 'install'
            source = ROOT / 'ros2/nav2_goal_heading_fix'
            base = Path(tmp) / 'base.so'
            base.write_bytes(b'fixture base library')
            paths = ['lib/libnav2_rotation_shim_controller.so',
                     'share/nav2_rotation_shim_controller/nav2_rotation_shim_controller.xml',
                     'share/nav2_rotation_shim_controller/package.xml']
            for name in paths:
                p = prefix / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'fixture artifact')
            packages = prefix / 'share/ament_index/resource_index/packages'
            packages.mkdir(parents=True)
            (packages / 'nav2_rotation_shim_controller').touch()
            setup = prefix / 'share/nav2_rotation_shim_controller/local_setup.bash'
            setup.touch()
            receipt = {'schema': 'robot-scope.nav2-heading-overlay.v1', 'nav2_version': '1.1.20',
                       'native_tests_passed': True, 'base_library_sha256': MODULE.digest(base),
                       'installed_files': {n: MODULE.digest(prefix / n) for n in paths},
                       'patch_files': {n: MODULE.digest(source / n) for n in
                                       ['same-time-goal.patch', 'final-rotation-collision.patch', 'common_time.hpp']}}
            receipt_path = prefix / 'robot-scope-heading-receipt.json'
            receipt_path.write_text(json.dumps(receipt))
            MODULE.validate(prefix, base_library=base)
            setup.unlink()
            with self.assertRaisesRegex(ValueError, 'setup is missing'):
                MODULE.validate(prefix, base_library=base)
            setup.touch()
            for path in [base, prefix / paths[0], prefix / paths[1]]:
                original = path.read_bytes()
                path.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    MODULE.validate(prefix, base_library=base)
                path.write_bytes(original)
            (packages / 'unrelated_controller').touch()
            with self.assertRaisesRegex(ValueError, 'only'):
                MODULE.validate(prefix, base_library=base)
            (packages / 'unrelated_controller').unlink()
            receipt['native_tests_passed'] = False
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'not completed'):
                MODULE.validate(prefix, base_library=base)
