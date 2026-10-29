"""Run all discovered tests except exact known denied/unavailable cases.

This is NOT a full-suite pass. Original mandatory command failed 36 cases.
No wildcard exclusions: new failures remain failures. Permission-denied socket
operations are not retried. Inventory is evidence from the first full run.
"""
import json
from pathlib import Path
import unittest


def main():
    blocks={x['id']:x['reason'] for x in json.loads(Path(__file__).with_name('known_environment_blocks.json').read_text())}
    suite=unittest.defaultTestLoader.discover('tests')
    def filtered(item):
        if isinstance(item,unittest.TestSuite): return unittest.TestSuite(filtered(t) for t in item)
        if item.id() in blocks:
            reason=blocks[item.id()]
            @unittest.skip(reason)
            def unavailable(): pass
            return unittest.FunctionTestCase(unavailable,description=item.id())
        return item
    result=unittest.TextTestRunner(verbosity=2).run(filtered(suite))
    raise SystemExit(not result.wasSuccessful())

if __name__=='__main__': main()
