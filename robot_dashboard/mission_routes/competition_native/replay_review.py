"""C1 loopback inspection: existing C4 loader -> worker -> read-only ingress.

No navigation port or mission session is constructed here. Private pixels stay
in bounded memory and are never written to the public browser artifact tree.
"""
from __future__ import annotations

import asyncio
from collections import Counter, deque
import copy
from dataclasses import replace
import re
import time

from .ingress import CompetitionIngress


class RGBReplayReview:
    def __init__(self, items, config, detector, *, fps, max_frames=10000,
                 private=True, observation_mode='detection-only', clock=time.monotonic):
        from ...competition_traffic.pipeline import TrafficPipeline
        from ...competition_traffic.replay_input import iter_frames
        from ...competition_traffic.worker import TrafficWorker
        pin = getattr(detector, 'inference_settings_sha256', None)
        if not isinstance(pin, str) or not re.fullmatch(r'[0-9a-f]{64}', pin):
            raise ValueError('EXPLICIT_INFERENCE_SETTINGS_PIN_REQUIRED')
        self.pin, self.clock, self.private = pin, clock, private
        self.profile = copy.deepcopy(detector.inference_settings)
        self.frames = iter_frames(items, fps=fps, max_frames=max_frames,
                                  binding_id=config.document['association']['binding_id'])
        self.worker = TrafficWorker(TrafficPipeline(config, detector, clock=clock,
            measure_wall_latency=True, observation_mode=observation_mode), clock=clock)
        self.task = None
        self.state = 'READY'
        self.error = None
        self.record = None
        self.trace = deque(maxlen=64)
        self.images = deque(maxlen=2)
        self.counts = Counter()
        self.processed = 0
        self.run_id = None
        self.anchor = self.first_source = self.previous_source = None

    def start(self):
        if self.task is not None:
            raise ValueError('REPLAY_ALREADY_STARTED')
        import secrets
        self.run_id = secrets.token_hex(16)
        self.worker.start()
        self.state = 'RUNNING'
        self.task = asyncio.create_task(self._drive())

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

    async def _drive(self):
        loop = asyncio.get_running_loop()
        try:
            while True:
                frame = await loop.run_in_executor(self.worker.executor, lambda: next(self.frames, None))
                if frame is None:
                    break
                source = frame.received_s
                if self.previous_source is not None and source <= self.previous_source:
                    raise ValueError('REPLAY_TIMELINE_NOT_INCREASING')
                self.previous_source = source
                if self.anchor is None:
                    self.anchor, self.first_source = self.clock(), source
                receipt = self.anchor + source - self.first_source
                await asyncio.sleep(max(0., receipt - self.clock()))
                frame = replace(frame, received_s=receipt)
                self.worker.offer(frame)
                await self.worker.queue.join()
                sample = self.worker.latest
                if sample is None:
                    raise ValueError('REPLAY_WORKER_FAILED')
                inspection = CompetitionIngress.review(sample, now=self.clock(), inference_settings_sha256=self.pin)
                obs, context = sample.observation, sample.observation.context
                # Explicit allowlist: original local paths/URLs and metadata never
                # enter the HTTP snapshot. Frames are fetched by opaque run/sequence.
                record = {'sequence': frame.sequence, 'source_stamp_ns': frame.source_stamp_ns,
                    'recorded_offset_s': source, 'first_received_s': frame.received_s,
                    'processed_s': context['processed_s'], 'stage': context['observation_stage'],
                    'raw_state': obs.signal['raw_state'], 'stable_state': obs.signal['stable_state'],
                    'quality_flags': obs.signal['quality_flags'],
                    'unknown_reason': context['diagnostics']['terminal_rejection'],
                    'detections': copy.deepcopy(context['free_observations']),
                    'queue_residence_s': context['queue_residence_s'],
                    'pipeline_wall_s': context['pipeline_wall_s'],
                    'inference_wall_s': context['diagnostics'].get('detector', {}).get('inference_wall_s'),
                    'observed_inference_settings_sha256': context['inference_settings_sha256'], **inspection}
                images = await loop.run_in_executor(self.worker.executor, lambda: self._images(sample))
                self.images.append((frame.sequence, images))
                self.record = record
                self.processed += 1
                self.counts.update(d['raw_state'] for d in record['detections'])
                self.trace.append({key: record[key] for key in ('sequence', 'stage', 'raw_state',
                    'stable_state', 'unknown_reason', 'pipeline_wall_s', 'inference_binding_matches')})
            self.state = 'COMPLETE'
        except asyncio.CancelledError:
            self.state = 'STOPPED'
            raise
        except Exception as exc:
            self.state, self.error = 'FAILED', type(exc).__name__

    def image(self, run_id, sequence, kind):
        if run_id != self.run_id or kind not in {'original', 'overlay'}:
            return None
        return next((images.get(kind) for seq, images in self.images if seq == sequence), None)

    def snapshot(self):
        return copy.deepcopy({'mode': 'PRIVATE_RECORDED_RGB' if self.private else 'SYNTHETIC_RGB_REVIEW',
            'state': self.state, 'run_id': self.run_id, 'frames_processed': self.processed,
            'inference_settings_sha256': self.pin, 'profile': self.profile,
            'observation': self.record, 'trace': list(self.trace), 'detection_counts': dict(self.counts),
            'historical_clock_verified': False, 'departure_authorized': False,
            'actual_nav2_run': False, 'physical_motion': False, 'error': self.error,
            'notice': 'Raw GREEN is not permission. C4 historical tile audit: 3 false GREEN signs and 28 unsupported housings; latency may exceed 0.25 s. No real stable GREEN qualification.'})

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
        if self.task:
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.worker.close()
