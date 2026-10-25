"""Current packages at the C1 boundary; synthetic images are never real RGB proof."""
import asyncio
import copy
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from competition_integration.harness import SoftwareHarness


class ProfileSessionTests(SoftwareHarness, unittest.IsolatedAsyncioTestCase):
    source_clock = 'synchronized_ros'

    async def test_actual_profile_projection_join_and_normal_completion(self):
        await self.exit_ready()
        self.assertEqual(self.last_sample.observation.context['inference_settings_sha256'],
                         self.session.ingress.signal_binding.inference_settings_sha256)
        self.assertEqual(self.last_sample.observation.context['observation_stage'], 'stable')
        self.assertEqual(len(self.nav.sent), 2)

    async def test_same_model_new_tile_profile_retires_green_dwell_and_owner(self):
        await self.terminal()
        for _ in range(9):
            await self.tick()
        self.assertEqual(self.last_sample.observation.signal['stable_state'], 'GREEN')
        old_packet, old_sample = self.last_packet, self.last_sample
        self.worker.pipeline.detector.select_profile('upper-overlap640')
        with self.assertRaisesRegex(ValueError, 'INFERENCE_SETTINGS_MISMATCH'):
            await self.tick()
        self.assertTrue(self.session.closed)
        self.assertEqual(self.command()[0], (0., 0., 0.))
        self.assertEqual(len(self.nav.sent), 1)
        with self.assertRaisesRegex(ValueError, 'SESSION_RETIRED'):
            await self.session.observe('profile-old-green-retry', old_packet, sample=old_sample)
        self.assertEqual(len(self.nav.sent), 1)

    async def test_missing_profile_retires_session_without_mutating_raw_diagnostics(self):
        await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        sample = self.last_sample
        context = {k: v for k, v in sample.observation.context.items() if k != 'inference_settings_sha256'}
        bad = replace(sample, observation=replace(sample.observation, context=context))
        original = copy.deepcopy(bad.observation.json_record())
        with self.assertRaisesRegex(ValueError, 'INFERENCE_SETTINGS_MISMATCH'):
            await self.session.observe('missing-profile', self.last_packet, sample=bad)
        self.assertEqual(bad.observation.json_record(), original)
        self.assertTrue(self.session.closed)
        self.assertEqual(len(self.nav.sent), 1)

    async def test_detection_only_cannot_fill_mission_signal(self):
        self.worker.pipeline.observation_mode = 'detection-only'
        with self.assertRaisesRegex(ValueError, 'MISSION_OBSERVATION_REQUIRED'):
            await self.tick()
        sample = self.worker.latest
        self.assertEqual(sample.observation.context['free_observations'][0]['raw_state'], 'GREEN')
        self.assertEqual(self.command()[0], (0., 0., 0.))
        self.assertEqual(len(self.nav.sent), 1)


class RGBReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from competition_fixture_server import make_rgb_review, replay_options
        self.temp = tempfile.TemporaryDirectory()
        self.review = make_rgb_review(Path(self.temp.name), replay_options(['--synthetic-rgb-review']))
        self.review.start()
        await asyncio.wait_for(self.review.task, 5)

    async def asyncTearDown(self):
        await self.review.close()
        self.temp.cleanup()

    async def test_real_loader_worker_projection_boundary_keeps_rgb_without_motion_facts(self):
        result = self.review.snapshot()
        self.assertEqual(result['state'], 'COMPLETE')
        self.assertEqual(result['frames_processed'], 8)
        self.assertFalse(result['departure_authorized'])
        obs = result['observation']
        self.assertEqual(obs['stage'], 'detection-only')
        self.assertEqual(obs['stable_state'], 'UNKNOWN')
        self.assertEqual(obs['detections'][0]['raw_state'], 'GREEN')
        self.assertIn('OFFLINE_REPLAY_NOT_ROBOT_EVIDENCE', obs['projection_reasons'])
        self.assertTrue(obs['inference_binding_matches'])
        self.assertTrue(all(value is None for value in obs['independent_facts'].values()))
        self.assertNotIn(self.temp.name, str(result))
        for _ in range(5):
            self.assertEqual(self.review.snapshot(), result)
        self.assertTrue(self.review.image(result['run_id'], obs['sequence'], 'original').startswith(b'\x89PNG'))
        self.assertTrue(self.review.image(result['run_id'], obs['sequence'], 'overlay').startswith(b'\x89PNG'))
        self.assertIsNone(self.review.image(result['run_id'], 0, 'original'))
        self.assertIsNone(self.review.image('another-run', obs['sequence'], 'original'))
        self.assertIsNone(self.review.image(result['run_id'], obs['sequence'], '/etc/passwd'))
        self.assertLessEqual(len(self.review.images), 2)

    async def test_private_source_is_rejected_in_public_ci(self):
        from competition_fixture_server import replay_options
        with patch.dict(os.environ, {'CI': 'true'}), self.assertRaises(SystemExit):
            replay_options(['--private-replay-manifest', '/private/frames.jsonl',
                            '--replay-config', '/private/config.json', '--replay-model', '/private/model.pt'])


class DemoPublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_during_start_sees_only_initialized_session(self):
        from competition_integration.demo import SignalDemo
        entered, release = asyncio.Event(), asyncio.Event()
        setup = SoftwareHarness.asyncSetUp
        async def delayed(harness):
            entered.set()
            await release.wait()
            await setup(harness)
        demo = SignalDemo()
        with patch.object(SoftwareHarness, 'asyncSetUp', delayed):
            task = asyncio.create_task(demo.start('normal', 'concurrent-snapshot'))
            try:
                await entered.wait()
                self.assertEqual(demo.snapshot()['phase'], 'NOT_STARTED')
                release.set()
                await task
                self.assertNotEqual(demo.snapshot()['phase'], 'NOT_STARTED')
            finally:
                release.set()
                await task
                await demo.close()
