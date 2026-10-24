"""Explicit synthetic contract evidence only; never ROS/robot qualification."""
import asyncio
import copy
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from robot_dashboard.mission_routes.competition_contract import capabilities, template_visits, arena_view
from robot_dashboard.mission_routes.competition_executor import ContractExecutor, FixtureAdapter, new_fixture_state
from robot_dashboard.mission_routes.models import CreateRequest, DefinitionInput, FixtureRunRequest, RunActionRequest, UpdateRequest, digest
from robot_dashboard.mission_routes.service import MissionRoutes
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.application.mission_coordinator import MissionConflict
import test_mission_route_service as base


class Clock:
    value = 0.0
    def __call__(self):
        return self.value


def definition(index=None):
    template = template_visits()
    visits = template['visits'] if index is None else [template['visits'][index]]
    return DefinitionInput.model_validate({**base.body().model_dump(exclude={'request_id'}), 'visits': visits, 'competition': template['competition']}).model_dump()


def executor(index=1, scenario='normal'):
    d, clock = definition(index), Clock()
    run = {'id': 'a'*32, 'definition': d, 'events': [], 'snapshot_pins': {'map_family': d['map_family'], 'competition': d['competition']}, 'fixture_state': new_fixture_state('a'*32, d)}
    run['fixture_state']['state'] = 'running'
    adapter = FixtureAdapter(scenario, clock=clock)
    return ContractExecutor(run, adapter, clock=clock), adapter, clock


def advance(engine, clock, seconds, **changes):
    for _ in range(round(seconds / .25)):
        clock.value += .25
        if engine.state['state'] != 'running':
            break
        evidence = engine.adapter.sample(engine.state).model_copy(update=changes)
        engine.tick(evidence)


class CompetitionContractTests(unittest.TestCase):
    def test_legacy_definition_hash_and_bytes_shape_survive(self):
        original = base.body().model_dump(exclude={'request_id'})
        self.assertNotIn('competition', original)
        self.assertNotIn('mission_action', original['visits'][0])
        self.assertEqual(digest(original), digest(DefinitionInput.model_validate(original).model_dump()))

    def test_draft_template_has_no_coordinates_and_new_visit_and_step_ids(self):
        one, two = template_visits(), template_visits()
        self.assertEqual(len(one['visits']), 6)
        self.assertTrue(all(v['pose'] is None and v['target'] == 'unplaced' for v in one['visits']))
        self.assertFalse({v['visit_id'] for v in one['visits']} & {v['visit_id'] for v in two['visits']})
        self.assertFalse({v['mission_action']['step_id'] for v in one['visits']} & {v['mission_action']['step_id'] for v in two['visits']})

    def test_minimums_finite_and_no_operator_or_legacy_bypass(self):
        for field, value in [('dwell_seconds', 1.99), ('sit_seconds', 4.99), ('dwell_seconds', float('nan'))]:
            data = definition(1)
            data['visits'][0]['mission_action'][field] = value
            with self.assertRaises(ValidationError):
                DefinitionInput.model_validate(data)
        for field, value in [('requires_operator_confirmation', True), ('after_arrival_confirmation', True), ('hold_seconds', 2.0), ('action', 'sit_then_rise'), ('arrival_tolerance', .1)]:
            data = definition(1)
            data['visits'][0][field] = value
            with self.assertRaises(ValidationError):
                DefinitionInput.model_validate(data)

    def test_duplicate_step_ids_and_fake_review_are_rejected(self):
        data = definition()
        data['visits'][1]['mission_action']['step_id'] = data['visits'][0]['mission_action']['step_id']
        with self.assertRaises(ValidationError):
            DefinitionInput.model_validate(data)
        data = definition()
        data['competition']['review_status'] = 'REVIEWED'
        with self.assertRaises(ValidationError):
            DefinitionInput.model_validate(data)

    def test_capabilities_are_step_specific_without_robot_claims(self):
        c = capabilities()
        self.assertFalse(c['native_enabled'])
        self.assertEqual(c['actions']['TRAFFIC_STOP_AND_GO']['stage'], 'PRESENT')
        self.assertIn('feet_evidence', [v['id'] for v in c['actions']['TRAFFIC_STOP_AND_GO']['components']])
        self.assertIn('posture_executor', [v['id'] for v in c['actions']['PARK_SIT_HOLD']['components']])

    def test_vm_manifest_uses_published_hashes_without_registration_or_native_promotion(self):
        from robot_dashboard.mission_routes.competition_assets import arena_manifest, vm_evidence, checked_file
        value = arena_manifest()
        self.assertTrue(value['available'])
        self.assertFalse(value['pose_overlay_allowed'])
        self.assertEqual(value['course_status'], 'DRAFT')
        self.assertEqual(value['revision'], 'rulebook-20261015-v1')
        self.assertEqual(vm_evidence()['traffic_signals']['scope'], 'SYNTHETIC_ONLY')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'asset').write_bytes(b'changed')
            (root/'SHA256SUMS.txt').write_text('0'*64+'  asset\n')
            with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
                checked_file(root, 'asset')

    def test_glb_file_and_metadata_do_not_prove_alignment(self):
        manifest = {'arena_id': 'arena', 'revision': 'r1', 'visual_asset': 'arena.glb'}
        self.assertFalse(arena_view(manifest, map_id='map', map_revision='m1', arena_revision='r1')['pose_overlay_allowed'])
        manifest['alignment'] = {'status': 'VERIFIED', 'map_id': 'map', 'map_revision': 'm1', 'arena_revision': 'r1', 'T_map_arena_design': [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]}
        self.assertTrue(arena_view(manifest, map_id='map', map_revision='m1', arena_revision='r1')['pose_overlay_allowed'])
        manifest['heartbeat'] = 99
        manifest['display_name'] = 'renamed'
        self.assertTrue(arena_view(manifest, map_id='map', map_revision='m1', arena_revision='r1')['pose_overlay_allowed'])
        self.assertFalse(arena_view(manifest, map_id='map', map_revision='m2', arena_revision='r1')['pose_overlay_allowed'])


