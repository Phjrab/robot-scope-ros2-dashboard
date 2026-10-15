import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from pydantic import ValidationError

from test_spatial_routes import MapProvider, family, MAP_ID, MAP_REVISION, pose, normalized
from robot_dashboard.application.mission_coordinator import MissionCoordinator, MissionConflict, MissionUnavailable
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.mission_routes.models import CreateRequest, UpdateRequest, RevisionRequest, PreviewRequest, RunActionRequest
from robot_dashboard.mission_routes.context import NavigationContext
from robot_dashboard.mission_routes.service import MissionRoutes
from robot_dashboard.mission_routes.planner import NativePlanner
from robot_dashboard.api.routers.mission_routes import router


class Navigation:
    def __init__(self):
        self.goal = {'state': 'idle', 'goal_id': None}
        self.sent = []
        self.job = 'nav-job-1'
        self.pose = pose(1.5, 2.0)
        self.seq = 1
        self.goal_admission = True
        self.pose_fresh = True

    def view(self):
        return {'seq': self.seq, 'pipeline': {'state': 'running', 'job_id': self.job}, 'localization_pipeline': {'job_id': 'lio-job-1'}, 'map': {'id': MAP_ID, 'revision': MAP_REVISION}, 'bindings': {'localization_pose':'/amcl_pose','localization_odometry': '/Odometry'}, 'readiness':{'localization':self.pose_fresh}, 'localization': {'state': 'localized', 'pose': self.pose}, 'safety': {'can_send_goal': self.goal_admission}, 'goal': dict(self.goal)}

    async def send_goal(self, **kwargs):
        self.sent.append(kwargs)
        self.goal = {'state': 'active', 'goal_id': f'{len(self.sent):032x}'}
        return {'navigation': self.view()}

    async def cancel_goal(self, *, goal_id):
        self.goal = {'state': 'canceled', 'goal_id': goal_id}
        return {'navigation': self.view()}


class FixturePlanner:
    def __init__(self):
        self.calls = []
        self.actual = False
        self.middle = None
        self.frame = 'map'

    async def plan(self, start, goal):
        self.calls.append((start, goal))
        return {'poses': [start, *([self.middle] if self.middle else []), goal], 'frame': self.frame, 'actual_nav2_run': self.actual, 'evidence_type': 'synthetic'}


def body(**changes):
    v = {'label': '순찰', 'map_family': family(), 'annotation_revision': '7'*64, 'visits': [{'visit_id': 'a'*32, 'label': '방문', 'pose': pose()}], 'request_id': 'request-00000001'}
    v.update(changes)
    return CreateRequest.model_validate(v)


def req(revision, key='operation-00000001'):
    return RevisionRequest(request_id=key, revision=revision)


class MissionRouteServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.maps, self.nav = MapProvider(), Navigation()
        self.maps.is_fixture = True
        self.policy = {'runtime_policy_enforced': True, 'planner_config_digest': 'b'*64, 'footprint_revision': 'c'*64, 'robot_radius_m': .25}
        self.raw_runtime = {'runtime_health': {'process_generation': 1234}}
        self.context = NavigationContext(self.nav, policy_provider=lambda: self.policy, runtime_provider=lambda: self.raw_runtime)
        self.coordinator = MissionCoordinator(self.nav, self.maps, self.root/'legacy', poll_interval_s=.05)
        self.planner = FixturePlanner()
        self.routes = SimpleNamespace(detail=lambda _: {'route': normalized()})
        self.service = MissionRoutes(self.root/'plans', self.maps, self.routes, self.coordinator, self.context, self.planner)
        self.coordinator._run_observer = self.service.observe
        def guard(mission):
            if mission.get('context_revision') != self.context.snapshot()['navigation_context_revision']:
                raise MissionConflict('CONTEXT_CHANGED')
        self.coordinator._context_guard = guard

    async def asyncTearDown(self):
        await self.coordinator.close()
        self.temp.cleanup()

    async def create(self, **changes):
        return (await self.service.write(body(**changes)))['plan']

    async def test_cas_idempotency_and_draft_revision_preserve_immutable_run(self):
        entry = await self.create()
        duplicate = await self.service.write(body())
        self.assertEqual(entry, duplicate['plan'])
        with self.assertRaises(MissionConflict):
            await self.service.write(body(label='다른 내용'))
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        update = UpdateRequest.model_validate({**body(request_id='update-0000000001').model_dump(), 'label': '변경', 'base_revision': entry['revision']})
        changed = await self.service.write(update, identifier=entry['id'])
        self.assertNotEqual(changed['plan']['revision'], entry['revision'])
        self.assertEqual(self.service.run(run['run']['id'])['run']['definition']['label'], '순찰')
        with self.assertRaises(MissionConflict):
            await self.service.write(update.model_copy(update={'request_id': 'update-0000000002'}), identifier=entry['id'])
        self.assertEqual(self.nav.sent, [])

    async def test_compile_and_run_creation_have_no_navigation_side_effect(self):
        entry = await self.create()
        compiled = await self.service.compile(entry['id'], req(entry['revision']))
        self.assertFalse(compiled['compiled']['start_sent'])
        run = await self.service.create_run(entry['id'], req(entry['revision'], 'create-run-0000001'))
        duplicate = await self.service.create_run(entry['id'], req(entry['revision'], 'create-run-0000001'))
        self.assertEqual(run['run']['id'], duplicate['run']['id'])
        self.assertEqual(self.nav.sent, [])
        self.assertEqual(self.planner.calls, [])

    async def test_preview_fixture_does_not_claim_native_and_never_sends_goal(self):
        entry = await self.create()
        result = await self.service.preview(entry['id'], PreviewRequest(request_id='preview-000000001', revision=entry['revision'], start_source='current_operational_pose'))
        self.assertFalse(result['actual_nav2_run'])
        self.assertEqual(result['evidence_type'], 'synthetic')
        self.assertGreater(result['length_m'], 0)
        self.assertIsNone(result['eta_seconds'])
        self.assertEqual(self.nav.sent, [])
        self.assertEqual(self.planner.calls[0][0], self.nav.pose)

    async def test_unknown_crossing_planned_connector_is_rejected(self):
        entry = await self.create()
        self.planner.middle = pose(4.25, 4.25)
        result = await self.service.preview(entry['id'], PreviewRequest(request_id='preview-000000001', revision=entry['revision'], start_source='current_operational_pose'))
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('PLANNED_PATH_INVALID', result['blocking_reasons'])
        self.assertEqual(self.nav.sent, [])

    async def test_custom_action_speed_tolerance_and_pass_through_block_execution(self):
        entry = await self.create(visits=[{'visit_id':'a'*32,'label':'설정','pose':pose(),'arrival_tolerance':.1,'speed':'SLOW','action':'photo','kind':'PASS_THROUGH'}])
        result = self.service.validate(entry['id'], entry['revision'])
        self.assertEqual(len(result['blocking_reasons']), 4)
        with self.assertRaises(MissionConflict):
            await self.service.create_run(entry['id'], req(entry['revision']))
        self.assertEqual(self.nav.sent, [])

    async def test_runtime_policy_missing_blocks_start_but_allows_authoring(self):
        self.policy['runtime_policy_enforced'] = False
        entry = await self.create()
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        with self.assertRaisesRegex(MissionConflict, 'RUNTIME_POLICY_NOT_ENFORCED'):
            await self.service.action(run['run']['id'], 'start', RunActionRequest(request_id='start-run-0000001'))
        self.assertEqual(self.nav.sent, [])

    async def test_context_revision_ignores_pose_sequence_but_pins_generation(self):
        before = self.context.snapshot()['navigation_context_revision']
        self.nav.pose = pose(1.6, 2.0)
        self.nav.seq += 1
        self.assertEqual(before, self.context.snapshot()['navigation_context_revision'])
        self.nav.job = 'different-source-generation'
        self.assertNotEqual(before, self.context.snapshot()['navigation_context_revision'])

    async def test_legacy_runtime_restart_changes_pin_with_unchanged_jobs(self):
        before = self.context.snapshot()
        self.assertIsNone(self.context.slam)
        self.assertEqual(before['pose_source']['generation'], 1234)
        self.raw_runtime['runtime_health']['process_generation'] = 1235
        after = self.context.snapshot()
        self.assertEqual(after['pose_source']['job_generation'], before['pose_source']['job_generation'])
        self.assertEqual(after['navigation_map'], before['navigation_map'])
        self.assertEqual(after['pose_source']['source'], before['pose_source']['source'])
        self.assertNotEqual(after['navigation_context_revision'], before['navigation_context_revision'])
        self.assertEqual(after['pose_source']['generation'], 1235)

    async def test_legacy_paused_run_cannot_resume_after_runtime_process_restart(self):
        self.planner.actual = True
        entry = await self.create()
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        identifier = run['run']['id']
        await self.service.action(identifier, 'start', RunActionRequest(request_id='legacy-start-00001'))
        await self.service.action(identifier, 'pause', RunActionRequest(request_id='legacy-pause-00001'))
        jobs = self.context.snapshot()['pose_source']['job_generation']
        self.raw_runtime['runtime_health']['process_generation'] = 1235
        self.assertEqual(self.context.snapshot()['pose_source']['job_generation'], jobs)
        with self.assertRaisesRegex(MissionConflict, 'RUN_CONTEXT_CHANGED'):
            await self.service.action(identifier, 'resume', RunActionRequest(request_id='legacy-resume-0001'))
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.coordinator.snapshot(identifier)['mission']['state'], 'paused')
        self.assertTrue(self.coordinator.blocks_navigation_goal())

    async def test_legacy_unknown_runtime_generation_blocks_start_despite_known_jobs(self):
        for unknown in (None, 0, False, '', '  ', 'unverified-generation', [], {}):
            with self.subTest(generation=unknown):
                self.raw_runtime['runtime_health']['process_generation'] = unknown
                snapshot = self.context.snapshot()
                self.assertTrue(all(snapshot['pose_source']['job_generation']))
                self.assertIsNone(snapshot['pose_source']['generation'])
                self.assertIn('SOURCE_GENERATION_UNAVAILABLE', snapshot['blocking_reasons'])
        self.raw_runtime['runtime_health']['process_generation'] = None
        entry = await self.create()
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        with self.assertRaisesRegex(MissionConflict, 'SOURCE_GENERATION_UNAVAILABLE'):
            await self.service.action(run['run']['id'], 'start', RunActionRequest(request_id='unknown-start-0001'))
        self.assertEqual(self.nav.sent, [])
        self.assertFalse(self.coordinator.blocks_navigation_goal())

    async def test_aborted_managed_run_cannot_skip_to_another_goal(self):
        self.planner.actual = True
        entry = await self.create(visits=[
            {'visit_id': 'a'*32, 'label': '첫 방문', 'pose': pose()},
            {'visit_id': 'b'*32, 'label': '다음 방문', 'pose': pose()},
        ])
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        identifier = run['run']['id']
        await self.service.action(identifier, 'start', RunActionRequest(request_id='terminal-start-001'))
        await self.service.action(identifier, 'abort', RunActionRequest(request_id='terminal-abort-001'))
        with self.assertRaisesRegex(MissionConflict, 'require a new run'):
            await self.service.action(identifier, 'skip', RunActionRequest(request_id='terminal-skip-0001'))
        mission = self.coordinator.snapshot(identifier)['mission']
        self.assertEqual(mission['outcome'], 'aborted')
        self.assertEqual(mission['current_index'], 0)
        self.assertEqual(len(self.nav.sent), 1)
        self.assertFalse(self.coordinator.blocks_navigation_goal())

    async def test_full_synthetic_start_uses_existing_owner_and_current_pose(self):
        # Fixture asserts adapter/coordinator wiring; never native/live evidence.
        self.planner.actual = True
        entry = await self.create(visits=[{'visit_id':'a'*32,'label':'작업','pose':pose(),'hold_seconds':.1,'after_arrival_confirmation':True}])
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        self.nav.pose = pose(1.75,2.0)
        result = await self.service.action(run['run']['id'], 'start', RunActionRequest(request_id='start-run-0000001'))
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.planner.calls[0][0], self.nav.pose)
        duplicate = await self.service.action(run['run']['id'], 'start', RunActionRequest(request_id='start-run-0000001'))
        self.assertEqual(duplicate["run"]["id"], result["run"]["id"])
        self.assertEqual(duplicate["mission"]["state"], result["mission"]["state"])
        self.assertEqual(len(self.nav.sent), 1)
        self.nav.goal['state'] = 'succeeded'
        for _ in range(40):
            await asyncio.sleep(.02)
            mission = self.coordinator.snapshot(run['run']['id'])['mission']
            if mission['phase'] == 'after_arrival_confirmation':
                break
        self.assertEqual(mission['completed_count'], 0)
        done = await self.service.action(run['run']['id'], 'resume', RunActionRequest(request_id='confirm-run-00001', confirmation_token=mission['confirmation_token']))
        self.assertEqual(done['mission']['state'], 'completed')
        self.assertEqual(done['run']['outcome'], 'completed')
        self.assertTrue(done['run']['logs'])
        self.assertEqual(len(self.nav.sent), 1)

    async def test_schema_injection_nonfinite_duplicate_ids_and_hypothetical_start(self):
        for patch in ({'shell':'echo unsafe'}, {'label':''}):
            with self.assertRaises(ValidationError):
                body(**patch)
        with self.assertRaises(ValidationError):
            body(visits=[{'visit_id':'a'*32,'label':'bad','pose':pose(float('nan'))}])
        v = {'visit_id':'a'*32,'label':'same','pose':pose()}
        with self.assertRaises(ValidationError):
            body(visits=[v,v])
        with self.assertRaises(ValidationError):
            PreviewRequest(request_id='preview-000000001', revision='a'*64, start_source='current_operational_pose', start=pose())

    async def test_corrupt_and_symlink_store_preserved(self):
        await self.create()
        path = self.service.store.path
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(MissionUnavailable):
            MissionRoutes(self.root/'plans', self.maps, self.routes, self.coordinator, self.context, self.planner)
        self.assertEqual(path.read_text(), '{broken')
        path.unlink()
        path.symlink_to(self.root/'legacy'/'missions.json')
        with self.assertRaises(MissionUnavailable):
            MissionRoutes(self.root/'plans', self.maps, self.routes, self.coordinator, self.context, self.planner)

    async def test_native_adapter_is_disabled_before_resource_window(self):
        with self.assertRaisesRegex(MissionUnavailable, 'RESOURCE_WINDOW'):
            await NativePlanner().plan(pose(), pose(3.,2.))

    async def test_wrong_frame_and_generation_change_preview_rejected(self):
        entry = await self.create()
        self.planner.frame = 'camera'
        with self.assertRaises(MissionConflict):
            await self.service.preview(entry['id'], PreviewRequest(request_id='preview-000000001', revision=entry['revision'], start_source='current_operational_pose'))

    async def test_source_change_blocks_existing_run_without_goal(self):
        entry = await self.create()
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        self.nav.job = 'new-generation'
        with self.assertRaisesRegex(MissionConflict,'RUN_CONTEXT_CHANGED'):
            await self.service.action(run['run']['id'], 'start', RunActionRequest(request_id='start-run-0000001'))
        self.assertEqual(self.nav.sent, [])

    async def test_failed_definition_write_does_not_publish_memory_only_draft(self):
        before = self.service.definitions()["definitions"]
        original = self.service.store.save
        self.service.store.save = lambda _: (_ for _ in ()).throw(OSError("disk full"))
        with self.assertRaises(MissionUnavailable):
            await self.create()
        self.assertEqual(self.service.definitions()["definitions"], before)
        self.service.store.save = original
        await self.create()

    async def test_full_request_ledger_never_prevents_abort(self):
        self.planner.actual = True
        entry = await self.create()
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        identifier = run['run']['id']
        await self.service.action(identifier, 'start', RunActionRequest(request_id='start-run-0000001'))
        self.service.data['requests'] = {f'full-ledger-{i:016d}': {'digest':'a'*64, 'result':{}} for i in range(256)}
        self.service._save()
        result = await self.service.action(identifier, 'abort', RunActionRequest(request_id='abort-run-0000001'))
        self.assertEqual(result['mission']['outcome'], 'aborted')
        self.assertFalse(result['mission']['ownership_active'])
        self.assertIn('audit_warning', result)
        self.assertEqual(len(self.nav.sent), 1)

    async def test_each_leg_is_planned_from_fresh_current_pose(self):
        self.planner.actual = True
        entry = await self.create(visits=[{'visit_id':'a'*32,'label':'첫 방문','pose':pose()}, {'visit_id':'b'*32,'label':'두번째','pose':pose(3.,2.)}])
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        await self.service.action(run['run']['id'], 'start', RunActionRequest(request_id='start-run-0000001'))
        self.assertEqual(len(self.planner.calls), 1)
        self.nav.pose = pose(2.1, 2.0)
        self.nav.goal['state'] = 'succeeded'
        for _ in range(50):
            await asyncio.sleep(.02)
            if len(self.nav.sent) == 2:
                break
        self.assertEqual(len(self.nav.sent), 2)
        self.assertEqual(self.planner.calls[1][0], self.nav.pose)

    async def test_planner_nonfinite_and_family_conflict_fail_closed(self):
        entry = await self.create()
        self.planner.middle = pose(float('nan'),2.)
        with self.assertRaisesRegex(MissionConflict, 'PLANNER_RESULT_INVALID'):
            await self.service.preview(entry['id'], PreviewRequest(request_id='preview-000000001', revision=entry['revision'], start_source='current_operational_pose'))
        invalid_family = {**family(), 'family_revision':'e'*64}
        entry2 = await self.create(request_id='different-create-0001', map_family=invalid_family)
        with self.assertRaisesRegex(MissionConflict, 'MAP_FAMILY'):
            self.service.validate(entry2['id'], entry2['revision'])

    async def test_ms_operational_pose_source_is_not_odometry_or_selected_engine(self):
        context = {'navigation_map':{'id':MAP_ID,'revision':MAP_REVISION}, 'operational_pose':{'source':'/amcl_pose','odometry_source':'/Odometry','generation':'native-1','readiness':{'pose_seq':1}}, 'alignment':{'verified':False}}
        slam = SimpleNamespace(navigation_context=lambda:context, blocks_context_change=lambda:False)
        adapter = NavigationContext(self.nav, slam=slam, policy_provider=lambda:self.policy)
        before = adapter.snapshot()
        self.assertEqual(before['pose_source']['source'], '/amcl_pose')
        self.assertEqual(before['pose_source']['odometry_source'], '/Odometry')
        context['operational_pose']['readiness']['pose_seq'] = 2
        self.assertEqual(before['navigation_context_revision'],adapter.snapshot()['navigation_context_revision'])
        context['operational_pose']['generation']='native-2'
        self.assertNotEqual(before['navigation_context_revision'],adapter.snapshot()['navigation_context_revision'])

    async def test_history_export_excludes_confirmation_token_and_is_not_executable(self):
        entry = await self.create()
        run = await self.service.create_run(entry['id'], req(entry['revision']))
        export = self.service.export_run(run['run']['id'])
        self.assertFalse(export['executable'])
        self.assertNotIn('confirmation_token',export['mission'])

    async def test_http_definition_compile_run_and_policy_gate_are_connected(self):
        self.app = FastAPI()
        self.app.include_router(router)
        runtime = ApplicationRuntime(competition=SimpleNamespace(require_unlocked=lambda _:None))
        runtime.mission_routes = self.service
        self.app.state.runtime = runtime
        request = MissionRouteHttpTests.request.__get__(self)
        self.assertEqual(await request('POST','/api/v1/mission-plans',body().model_dump()),201)
        entry = self.last_response['plan']
        prefix = '/api/v1/mission-plans/'+entry['id']
        self.assertEqual(await request('POST',prefix+'/compile',req(entry['revision']).model_dump()),200)
        self.assertFalse(self.last_response['compiled']['start_sent'])
        self.assertEqual(await request('POST',prefix+'/runs',req(entry['revision'],'http-run-request-0001').model_dump()),201)
        identifier = self.last_response['run']['id']
        self.policy['runtime_policy_enforced'] = False
        self.assertEqual(await request('POST','/api/v1/mission-runs/'+identifier+'/start',{'request_id':'http-start-request-001'}),409)
        self.assertEqual(self.nav.sent,[])

    async def test_annotation_heading_override_is_compiled_and_sent(self):
        self.maps.document['points']=[{'id':'f'*24,'type':'POI','label':'반복','x':2.,'y':2.,'yaw':.5}]
        self.planner.actual = True
        entry = await self.create(visits=[{'visit_id':'a'*32,'label':'첫 방문','target':'annotation_ref','annotation_id':'f'*24,'heading_yaw':1.2}])
        report = self.service.validate(entry['id'],entry['revision'])
        self.assertEqual(report['resolved_poses'][0]['yaw'],1.2)
        run = await self.service.create_run(entry['id'],req(entry['revision']))
        await self.service.action(run['run']['id'],'start',RunActionRequest(request_id='start-heading-00001'))
        self.assertEqual(self.nav.sent[0]['yaw'],1.2)

    async def test_active_definition_requires_copy_and_delete_keeps_history(self):
        self.planner.actual = True
        entry = await self.create()
        run = await self.service.create_run(entry['id'],req(entry['revision']))
        await self.service.action(run['run']['id'],'start',RunActionRequest(request_id='start-active-000001'))
        with self.assertRaisesRegex(MissionConflict,'ACTIVE_COPY'):
            await self.service.delete_definition(entry['id'],req(entry['revision'],'delete-active-00001'))
        await self.service.action(run['run']['id'],'abort',RunActionRequest(request_id='abort-active-000001'))
        await self.service.delete_definition(entry['id'],req(entry['revision'],'delete-idle-0000001'))
        self.assertEqual(self.service.definitions()['definitions'],[])
        self.assertEqual(self.service.run(run['run']['id'])['run']['definition']['label'],'순찰')

    async def test_moving_pose_is_observed_while_new_goal_admission_is_closed(self):
        self.planner.actual = True
        entry = await self.create()
        run = await self.service.create_run(entry['id'],req(entry['revision']))
        identifier = run['run']['id']
        await self.service.action(identifier,'start',RunActionRequest(request_id='observe-start-00001'))
        self.nav.goal_admission = False
        self.nav.pose = pose(1.8,2.)
        self.service._last_observation.clear()
        self.service.observe(self.coordinator.snapshot(identifier)['mission'])
        self.assertEqual(self.service.run(identifier)['run']['trajectory'][-1]['x'],1.8)
        self.service.require_run_context(self.coordinator.snapshot(identifier)['mission'])
        self.nav.pose_fresh = False
        self.assertIsNone(self.context.snapshot()['operational_pose'])
        with self.assertRaisesRegex(MissionConflict,'FRESH_OPERATIONAL_POSE_REQUIRED'):
            self.service.require_run_context(self.coordinator.snapshot(identifier)['mission'])

    async def test_native_preview_has_shared_resource_gate_without_motion_ownership(self):
        entry = await self.create()
        self.context.slam = SimpleNamespace(navigation_context=lambda:{},blocks_context_change=lambda:True)
        with self.assertRaisesRegex(MissionConflict,'SLAM_CONTEXT_BUSY'):
            await self.service.preview(entry['id'],PreviewRequest(request_id='preview-busy-00001',revision=entry['revision'],start_source='hypothetical_preview_start',start=pose()))
        self.assertEqual(self.planner.calls,[])
        self.assertFalse(self.coordinator.blocks_navigation_goal())
        self.context.slam = None
        entered = asyncio.Event()
        release = asyncio.Event()
        original = self.planner.plan
        async def delayed(start,goal):
            entered.set()
            await release.wait()
            return await original(start,goal)
        self.planner.plan = delayed
        task = asyncio.create_task(self.service.preview(entry['id'],PreviewRequest(request_id='preview-lock-00001',revision=entry['revision'],start_source='current_operational_pose')))
        await entered.wait()
        self.assertFalse(self.coordinator._coordination_lock.locked())
        self.assertTrue(self.service.blocks_context_change())
        self.assertFalse(self.coordinator.blocks_navigation_goal())
        release.set()
        await task
        self.assertFalse(self.coordinator._coordination_lock.locked())
        self.assertFalse(self.service.blocks_context_change())

    async def test_run_receipt_is_bounded_reference_and_replay_does_not_dispatch(self):
        self.planner.actual = True
        entry = await self.create()
        run = await self.service.create_run(entry['id'],req(entry['revision']))
        identifier = run['run']['id']
        request = RunActionRequest(request_id='compact-start-00001')
        await self.service.action(identifier,'start',request)
        receipt=self.service.data['requests'][request.request_id]['result']
        self.assertEqual(receipt['receipt_type'],'run_ref')
        self.assertLess(len(json.dumps(receipt)),200)
        await self.service.action(identifier,'start',request)
        self.assertEqual(len(self.nav.sent),1)


class MissionRouteHttpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.runtime = ApplicationRuntime(competition=SimpleNamespace(require_unlocked=lambda _: None))

    def tearDown(self):
        self.temp.cleanup()

    async def request(self, method, path, body=None, origin='http://testserver'):
        messages = []
        pending = [{'type':'http.request', 'body':json.dumps(body or {}).encode(), 'more_body':False}]
        async def receive():
            return pending.pop(0) if pending else {'type':'http.disconnect'}
        async def send(value):
            messages.append(value)
        await self.app({'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},'http_version':'1.1','method':method,'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','server':('testserver',80),'client':('127.0.0.1',1000),'headers':[(b'host',b'testserver'),(b'origin',origin.encode()),(b'content-type',b'application/json')]},receive,send)
        self.last_response = json.loads(b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body'))
        return next(m['status'] for m in messages if m['type']=='http.response.start')

    async def test_no_integration_is_explicit_503_and_no_arbitrary_actions(self):
        response = await self.request('GET', '/api/v1/mission-plans')
        self.assertEqual(response, 503)
        response = await self.request('POST', '/api/v1/mission-runs/'+'a'*32+'/shell', {'request_id':'valid-request-0001'})
        self.assertEqual(response, 404)

    async def test_cross_origin_and_extra_fields_rejected(self):
        response = await self.request('POST', '/api/v1/mission-plans', body().model_dump(), origin='https://evil.example')
        self.assertEqual(response, 403)
        response = await self.request('POST', '/api/v1/mission-plans', {**body().model_dump(), 'topic':'/cmd_vel'})
        self.assertEqual(response, 422)
