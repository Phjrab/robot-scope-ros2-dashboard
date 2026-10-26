"""Overload/teardown at the real C4 worker and C1 viewer boundary, no device."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from competition_fixture_server import make_rgb_review, replay_options
from competition_integration.harness import PinnedDetector
from robot_dashboard.competition_traffic.worker import TrafficWorker
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from competition_traffic.helpers import config, frame


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(.005)
    await asyncio.wait_for(wait(), 5)


class ReplayLatestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.reviews = []
        self.release = threading.Event()

    async def asyncTearDown(self):
        self.release.set()
        for review in self.reviews:
            await review.close()
        self.temp.cleanup()

    def review(self, mode='exhaustive', *, clock='wall-clock', spacing=.02):
        root = Path(self.temp.name) / str(len(self.reviews))
        root.mkdir()
        review = make_rgb_review(root, replay_options(['--synthetic-rgb-review',
            '--replay-mode', mode, '--replay-clock', clock]))
        for i, item in enumerate(review.items):
            item.metadata['replay_time_s'] = i * spacing
        self.reviews.append(review)
        return review

    async def test_latest_clock_reaches_end_while_inference_blocked_exhaustive_waits(self):
        for mode in ('exhaustive', 'latest-wall-clock'):
            with self.subTest(mode=mode):
                review = self.review(mode)
                detector = review.worker.pipeline.detector.detector
                entered, release = threading.Event(), threading.Event()
                original = detector.infer
                def infer(image):
                    entered.set()
                    release.wait(5)
                    return original(image)
                detector.infer = infer
                review.start()
                try:
                    await until(entered.is_set)
                    if mode == 'latest-wall-clock':
                        await until(lambda: review.input_finished_s is not None)
                        self.assertEqual(review.processed, 0)
                        self.assertLessEqual(review.worker.queue.qsize(), 1)
                        self.assertGreater(review.worker.dropped, 0)
                    else:
                        await asyncio.sleep(.18)
                        self.assertIsNone(review.input_finished_s)
                        self.assertEqual(review.counters['input'], 1)
                    release.set()
                    await asyncio.wait_for(review.task, 5)
                finally:
                    release.set()
                s = review.snapshot()
                self.assertEqual(s['state'], 'COMPLETE')
                self.assertEqual(s['counts']['input'], 8)
                self.assertEqual(s['observation']['sequence'], 7)
                self.assertEqual(s['observation']['source_stamp_ns'], '140000000')
                self.assertAlmostEqual(s['observation']['first_received_s'], review.anchor + .14)
                self.assertEqual(s['counts']['offered'], s['counts']['processed'] + s['counts']['replaced_pending'])
                if mode == 'exhaustive':
                    self.assertEqual(s['frames_processed'], 8)
                    self.assertGreater(s['observation']['schedule_to_processing_s'], s['observation']['worker_pending_s'])
                else:
                    self.assertEqual(s['frames_processed'], 2)
                    self.assertIn('FRAME_SEQUENCE_GAP', s['observation']['quality_flags'])
                    self.assertEqual(s['observation']['stable_state'], 'UNKNOWN')
                self.assertFalse(s['departure_authorized'])
                self.assertEqual(s, review.snapshot())
                json.dumps(s, allow_nan=False)

    async def test_slow_decode_skips_before_decode_without_renumbering(self):
        review = self.review('latest-wall-clock', spacing=.01)
        decode = review._decode
        def slow(index):
            time.sleep(.045)
            return decode(index)
        review._decode = slow
        review.start()
        await asyncio.wait_for(review.task, 5)
        s = review.snapshot()
        self.assertGreater(s['counts']['dropped_before_decode'], 0)
        self.assertGreater(s['counts']['dropped_after_decode'], 0)
        self.assertEqual(s['counts']['input'], s['counts']['dropped_before_decode'] + s['counts']['decoded'])
        self.assertEqual(s['counts']['decoded'], s['counts']['dropped_after_decode'] + s['counts']['offered'])
        self.assertEqual(s['observation']['sequence'], 7)
        self.assertEqual(s['observation']['source_stamp_ns'], '70000000')
        self.assertLess(s['frames_processed'], 8)

    async def test_encode_is_bounded_and_does_not_hold_latest_producer_or_worker(self):
        review = self.review('latest-wall-clock', spacing=.04)
        entered = threading.Event()
        encode = review._images
        def slow(sample):
            entered.set()
            self.release.wait(5)
            return encode(sample)
        review._images = slow
        review.start()
        await until(entered.is_set)
        await until(lambda: review.input_finished_s is not None)
        await review.worker.queue.join()
        self.assertGreater(review.processed, 1)
        self.assertLessEqual(review.results.qsize(), 1)
        self.assertGreater(review.counters['replaced_display'], 0)
        self.release.set()
        await asyncio.wait_for(review.task, 5)
        s = review.snapshot()
        self.assertEqual(s['observation']['sequence'], 7)
        self.assertLessEqual(len(review.images), 2)
        raw = cv2.imdecode(np.frombuffer(review.image(s['run_id'], 7, 'original'), np.uint8), cv2.IMREAD_COLOR)
        expected = cv2.imread(str(review.items[7].path))
        np.testing.assert_array_equal(raw, expected)
        sample = review.worker.latest
        self.assertEqual(review.image(s['run_id'], 7, 'overlay'), encode(sample)['overlay'])
        t = s['observation']['timing']
        ordered = ['decode_started_s', 'decode_completed_s', 'enqueued_s', 'processing_started_s',
                   'inference_started_s', 'inference_completed_s', 'pipeline_completed_s',
                   'encode_started_s', 'encode_completed_s', 'published_s']
        self.assertEqual([t[k] for k in ordered], sorted(t[k] for k in ordered))

    async def test_source_timeline_preserves_offsets_and_identical_images_with_new_sequences(self):
        review = self.review(clock='source-timeline')
        # Eight real decoder reads of one immutable image; image content is not packet identity.
        first = review.items[0]
        review.items[:] = [replace(first, metadata={'replay_time_s': i * .02}) for i in range(8)]
        review.start()
        await asyncio.wait_for(review.task, 5)
        self.assertEqual(review.worker.pipeline.detector.calls, 8)
        self.assertEqual([x['sequence'] for x in review.trace], list(range(8)))
        self.assertEqual(review.record['first_received_s'], .14)
        self.assertEqual(review.record['processed_s'], .14)
        self.assertFalse(review.snapshot()['historical_clock_verified'])
        self.assertFalse(review.record['departure_authorized'])
        before = review.snapshot()
        for _ in range(5):
            self.assertEqual(before, review.snapshot())

    async def test_unknown_clock_and_changed_profile_keep_raw_but_never_authorize(self):
        review = self.review(clock='source-timeline')
        decode = review._decode
        def unknown(index):
            f = decode(index)
            if index:
                review.worker.pipeline.detector.select_profile('upper-overlap640')
            return replace(f, clock_verified=False, source_age_s=None)
        review._decode = unknown
        review.start()
        await asyncio.wait_for(review.task, 5)
        self.assertIn('SOURCE_CLOCK_UNVERIFIED', review.record['quality_flags'])
        self.assertFalse(review.record['inference_binding_matches'])
        self.assertEqual(review.record['detections'][0]['raw_state'], 'GREEN')
        self.assertEqual(review.record['stable_state'], 'UNKNOWN')
        self.assertFalse(review.record['departure_authorized'])

    async def test_late_inference_keeps_original_receipt_and_ttl_failure(self):
        review = self.review()
        review.limit = 1
        detector = review.worker.pipeline.detector.detector
        original = detector.infer
        def slow(image):
            time.sleep(.3)
            return original(image)
        detector.infer = slow
        review.start()
        await asyncio.wait_for(review.task, 5)
        self.assertEqual(review.record['first_received_s'], review.anchor)
        self.assertIn('RECEIPT_EXPIRED', review.record['quality_flags'])
        self.assertIn('SOURCE_STALE', review.record['quality_flags'])
        self.assertEqual(review.record['stable_state'], 'UNKNOWN')
        self.assertGreaterEqual(review.record['inference_wall_s'], .3)

    async def test_close_discards_running_inference_and_clears_pending(self):
        review = self.review('latest-wall-clock')
        entered = threading.Event()
        detector = review.worker.pipeline.detector.detector
        original = detector.infer
        def blocked(image):
            entered.set()
            self.release.wait(5)
            return original(image)
        detector.infer = blocked
        review.start()
        await until(entered.is_set)
        await until(lambda: review.worker.queue.qsize() == 1)
        await asyncio.wait_for(review.close(), 1)
        self.assertTrue(review.consumer.done())
        self.assertTrue(review.worker.queue.empty())
        self.assertTrue(review.results.empty())
        self.release.set()
        await until(lambda: review.worker.late_results == 1)
        self.assertIsNone(review.record)
        self.assertIsNone(review.worker.latest)
        self.assertEqual(review.processed, 0)
        self.assertFalse(review.snapshot()['departure_authorized'])

    async def test_close_discards_running_encode(self):
        review = self.review('latest-wall-clock')
        entered = threading.Event()
        encode = review._images
        def blocked(sample):
            entered.set()
            self.release.wait(5)
            return encode(sample)
        review._images = blocked
        review.start()
        await until(entered.is_set)
        await asyncio.wait_for(review.close(), 1)
        self.release.set()
        await until(lambda: review.counters['late_encode'] == 1)
        self.assertIsNone(review.record)
        self.assertEqual(len(review.images), 0)

    async def test_invalid_decode_is_counted_without_fabricated_pixels(self):
        review = self.review(clock='source-timeline')
        review.limit = 1
        decode = review._decode
        review._decode = lambda i: replace(decode(i), bgr=None)
        review.start()
        await asyncio.wait_for(review.task, 5)
        self.assertEqual(review.snapshot()['counts']['invalid'], 1)
        self.assertIn('IMAGE_DECODE_FAILED', review.record['quality_flags'])
        self.assertIsNone(review.image(review.run_id, 0, 'original'))

    async def test_actual_retransmission_is_not_inferred_again(self):
        detector = PinnedDetector()
        worker = TrafficWorker(TrafficPipeline(config(), detector), clock=lambda: .2)
        worker.start()
        try:
            f = frame(1)
            worker.offer(f)
            await worker.queue.join()
            worker.offer(replace(f, received_s=.2))
            await worker.queue.join()
            self.assertEqual(detector.calls, 1)
            self.assertEqual(worker.latest.observation.context['first_received_s'], .1)
            self.assertIn('REPEATED_OR_REVERSED_FRAME', worker.latest.observation.signal['quality_flags'])
        finally:
            await worker.close()

    async def test_latest_rejects_virtual_clock_and_decode_failure_terminates(self):
        with self.assertRaises(SystemExit):
            replay_options(['--synthetic-rgb-review', '--replay-mode', 'latest-wall-clock', '--replay-clock', 'source-timeline'])
        review = self.review()
        with patch.object(review, '_decode', side_effect=ValueError('corrupt')):
            review.start()
            await asyncio.wait_for(review.task, 5)
        self.assertEqual(review.state, 'FAILED')
        self.assertTrue(review.worker.closed)
        self.assertTrue(review.consumer.done())
