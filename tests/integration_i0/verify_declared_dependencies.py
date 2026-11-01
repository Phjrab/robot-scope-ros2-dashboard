"""Exercise I0 HTTP boundaries with optional httpx/httpx2 imports denied."""
import builtins
import unittest

original_import = builtins.__import__


def declared_import(name, *args, **kwargs):
    if name.split('.')[0] in {'httpx', 'httpx2'}:
        raise ModuleNotFoundError('optional HTTP clients intentionally unavailable')
    return original_import(name, *args, **kwargs)


if __name__ == '__main__':
    builtins.__import__ = declared_import
    suite = unittest.defaultTestLoader.loadTestsFromNames([
        'tests.integration_i0.test_maps', 'tests.integration_i0.test_boundaries'])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    from robot_dashboard.expansion_services.scene import SceneSnapshotService
    from robot_dashboard.expansion_diagnostics.http_probe import http_snapshot
    service = SceneSnapshotService({'map_id':'a'*24,'revision':'b'*64,'generation':1}, schema_version='0.2')
    assert '0.2' in http_snapshot(service)
    print('PASS: I0 and C7 actual HTTP without httpx/httpx2')
