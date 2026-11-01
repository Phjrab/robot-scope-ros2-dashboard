from pathlib import Path

from tests.expansion_runtime import async_cases as upstream
from tests.expansion_runtime import async_fixtures
from robot_dashboard.expansion_integration.flags import ExpansionFlags
from robot_dashboard.expansion_integration.runtime import create_review_runtime


class InstalledAsyncComposition(upstream.ActualAsyncComposition):
    """Same 12 owner assertions against installed modules, including real TCP HTTP."""
    @classmethod
    def setUpClass(cls):
        cls.paths = {'c3': Path(__file__).resolve().parents[2]}
        cls.f = async_fixtures

    async def test_product_factory_is_explicit_advisory_and_has_no_native_sink(self):
        args = dict(geometry=self.adapter.runtime.ports.geometry, context=self.adapter.context,
                    mapping=self.adapter.mapping, capture_provider=lambda i:self.captures[(i.source_epoch,i.sequence)],
                    clock_ns=self.clock, source_id='lidar')
        with self.assertRaisesRegex(ValueError,'FEATURE_DISABLED'):
            create_review_runtime(ExpansionFlags(), **args)
        with self.assertRaisesRegex(ValueError,'BLOCKED_NATIVE_IDENTITY'):
            create_review_runtime(ExpansionFlags(runtime=True,scene=True), mode='ros', **args)
        product = create_review_runtime(ExpansionFlags(runtime=True,scene=True), **args)
        product.start()
        try:
            self.assertTrue(product.offer_raw(*self.packet()))
            await product.worker.queue.join()
            self.assertEqual(product.delivered,1,product.health())
            self.assertEqual(product.runtime.mode,'ADVISORY_ONLY')
            self.assertEqual(product.scene.snapshot()['schema_version'],'0.2')
            self.assertFalse(product.health()['product_enforcement_connected'])
            self.assertEqual(product.health()['adapter_publications'],0)
        finally:
            await product.close()
