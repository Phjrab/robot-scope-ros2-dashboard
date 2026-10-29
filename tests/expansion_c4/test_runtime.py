import asyncio
from dataclasses import replace
import threading
import unittest

from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig
from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
from robot_dashboard.obstacle_runtime_adapter.runtime import RuntimeAdapter, ReadOnlySource
from .fixtures import identity, cloud, D2Fixture, C1Fixture, fixture_validator


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1_000_000_000
        self.d2, self.c1 = D2Fixture(), C1Fixture()
        self.runtime = RuntimeAdapter(d2=self.d2, scene_sink=self.c1, validate_obstacle=fixture_validator,
            source_epochs={"lidar": "epoch-1", "depth": "epoch-1"}, binding=identity().binding,
            receipt_clock_id="host-fixture", config=RuntimeConfig(mode="synthetic"), clock_ns=lambda: self.now)

    async def asyncTearDown(self):
        await self.runtime.close()

    def offer(self, i=None):
        i = i or identity()
        return self.runtime.offer_raw(cloud(stamp=i.stamp_ns, frame=i.frame_id), i, pointcloud2, origin_m=(0, 0, 0))

    async def drain(self):
        # Restricted Linux sandboxes can suppress asyncio's cross-thread
        # self-pipe wakeup (also documented by test_pcd_editing_integration).
        # A test-only timer bounds selector sleep; production worker unchanged.
        loop = asyncio.get_running_loop()
        timer = None
        def tick():
            nonlocal timer
            timer = loop.call_later(.01, tick)
        tick()
        try:
            await asyncio.wait_for(self.runtime.worker.queue.join(), 3)
        finally:
            timer.cancel()

    async def test_d2_actually_called_c1_c3_provenance_and_bound(self):
        self.runtime.start()
        self.assertTrue(self.offer())
        await self.drain()
        self.assertEqual(self.d2.calls, 1)
        scene = self.c1.snapshot()
        self.assertEqual(scene["obstacle_frame"]["provenance"]["source_identity"]["stamp_ns"], "1000000000")
        self.assertFalse(scene["published_to_nav2"])
        self.assertIsNone(scene["local_trajectory"])
        scene["sequence"] = 888
        self.assertEqual(self.c1.snapshot()["sequence"], 1)
        for n in range(2, 1202):
            self.assertTrue(self.offer(identity(sequence=n, stamp_ns=str(1_000_000_000+n))))
        await self.drain()
        self.assertEqual(self.c1.snapshot()["sequence"], 1201)
        self.assertEqual(self.runtime.worker.queue.maxsize, 1)
        self.assertGreaterEqual(self.runtime.health()["dropped"], 1198)

    async def test_delayed_reordered_and_duplicate_rejected(self):
        self.runtime.start()
        self.assertTrue(self.offer(identity(sequence=5)))
        self.assertFalse(self.offer(identity(sequence=5)))
        self.assertFalse(self.offer(identity(sequence=4)))
        self.assertFalse(self.offer(identity(sequence=6, stamp_ns="999999999")))
        self.now += 600_000_000
        self.assertFalse(self.offer(identity(sequence=7)))
        self.assertFalse(self.offer(identity(sequence=8, received_ns=self.now+1)))
        await self.drain()
        self.assertIsNone(self.c1.snapshot())

    async def test_map_tf_source_epoch_and_receipt_clock_mismatch(self):
        self.runtime.start()
        for changes in ({"map_id": "other"}, {"revision": "r2"}, {"tf_epoch": "tf2"},
                        {"source_epoch": "old"}, {"receipt_clock_id": "foreign"}, {"source_id": "unregistered"}):
            self.assertFalse(self.offer(identity(**changes)))
        self.assertEqual(self.d2.calls, 0)

    async def test_one_stale_sensor_does_not_refresh_another(self):
        self.runtime.start()
        self.offer()
        await self.drain()
        self.now += 600_000_000
        i = identity(source_id="depth", received_ns=self.now)
        self.offer(i)
        await self.drain()
        h = self.runtime.health()["sources"]
        self.assertTrue(h["lidar"]["stale"])
        self.assertFalse(h["depth"]["stale"])

    async def test_unknown_source_clock_keeps_stamp_and_unknown_fusion_age(self):
        self.runtime.start()
        self.offer(identity(clock_domain="unknown"))
        await self.drain()
        scene = self.c1.snapshot()
        self.assertEqual(scene["stamp_ns"], "1000000000")
        self.assertEqual(scene["health"]["sources"]["lidar"]["fusion_time"], "UNKNOWN")

    async def test_heavy_work_off_callback_and_old_generation_discarded(self):
        entered, release = threading.Event(), threading.Event()
        thread_ids = []
        normalizer_thread = []
        base = self.d2.process

        def block(sample):
            thread_ids.append(threading.get_ident())
            entered.set()
            if not release.wait(2):
                raise TimeoutError("fixture watchdog")
            return base(sample)

        def normalize(*args, **kwargs):
            normalizer_thread.append(threading.get_ident())
            return pointcloud2(*args, **kwargs)

        self.d2.process = block
        self.runtime.start()
        main_thread = threading.get_ident()
        self.runtime.offer_raw(cloud(), identity(), normalize)
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.001)
            self.assertTrue(entered.is_set())
            for n in range(2, 25):
                self.offer(identity(sequence=n))
            self.assertEqual(self.runtime.worker.queue.qsize(), 1)
            self.runtime.rebind(source_epochs={"lidar": "epoch-2"}, binding=identity().binding)
        finally:
            release.set()
        await self.drain()
        self.assertNotEqual(thread_ids[0], main_thread)
        self.assertNotEqual(normalizer_thread[0], main_thread)
        self.assertIsNone(self.c1.snapshot())
        self.assertGreaterEqual(self.runtime.late_results, 1)

    async def test_bad_d2_identity_oversize_and_error_do_not_publish(self):
        original = self.d2.process
        self.d2.process = lambda sample: dict(original(sample), stamp_ns="1")
        self.runtime.start()
        self.offer()
        await self.drain()
        self.assertIsNone(self.c1.snapshot())
        self.assertEqual(self.runtime.health()["invalid"], 1)
        self.d2.process = lambda sample: dict(original(sample), excess="x"*600_000)
        self.offer(identity(sequence=2))
        await self.drain()
        self.assertEqual(self.runtime.health()["invalid"], 2)

    async def test_close_drops_late_result_and_rejects_ingress(self):
        self.runtime.start()
        self.offer()
        await self.runtime.close()
        self.assertFalse(self.offer(identity(sequence=2)))
        self.assertIsNone(self.c1.snapshot())

    async def test_default_off_and_source_creation_is_inert(self):
        called = []
        source = ReadOnlySource(lambda: called.append(1))
        self.assertFalse(called)
        with self.assertRaises(ValueError):
            source.samples()
        r = RuntimeAdapter(d2=self.d2, scene_sink=self.c1, validate_obstacle=fixture_validator,
            source_epochs={"lidar": "epoch-1"}, binding=identity().binding, receipt_clock_id="host-fixture")
        with self.assertRaises(ValueError):
            r.start()
        self.assertIsNone(r.worker)
        for mode, endpoint in (("synthetic", "synthetic://fixture"), ("replay", "recorded://local"),
                               ("synthetic", "owner://readonly")):
            source = ReadOnlySource(lambda: [identity()], config=RuntimeConfig(mode=mode, endpoint=endpoint))
            self.assertEqual(next(source.samples()).stamp_ns, "1000000000")
