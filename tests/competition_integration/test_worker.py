import asyncio
import threading
import unittest

from competition_traffic import optional_deps  # noqa: F401
from competition_traffic.helpers import Detector, config, frame
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from robot_dashboard.competition_traffic.worker import TrafficWorker


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_detector_keeps_one_pending_frame_and_does_not_block_loop(self):
        entered, release = threading.Event(), threading.Event()
        class SlowDetector(Detector):
            def infer(self, bgr):
                entered.set()
                release.wait(2)
                return super().infer(bgr)
        worker = TrafficWorker(TrafficPipeline(config(), SlowDetector()), clock=lambda: .1)
        worker.start()
        try:
            worker.offer(frame(0))
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.001)
            self.assertTrue(entered.is_set())
            for i in range(1, 50):
                worker.offer(frame(i, received_s=.1))
            self.assertEqual(worker.queue.qsize(), 1)
            self.assertEqual(worker.dropped, 48)
            release.set()
            await asyncio.wait_for(worker.queue.join(), 2)
            self.assertEqual(worker.latest.frame.sequence, 49)
            self.assertIn('FRAME_SEQUENCE_GAP', worker.latest.observation.signal['quality_flags'])
        finally:
            release.set()
            await worker.close()
        self.assertFalse(worker.offer(frame(50)))
        self.assertIsNone(worker.latest)

    async def test_close_discards_result_from_inflight_inference(self):
        entered, release = threading.Event(), threading.Event()
        class SlowDetector(Detector):
            def infer(self, bgr):
                entered.set()
                release.wait(2)
                return super().infer(bgr)
        worker = TrafficWorker(TrafficPipeline(config(), SlowDetector()), clock=lambda: 0.)
        worker.start()
        worker.offer(frame(0))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.001)
            self.assertTrue(entered.is_set())
            await asyncio.wait_for(worker.close(), .2)
        finally:
            release.set()
        await asyncio.sleep(.02)
        self.assertIsNone(worker.latest)
