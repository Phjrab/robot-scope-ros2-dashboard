"""Actual latest C4 Observation/projection -> C2 join/runtime -> C1 session."""
import unittest
from dataclasses import replace
from unittest.mock import patch

from competition_integration.harness import SoftwareHarness
from competition_traffic.helpers import frame
from robot_dashboard.competition_traffic.projection import signal_fragment, signal_status
from robot_dashboard.competition_traffic.worker import SignalSample
from robot_dashboard.mission_routes.competition_native.runtime import NativeRuntime


class TimeContractTests(SoftwareHarness, unittest.IsolatedAsyncioTestCase):
    source_clock = 'synchronized_ros'

    async def delayed_sample(self, *, queue=.04, inference=.08, age=.03):
        self.number += 1
        self.clock.now += .1
        first = self.clock.now
        f = frame(self.number, source_clock=self.source_clock, received_s=first,
                  source_stamp_ns=str(round(first * 1e9)), source_age_s=age)
        self.clock.now += queue
        detector = self.worker.pipeline.detector
        original = detector.infer
        def infer(image):
            self.clock.now += inference
            return original(image)
        with patch.object(detector, 'infer', side_effect=infer):
            observation = self.worker.pipeline.process(f, now_s=self.clock.now)
        return SignalSample(f, observation, observation.context['processed_s'])

    async def deliver(self, sample, key='time-contract-event-01'):
        packet = self.rig.packet(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        packet = replace(packet, evidence={**packet.evidence, **self.session.port.goal_observation(self.session.adapter.scope)})
        return await self.session.observe(key, packet, sample=sample)

    async def test_queue_and_positive_inference_delay_use_first_age_exactly_once(self):
        sample = await self.delayed_sample()
        await self.deliver(sample)
        self.assertIsInstance(self.session.runtime, NativeRuntime)
        received = self.session.adapter.normalizer.received['signal']
        self.assertAlmostEqual(received.receipt_s, .1)
        self.assertAlmostEqual(received.stamp.source_age_s, .03)
        self.assertAlmostEqual(sample.observation.context['receiver_age_s'], .12)
        # New envelope with identical signal does not refresh first receipt.
        self.clock.now += .05
        await self.deliver(sample, 'time-contract-event-02')
        self.assertAlmostEqual(self.session.adapter.normalizer.received['signal'].receipt_s, .1)
        self.clock.now += .051
        with self.assertRaisesRegex(ValueError, 'EXPIRED'):
            await self.deliver(sample, 'time-contract-event-03')
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_first_receipt_mismatch_is_actual_projection_error(self):
        sample = await self.delayed_sample()
        with self.assertRaisesRegex(ValueError, 'FIRST_RECEIPT_MISMATCH'):
            signal_fragment(sample.observation, now_s=self.clock.now, received_s=sample.processed_s)
        with self.assertRaisesRegex(ValueError, 'FIRST_RECEIPT_MISMATCH'):
            await self.deliver(replace(sample, frame=replace(sample.frame, received_s=sample.processed_s)))

    async def test_identical_bytes_new_verified_frames_are_not_replays_and_polling_expires(self):
        for _ in range(6):
            await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        self.assertEqual(self.last_sample.observation.signal['stable_state'], 'GREEN')
        first = self.last_sample.observation.context['first_received_s']
        for _ in range(1000):
            status = signal_status(self.worker.pipeline, now_s=self.clock.now)
            self.assertEqual(status['first_received_s'], first)
        self.clock.now += .251
        self.assertIsNone(signal_status(self.worker.pipeline, now_s=self.clock.now)['fragment'])
        with self.assertRaisesRegex(ValueError, 'EXPIRED'):
            await self.deliver(self.last_sample)

    async def test_same_stamp_retransmission_cannot_refresh_or_authorize(self):
        sample = await self.delayed_sample(queue=0, inference=0)
        await self.deliver(sample)
        self.clock.now += .1
        f = replace(sample.frame, received_s=self.clock.now)
        obs = self.worker.pipeline.process(f, now_s=self.clock.now)
        self.assertEqual(obs.context['first_received_s'], sample.frame.received_s)
        self.assertIn('REPEATED_OR_REVERSED_FRAME', obs.signal['quality_flags'])
        with self.assertRaisesRegex(ValueError, 'FIRST_RECEIPT_MISMATCH'):
            await self.deliver(SignalSample(f, obs, obs.context['processed_s']), 'time-retransmitted-01')
        self.assertEqual(len(self.nav.sent), 1)

    async def test_unknown_source_clock_is_rejected(self):
        sample = await self.delayed_sample()
        bad = replace(sample.frame, source_clock='unknown', clock_verified=False)
        with self.assertRaisesRegex(ValueError, 'FRAME_METADATA_INVALID'):
            self.worker.pipeline.process(bad, now_s=self.clock.now)
        # Supported clock label without a verified clock relation is also closed.
        bad = replace(sample.frame, sequence=sample.frame.sequence+1, clock_verified=False)
        obs = self.worker.pipeline.process(bad, now_s=self.clock.now)
        with self.assertRaisesRegex(ValueError, 'EXPIRED'):
            await self.deliver(SignalSample(bad, obs, obs.context['processed_s']))

    async def test_epoch_change_and_two_signal_association_mismatch_fail_closed(self):
        sample = await self.delayed_sample()
        for bad in (replace(sample, frame=replace(sample.frame, producer_epoch='new-epoch')),
                    replace(sample, observation=replace(sample.observation,
                        signal={**sample.observation.signal, 'crossing_id':'other-crossing'}))):
            with self.assertRaisesRegex(ValueError, 'SIGNAL_BINDING'):
                await self.deliver(bad)
        self.assertEqual(len(self.nav.sent), 1)

    async def test_mixed_context_age_is_rejected_by_actual_c2_join(self):
        sample = await self.delayed_sample()
        altered = replace(sample.observation,
            context={**sample.observation.context, 'source_age_s': .03})
        with self.assertRaisesRegex(ValueError, 'CONTRADICTORY_AGE'):
            await self.deliver(replace(sample, observation=altered))
        self.assertEqual(len(self.nav.sent), 1)