class CompetitionExecutorTests(unittest.TestCase):
    def test_normal_green_completes_with_fresh_new_exit_generation(self):
        e, adapter, clock = executor()
        first = copy.deepcopy(adapter.commands[0])
        advance(e, clock, 4)
        self.assertEqual(e.state['state'], 'completed')
        self.assertEqual([c['leg'] for c in adapter.commands], ['approach', 'exit'])
        self.assertGreater(adapter.commands[1]['goal_generation'], first['goal_generation'])
        self.assertEqual(first['action'], e.run['definition']['visits'][0]['mission_action'])
        self.assertEqual(first['visit'], e.run['definition']['visits'][0])
        self.assertEqual([c['mode'] for c in adapter.constraints], ['HOLD', 'RELEASE'])
        self.assertTrue(all(c['owner_id'] == adapter.owner_id for c in adapter.constraints))

    def test_red_unknown_one_foot_stale_image_missing_pose_are_distinct(self):
        expected = {'red': 'SIGNAL_RED', 'unknown': 'SIGNAL_UNKNOWN', 'one_foot': 'BOTH_FEET_AND_PHYSICAL_STOP_REQUIRED', 'stale_image': 'CAMERA_STALE', 'missing_pose': 'CURRENT_POSE_MISSING'}
        for scenario, reason in expected.items():
            with self.subTest(scenario=scenario):
                e, a, clock = executor(scenario=scenario)
                advance(e, clock, 4)
                self.assertEqual(e.state['reason'], reason)
                self.assertEqual(len(a.commands), 1)
                self.assertNotIn('RELEASE', [c['mode'] for c in a.constraints])

    def test_final_persistence_failure_can_replace_unaudited_completion(self):
        e, _, clock = executor(index=0)
        advance(e, clock, 1)
        self.assertEqual(e.state['state'], 'completed')
        e.fail('FIXTURE_BACKEND_FAILED')
        self.assertEqual(e.state['state'], 'failed')
        self.assertEqual(e.state['reason'], 'FIXTURE_BACKEND_FAILED')
        self.assertEqual(e.run['events'][-1]['event'], 'FIXTURE_BACKEND_FAILED')

    def test_less_than_two_seconds_cannot_depart(self):
        e, a, clock = executor()
        advance(e, clock, 2.5)
        self.assertLess(e.state['dwell_elapsed_s'], 2)
        self.assertEqual(len(a.commands), 1)
        advance(e, clock, .5)
        self.assertEqual(len(a.commands), 2)

    def test_approach_requires_terminal_and_cancel_ack_then_hold_ack(self):
        e, a, clock = executor()
        advance(e, clock, 3, goal_state='ACTIVE')
        self.assertEqual(e.state['phase'], 'FOLLOWING')
        self.assertEqual(a.constraints, [])
        advance(e, clock, .25, goal_state='CANCELED', cancel_ack=False)
        self.assertEqual(e.state['reason'], 'CANCEL_ACK_REQUIRED')
        advance(e, clock, .25, goal_state='CANCELED', cancel_ack=True)
        self.assertEqual(e.state['phase'], 'HOLD_SIGNAL')
        advance(e, clock, 3, hold_ack=False)
        self.assertEqual(len(a.commands), 1)

    def test_wrong_signal_crossing_proxy_motion_and_no_path_cannot_release(self):
        for patch in [{'signal_id': 'other'}, {'crossing_id': 'other'}, {'feet_evidence_kind': 'PROXY'}, {'body_motion_status': 'MOVING'}, {'path_clear': False}]:
            e, a, clock = executor()
            advance(e, clock, 4, **patch)
            self.assertEqual(len(a.commands), 1, patch)

    def test_signal_hold_is_not_nav_progress_failure_but_approach_failure_is(self):
        e, a, clock = executor(scenario='red')
        advance(e, clock, 1)
        advance(e, clock, 4, goal_state='FAILED')
        self.assertEqual(e.state['phase'], 'HOLD_SIGNAL')
        self.assertEqual(e.state['state'], 'running')
        failed, _, timer = executor(scenario='nav_failure')
        advance(failed, timer, .25)
        self.assertEqual(failed.state['outcome'], 'NAVIGATION_PROGRESS_FAILED')
        obstacle, _, timer = executor(scenario='obstacle')
        advance(obstacle, timer, 4)
        self.assertEqual(obstacle.state['reason'], 'WAIT_OBSTACLE')
        self.assertEqual(obstacle.state['phase'], 'FOLLOWING')

    def test_gap_loss_stale_and_replay_reset_continuous_dwell(self):
        for patch in [{'front_right_status':'UNKNOWN'}, {'source_age_s': .51}, {'sequence': 0}, {'producer_epoch':'other'}, {'goal_generation': 999}, {'mission_run_id':'b'*32}]:
            e, _, clock = executor()
            advance(e, clock, 2)
            self.assertGreater(e.state['dwell_elapsed_s'], 0)
            advance(e, clock, .25, **patch)
            self.assertEqual(e.state['dwell_elapsed_s'], 0, patch)
        e, a, clock = executor()
        advance(e, clock, 2)
        clock.value += 2
        advance(e, clock, .25)
        self.assertEqual(e.state['dwell_elapsed_s'], 0)
        self.assertEqual(len(a.commands), 1)

    def test_old_exit_result_cannot_complete_new_leg(self):
        e, a, clock = executor()
        advance(e, clock, 2.5)
        stale = a.sample(e.state)
        advance(e, clock, .5)
        self.assertEqual(e.state['phase'], 'EXITING')
        e.tick(stale)
        self.assertEqual(e.state['state'], 'running')
        self.assertEqual(e.state['reason'], 'STALE_OWNER_OR_GENERATION')
        advance(e, clock, 1)
        self.assertEqual(e.state['state'], 'completed')

    def test_park_requires_five_seconds_after_sit_and_full_containment(self):
        e, _, clock = executor(index=4)
        advance(e, clock, 3, posture='STAND')
        self.assertEqual(e.state['dwell_elapsed_s'], 0)
        advance(e, clock, 3, full_body_inside=False)
        self.assertEqual(e.state['dwell_elapsed_s'], 0)
        advance(e, clock, 5)
        self.assertEqual(e.state['state'], 'running')
        advance(e, clock, .25)
        self.assertEqual(e.state['state'], 'completed')

    def test_terrain_and_finish_need_completion_evidence(self):
        for index, patch in [(2, {'terrain_complete':False}), (5, {'full_body_crossed':False})]:
            e, _, clock = executor(index=index)
            advance(e, clock, 4, **patch)
            self.assertEqual(e.state['state'], 'running')
            advance(e, clock, .25)
            self.assertEqual(e.state['state'], 'completed')

    def test_full_template_runs_without_client_and_has_no_fake_paths(self):
        e, a, clock = executor(index=None)
        advance(e, clock, 30)
        self.assertEqual(e.state['state'], 'completed')
        self.assertEqual(e.state['completed_count'], 6)
        self.assertEqual(len(a.commands), 8)
        self.assertEqual(e.run['snapshot_pins']['competition'], e.run['definition']['competition'])


class CompetitionServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base.MissionRouteServiceTests.setUp(self)

    async def asyncTearDown(self):
        await self.service.close()
        await self.coordinator.close()
        self.temp.cleanup()

    async def create(self):
        return (await self.service.write(CreateRequest.model_validate({**definition(1), 'request_id':'competition-plan-01'})))['plan']

    async def create_run(self, entry):
        return await self.service.create_fixture_run(entry['id'], FixtureRunRequest(request_id='fixture-create-001', revision=entry['revision']))

    async def test_saved_fields_reach_real_backend_fixture_adapter_and_native_blocked(self):
        entry = await self.create()
        reread = self.service.definition(entry['id'])
        self.assertEqual(reread, entry)
        report = self.service.validate(entry['id'], entry['revision'])
        self.assertIn('STEP_COORDINATES_DRAFT', report['authoring_reasons'])
        self.assertIn('FEET_EVIDENCE_UNCONNECTED', report['execution_readiness']['steps'][0]['blocking_reasons'])
        with self.assertRaises(MissionConflict):
            await self.service.create_run(entry['id'], base.req(entry['revision']))
        run = await self.create_run(entry)
        identifier = run['run']['id']
        await self.service.action(identifier, 'start', RunActionRequest(request_id='fixture-start-0001'))
        command = self.service.fixture_runs.executors[identifier].adapter.commands[0]
        self.assertEqual(command['visit'], reread['definition']['visits'][0])
        self.assertEqual(command['snapshot_pins'], run['run']['snapshot_pins'])
        self.assertEqual(self.nav.sent, [])
        self.assertFalse(self.coordinator.blocks_navigation_goal())

    async def test_request_replay_duplicate_start_abort_and_no_manual_bypass(self):
        entry = await self.create()
        run = await self.create_run(entry)
        self.assertEqual(run['run']['id'], (await self.create_run(entry))['run']['id'])
        identifier = run['run']['id']
        request = RunActionRequest(request_id='fixture-start-0001')
        await self.service.action(identifier, 'start', request)
        await self.service.action(identifier, 'start', request)
        await self.service.action(identifier, 'start', RunActionRequest(request_id='fixture-start-0002'))
        self.assertEqual(len(self.service.fixture_runs.executors[identifier].adapter.commands), 1)
        with self.assertRaises(MissionConflict):
            await self.service.action(identifier, 'skip', RunActionRequest(request_id='fixture-skip-00001'))
        request = RunActionRequest(request_id='fixture-abort-001')
        await self.service.action(identifier, 'abort', request)
        await self.service.action(identifier, 'abort', request)
        self.assertEqual(self.service.run(identifier)['mission']['outcome'], 'FIXTURE_ABORTED')
        with self.assertRaises(MissionConflict):
            await self.service.action(identifier, 'start', RunActionRequest(request_id='fixture-start-0003'))

    async def test_browser_absence_and_reconnect_read_server_timer(self):
        entry = await self.create()
        run = await self.create_run(entry)
        identifier = run['run']['id']
        await self.service.action(identifier, 'start', RunActionRequest(request_id='fixture-start-0001'))
        await asyncio.sleep(1.05)  # No HTTP requests/subscriptions are needed to progress.
        snapshot = self.service.run(identifier)
        self.assertGreater(snapshot['mission']['elapsed_s'], .5)
        self.assertEqual(snapshot['mission']['phase'], 'HOLD_SIGNAL')
        self.assertEqual(snapshot['mission']['timer_owner'], 'onboard_backend')
        self.assertEqual(snapshot['run']['trajectory'], [])
        self.assertEqual(snapshot['run']['live_plan']['reason'], 'FIXTURE_NO_NATIVE_PATH')

    async def test_restart_interrupts_without_restoring_green_dwell_or_owner(self):
        entry = await self.create()
        run = await self.create_run(entry)
        identifier = run['run']['id']
        await self.service.action(identifier, 'start', RunActionRequest(request_id='fixture-start-0001'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Copy crash-time store before the graceful close path can alter it.
            from robot_dashboard.mission_routes.store import PlanStore
            store = PlanStore(root)
            store.save(self.service.data)
            restarted = MissionRoutes(root, self.maps, self.routes, self.coordinator, self.context, self.planner)
            snapshot = restarted.run(identifier)['mission']
            self.assertEqual(snapshot['outcome'], 'interrupted')
            self.assertEqual(snapshot['dwell_elapsed_s'], 0)
            self.assertIsNone(snapshot['observation'])
            self.assertIsNone(snapshot['goal_id'])
            self.assertFalse(restarted.fixture_runs.tasks)
            with self.assertRaises(MissionConflict):
                await restarted.action(identifier, 'start', RunActionRequest(request_id='fixture-restart-01'))
            await restarted.close()

    async def test_active_definition_copy_required_and_snapshot_immutable(self):
        entry = await self.create()
        run = await self.create_run(entry)
        await self.service.action(run['run']['id'], 'start', RunActionRequest(request_id='fixture-start-0001'))
        changed = UpdateRequest.model_validate({**entry['definition'], 'label':'changed', 'request_id':'fixture-edit-00001', 'base_revision':entry['revision']})
        with self.assertRaisesRegex(MissionConflict, 'ACTIVE_COPY'):
            await self.service.write(changed, identifier=entry['id'])
        self.assertEqual(self.service.run(run['run']['id'])['run']['definition'], entry['definition'])
        exported = self.service.export_run(run['run']['id'])
        self.assertFalse(exported['executable'])
        self.assertFalse(exported['actual_nav2_run'])

    async def test_semantic_revision_change_requires_recheck_but_pose_heartbeat_does_not(self):
        entry = await self.create()
        run = await self.create_run(entry)
        identifier = run['run']['id']
        await self.service.action(identifier, 'start', RunActionRequest(request_id='fixture-start-0001'))
        self.nav.seq += 1
        self.nav.pose = base.pose(1.6, 2.0)
        await asyncio.sleep(.25)
        self.assertEqual(self.service.run(identifier)['mission']['state'], 'running')
        self.nav.job = 'new-generation'
        await asyncio.sleep(.25)
        self.assertEqual(self.service.run(identifier)['mission']['outcome'], 'RUN_CONTEXT_CHANGED_REVALIDATE')

    async def test_storage_failure_stops_fixture_and_does_not_display_old_running_state(self):
        entry = await self.create()
        run = await self.create_run(entry)
        identifier = run['run']['id']
        await self.service.action(identifier, 'start', RunActionRequest(request_id='fixture-start-0001'))
        original = self.service.store.save
        def fail(_):
            raise OSError('synthetic disk failure')
        self.service.store.save = fail
        try:
            await asyncio.sleep(.3)
            self.assertEqual(self.service.run(identifier)['mission']['state'], 'failed')
            self.assertEqual(self.service.run(identifier)['mission']['reason'], 'FIXTURE_BACKEND_FAILED')
        finally:
            self.service.store.save = original

    async def test_http_save_reload_fixture_dispatch_and_native_endpoint_denial(self):
        from fastapi import FastAPI
        from types import SimpleNamespace
        from robot_dashboard.api.routers.mission_routes import router
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.runtime = ApplicationRuntime(mission_routes=self.service, competition=SimpleNamespace(require_unlocked=lambda _: None))
        async def request(method, path, body=None, **kwargs):
            return await base.MissionRouteHttpTests.request(self, method, path, body, **kwargs)
        self.assertEqual(await request('GET', '/api/v1/mission-competition/capabilities'), 200)
        self.assertFalse(self.last_response['native_enabled'])
        payload = {**definition(1), 'request_id':'http-plan-0000001'}
        self.assertEqual(await request('POST', '/api/v1/mission-plans', payload), 201)
        entry = self.last_response['plan']
        self.assertEqual(await request('GET', '/api/v1/mission-plans/' + entry['id']), 200)
        self.assertEqual(self.last_response['plan']['definition'], entry['definition'])
        path = '/api/v1/mission-plans/' + entry['id']
        self.assertEqual(await request('POST', path + '/runs', {'request_id':'http-native-00001', 'revision':entry['revision']}), 409)
        body = {'request_id':'http-fixture-0001', 'revision':entry['revision'], 'scenario':'normal'}
        self.assertEqual(await request('POST', path + '/fixture-runs', body, origin='https://evil.example'), 403)
        self.assertEqual(await request('POST', path + '/fixture-runs', {**body, 'mode':'native'}), 422)
        self.assertEqual(await request('POST', path + '/fixture-runs', body), 201)
        run = self.last_response['run']
        self.assertEqual(await request('POST', '/api/v1/mission-runs/' + run['id'] + '/start', {'request_id':'http-start-000001'}), 200)
        dispatched = self.service.fixture_runs.executors[run['id']].adapter.commands[0]
        self.assertEqual(dispatched['action'], entry['definition']['visits'][0]['mission_action'])
        self.assertEqual(self.nav.sent, [])
