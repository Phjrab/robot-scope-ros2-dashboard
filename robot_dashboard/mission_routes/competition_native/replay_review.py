"""Bounded, read-only recorded RGB inspection; never constructs a mission port."""
from __future__ import annotations

import asyncio
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
import math
import re
import time

from .ingress import CompetitionIngress


class _MeasuredDetector:
    def __init__(self, detector, clock):
        self.detector, self.clock = detector, clock
        self.started = self.completed = None

    def __getattr__(self, name):
        return getattr(self.detector, name)

    def infer(self, image):
        self.started = self.clock()
        try:
            return list(self.detector.infer(image))
        finally:
            self.completed = self.clock()


class _ReplayPipeline:
    def __init__(self, config, detector, clock, observation_mode, clock_mode):
        from ...competition_traffic.pipeline import TrafficPipeline
        self.detector = _MeasuredDetector(detector, clock)
        self.clock_mode = clock_mode
        self.pipeline = TrafficPipeline(config, self.detector, clock=clock,
            measure_wall_latency=clock_mode == 'wall-clock', observation_mode=observation_mode)

    def process(self, frame, *, now_s):
        self.detector.started = self.detector.completed = None
        observation = self.pipeline.process(frame, now_s=(
            frame.received_s if self.clock_mode == 'source-timeline' else now_s))
        observation.context['review_inference_timing'] = {
            'inference_started_s': self.detector.started, 'inference_completed_s': self.detector.completed}
        return observation


class RGBReplayReview:
    def __init__(self, items, config, detector, *, fps, max_frames=10000,
                 private=True, observation_mode='detection-only', clock=time.monotonic,
                 replay_mode='exhaustive', clock_mode='wall-clock'):
        from ...competition_traffic.config import finite
        from ...competition_traffic.replay_input import IMAGES
        from ...competition_traffic.worker import TrafficWorker
        pin = getattr(detector, 'inference_settings_sha256', None)
        if not isinstance(pin, str) or not re.fullmatch(r'[0-9a-f]{64}', pin):
            raise ValueError('EXPLICIT_INFERENCE_SETTINGS_PIN_REQUIRED')
        if replay_mode not in ('exhaustive', 'latest-wall-clock'):
            raise ValueError('REPLAY_MODE_INVALID')
        if clock_mode not in ('wall-clock', 'source-timeline') or (
                replay_mode == 'latest-wall-clock' and clock_mode != 'wall-clock'):
            raise ValueError('REPLAY_CLOCK_MODE_INVALID')
        if not finite(fps, .01, 240) or type(max_frames) is not int or not 1 <= max_frames <= 10000:
            raise ValueError('REPLAY_LIMIT_INVALID')
        self.items, self.limit, self.fps = items, min(len(items), max_frames), fps
        if not self.limit:
            raise ValueError('INPUT_IMAGES_REQUIRED')
        previous = None
        for i in range(self.limit):
            offset = self._offset(i)
            if (self.items[i].path.suffix.lower() not in IMAGES or not finite(offset, 0, 1e9)
                    or (previous is not None and offset <= previous)):
                raise ValueError('REPLAY_IMAGE_TIMELINE_INVALID')
            previous = offset
        self.pin, self.clock, self.private = pin, clock, private
        self.replay_mode, self.clock_mode = replay_mode, clock_mode
        self.profile = copy.deepcopy(detector.inference_settings)
        self.binding_id = config.document['association']['binding_id']
        self.worker = TrafficWorker(_ReplayPipeline(config, detector, clock, observation_mode, clock_mode),
                                    clock=clock, result_sink=self._accept_result)
        self.decoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix='replay-decode')
        self.encoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix='replay-encode')
        self.results = asyncio.Queue(maxsize=1)
        self.task = self.consumer = None
        self.closed = False
        self.state, self.error, self.record = 'READY', None, None
        self.trace, self.images = deque(maxlen=64), deque(maxlen=2)
        self.counts, self.counters = Counter(), Counter()
        self.metrics = {}
        self.processed = 0
        self.run_id = None
        self.anchor = self.input_finished_s = None
        self.first_source = self._offset(0)

    def _offset(self, index):
        return self.items[index].metadata.get('replay_time_s', index / self.fps)

    def _arrival(self, index):
        return self.anchor + self._offset(index) - self.first_source

    def start(self):
        if self.task is not None or self.closed:
            raise ValueError('REPLAY_ALREADY_STARTED_OR_CLOSED')
        import secrets
        self.run_id, self.anchor = secrets.token_hex(16), self.clock()
        self.worker.start()
        self.state = 'RUNNING'
        self.consumer = asyncio.create_task(self._consume())
        self.task = asyncio.create_task(self._drive())

    def _decode(self, index):
        from ...competition_traffic.replay_input import iter_frames
        began = self.clock()
        item = self.items[index]
        # Reuse C4 validation/decoder. Selecting a subset must not renumber frames
        # or create a new epoch for every decoded image. These remain fixture IDs;
        # historical hardware metadata is retained, never declared synchronized.
        frame = next(iter_frames([replace(item, metadata={**item.metadata,
            'replay_time_s': self._offset(index)})], fps=self.fps, binding_id=self.binding_id))
        frame = replace(frame, sequence=index, producer_epoch='replay-' + self.run_id,
            received_s=self._offset(index) if self.clock_mode == 'source-timeline' else self._arrival(index),
            original_metadata={**frame.original_metadata, 'review_decode_started_s': began,
                               'review_decode_completed_s': self.clock()})
        return frame

    @staticmethod
    def _images(sample):
        import cv2
        from ...competition_traffic.artifacts import detection_overlay
        if sample.frame.bgr is None:
            return {}
        output = {}
        for name, pixels in (('original', sample.frame.bgr),
                             ('overlay', detection_overlay(sample.frame.bgr, sample.observation))):
            ok, encoded = cv2.imencode('.png', pixels)
            if not ok:
                raise ValueError('REVIEW_IMAGE_ENCODE_FAILED')
            output[name] = encoded.tobytes()
        return output

    def _encode(self, sample):
        began = self.clock()
        images = self._images(sample)
        if self.closed:
            self.counters['late_encode'] += 1
        return images, began, self.clock()

    def _measure(self, key, value):
        if value is None:
            return
        metric = self.metrics.setdefault(key, {'count': 0, 'sum': 0., 'max': 0., 'recent': deque(maxlen=256)})
        metric['count'] += 1
        metric['sum'] += value
        metric['max'] = max(metric['max'], value)
        metric['recent'].append(value)

    def _accept_result(self, sample):
        if self.closed:
            return
        self.processed += 1
        c = sample.observation.context
        self.counters['invalid_observation'] += int('IMAGE_DECODE_FAILED' in sample.observation.signal['quality_flags'])
        self.counts.update(d['raw_state'] for d in c['free_observations'])
        self._measure('worker_pending_s', sample.processing_started_s - sample.enqueued_s)
        self._measure('pipeline_wall_s', sample.completed_s - sample.processing_started_s)
        inference = c['review_inference_timing']
        if inference['inference_started_s'] is not None:
            self._measure('inference_wall_s', inference['inference_completed_s'] - inference['inference_started_s'])
        if self.clock_mode == 'wall-clock':
            self._measure('schedule_to_processing_s', sample.processing_started_s - self._arrival(sample.frame.sequence))
        if self.results.full():
            self.results.get_nowait()
            self.results.task_done()
            self.counters['replaced_display'] += 1
        self.results.put_nowait(sample)

    async def _drive(self):
        loop = asyncio.get_running_loop()
        index = 0
        try:
            while index < self.limit:
                if self.consumer.done():
                    self.consumer.result()
                    raise ValueError('REVIEW_CONSUMER_STOPPED')
                if self.clock_mode == 'wall-clock':
                    await asyncio.sleep(max(0., self._arrival(index) - self.clock()))
                if self.replay_mode == 'latest-wall-clock':
                    # Metadata-only seek to newest due frame; never decode an old
                    # FIFO after a slow decoder or event-loop scheduling delay.
                    while index + 1 < self.limit and self._arrival(index + 1) <= self.clock():
                        self.counters['input'] += 1
                        self.counters['dropped_before_decode'] += 1
                        index += 1
                self.counters['input'] += 1
                try:
                    frame = await loop.run_in_executor(self.decoder, self._decode, index)
                except Exception:
                    self.counters['invalid_decode'] += 1
                    raise
                meta = frame.original_metadata
                self.counters['decoded'] += 1
                self._measure('decode_wall_s', meta['review_decode_completed_s'] - meta['review_decode_started_s'])
                if (self.replay_mode == 'latest-wall-clock' and index + 1 < self.limit
                        and self._arrival(index + 1) <= self.clock()):
                    self.counters['dropped_after_decode'] += 1
                else:
                    if not self.worker.offer(frame):
                        raise ValueError('REPLAY_WORKER_CLOSED')
                    self.counters['offered'] += 1
                    if self.replay_mode == 'exhaustive':
                        await self.worker.queue.join()
                        if self.worker.error:
                            raise ValueError('REPLAY_WORKER_FAILED')
                        await self._drain_display()
                index += 1
            self.input_finished_s = self.clock()
            await self.worker.queue.join()
            await self._drain_display()
            self.state = 'FAILED' if self.worker.invalid else 'COMPLETE'
            self.error = self.worker.error if self.worker.invalid else None
        except asyncio.CancelledError:
            self.state = 'STOPPED'
            raise
        except Exception as exc:
            self.state, self.error = 'FAILED', type(exc).__name__
        finally:
            if self.state in ('FAILED', 'STOPPED'):
                self.closed = True
                await self.worker.close()
            self.consumer.cancel()
            await asyncio.gather(self.consumer, return_exceptions=True)
            self.decoder.shutdown(wait=False, cancel_futures=True)
            self.encoder.shutdown(wait=False, cancel_futures=True)

    async def _drain_display(self):
        join = asyncio.create_task(self.results.join())
        try:
            done, _ = await asyncio.wait((join, self.consumer), return_when=asyncio.FIRST_COMPLETED)
            if self.consumer in done:
                self.consumer.result()
        finally:
            if not join.done():
                join.cancel()
            await asyncio.gather(join, return_exceptions=True)

    async def _consume(self):
        loop = asyncio.get_running_loop()
        while True:
            sample = await self.results.get()
            try:
                images, encode_started, encode_completed = await loop.run_in_executor(self.encoder, self._encode, sample)
                if self.closed:
                    continue
                self._publish(sample, images, encode_started, encode_completed)
            finally:
                self.results.task_done()

    def _publish(self, sample, images, encode_started, encode_completed):
        frame, obs = sample.frame, sample.observation
        context, published = obs.context, self.clock()
        inspection = CompetitionIngress.review(sample,
            now=sample.processed_s if self.clock_mode == 'source-timeline' else published,
            inference_settings_sha256=self.pin)
        meta = frame.original_metadata
        scheduled = self._arrival(frame.sequence) if self.clock_mode == 'wall-clock' else None
        timing = {'clock': 'local_monotonic', 'scheduled_arrival_s': scheduled,
            'decode_started_s': meta['review_decode_started_s'], 'decode_completed_s': meta['review_decode_completed_s'],
            'enqueued_s': sample.enqueued_s, 'processing_started_s': sample.processing_started_s,
            **context['review_inference_timing'], 'pipeline_completed_s': sample.completed_s,
            'encode_started_s': encode_started, 'encode_completed_s': encode_completed, 'published_s': published}
        # Paths, source URLs and arbitrary original metadata never enter HTTP.
        record = {'sequence': frame.sequence, 'source_stamp_ns': frame.source_stamp_ns,
            'source_clock': frame.source_clock, 'producer_epoch': frame.producer_epoch,
            'recorded_offset_s': self._offset(frame.sequence), 'first_received_s': frame.received_s,
            'processed_s': context['processed_s'], 'stage': context['observation_stage'],
            'raw_state': obs.signal['raw_state'], 'stable_state': obs.signal['stable_state'],
            'quality_flags': obs.signal['quality_flags'], 'unknown_reason': context['diagnostics']['terminal_rejection'],
            'detections': copy.deepcopy(context['free_observations']), 'timing': timing,
            'queue_residence_s': context['queue_residence_s'],  # legacy: schedule -> processing, NOT queue length
            'worker_pending_s': sample.processing_started_s - sample.enqueued_s,
            'schedule_to_processing_s': sample.processing_started_s - scheduled if scheduled is not None else None,
            'pipeline_wall_s': sample.completed_s - sample.processing_started_s,
            'inference_wall_s': (timing['inference_completed_s'] - timing['inference_started_s']
                                 if timing['inference_started_s'] is not None else None),
            'encode_wall_s': encode_completed - encode_started,
            'publish_lag_s': published - scheduled if scheduled is not None else None,
            'observed_inference_settings_sha256': context['inference_settings_sha256'], **inspection}
        self.images.append((frame.sequence, images))
        self.record = record
        self.counters['published'] += 1
        self._measure('encode_wall_s', record['encode_wall_s'])
        self._measure('publish_lag_s', record['publish_lag_s'])
        self.trace.append({key: record[key] for key in ('sequence', 'source_stamp_ns', 'first_received_s',
            'stage', 'raw_state', 'stable_state', 'quality_flags', 'unknown_reason', 'pipeline_wall_s',
            'worker_pending_s', 'schedule_to_processing_s', 'encode_wall_s', 'publish_lag_s', 'inference_binding_matches')})

    def image(self, run_id, sequence, kind):
        if run_id != self.run_id or kind not in {'original', 'overlay'}:
            return None
        return next((images.get(kind) for seq, images in self.images if seq == sequence), None)

    def snapshot(self):
        metrics = {}
        for name, m in self.metrics.items():
            ordered = sorted(m['recent'])
            metrics[name] = {'count': m['count'], 'mean': m['sum'] / m['count'], 'max': m['max'],
                'percentile_window_count': len(ordered), 'p50': ordered[math.ceil(.5 * len(ordered)) - 1],
                'p95': ordered[math.ceil(.95 * len(ordered)) - 1]}
        counts = {key: self.counters[key] for key in ('input', 'decoded', 'offered', 'dropped_before_decode',
            'dropped_after_decode', 'published', 'replaced_display', 'late_encode')}
        counts.update(processed=self.processed, replaced_pending=self.worker.dropped,
            invalid=self.worker.invalid + self.counters['invalid_observation'] + self.counters['invalid_decode'],
            late_result=self.worker.late_results)
        return copy.deepcopy({'mode': 'PRIVATE_RECORDED_RGB' if self.private else 'SYNTHETIC_RGB_REVIEW',
            'replay_mode': self.replay_mode, 'clock_mode': self.clock_mode, 'state': self.state, 'run_id': self.run_id,
            'frames_processed': self.processed, 'input_frames': self.limit, 'counts': counts, 'latency_s': metrics,
            'coverage': self.processed / self.limit, 'input_finished_s': self.input_finished_s,
            'inference_settings_sha256': self.pin, 'profile': self.profile,
            'observation': self.record, 'trace': list(self.trace), 'detection_counts': dict(self.counts),
            'historical_clock_verified': False, 'departure_authorized': False,
            'actual_nav2_run': False, 'physical_motion': False, 'error': self.error,
            'notice': 'Recorded fixture only, not live or online qualification. TTL .25s and stability .4s unchanged. '
                      'Raw GREEN is not permission; failed emitter experiment remains unadopted. '
                      'Means cover all samples; percentiles cover at most the last 256 per stage.'})

    async def close(self):
        self.closed = True
        if self.task and not self.task.done():
            self.task.cancel()
        if self.task:
            await asyncio.gather(self.task, return_exceptions=True)
        await self.worker.close()
        if self.consumer:
            self.consumer.cancel()
            await asyncio.gather(self.consumer, return_exceptions=True)
        while not self.results.empty():
            self.results.get_nowait()
            self.results.task_done()
        self.decoder.shutdown(wait=False, cancel_futures=True)
        self.encoder.shutdown(wait=False, cancel_futures=True)
