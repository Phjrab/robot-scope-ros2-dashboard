"""Synthetic execution regressions; never connects to ROS or a device."""
import asyncio
import json
import test_mission_coordinator as legacy

from test_mission_coordinator import waypoint, FIRST, SECOND, wait_for
from robot_dashboard.application.mission_coordinator import MissionConflict, MissionCoordinator, MissionValidationError


class MissionRouteExecutionTests(legacy.MissionCoordinatorTests):
    async def test_final_hold_is_not_skipped_and_uses_monotonic_time(self):
        clock = [10.0]
        self.coordinator._monotonic = lambda: clock[0]
        m = await self.create([waypoint(FIRST, hold=5.0)])
        await self.coordinator.start(m['id'])
        self.navigation.goal['state'] = 'succeeded'
        await wait_for(lambda: self.coordinator.snapshot(m['id'])['mission']['phase'] == 'holding')
        self.coordinator._now = lambda: 9_000_000_000.0
        await asyncio.sleep(.08)
        s = self.coordinator.snapshot(m['id'])['mission']
        self.assertEqual(s['state'], 'running')
        self.assertEqual(s['completed_count'], 0)
        self.assertEqual(s['hold_remaining'], 5.0)
        clock[0] = 15.1
        await wait_for(lambda: self.coordinator.snapshot(m['id'])['mission']['state'] == 'completed')

    async def test_pause_freezes_final_hold_and_resume_does_not_redrive(self):
        clock = [10.0]
        self.coordinator._monotonic = lambda: clock[0]
        m = await self.create([waypoint(FIRST, hold=5.0)])
        await self.coordinator.start(m['id'])
        self.navigation.goal['state'] = 'succeeded'
        await wait_for(lambda: self.coordinator.snapshot(m['id'])['mission']['phase'] == 'holding')
        clock[0] = 12.0
        paused = await self.coordinator.pause(m['id'])
        self.assertEqual(paused['mission']['hold_remaining'], 3.0)
        clock[0] = 100.0
        await self.coordinator.resume(m['id'])
        self.assertEqual(self.navigation.sent, [FIRST])
        self.assertEqual(self.coordinator.snapshot(m['id'])['mission']['hold_remaining'], 3.0)
        clock[0] = 103.1
        await wait_for(lambda: self.coordinator.snapshot(m['id'])['mission']['state'] == 'completed')

    async def test_first_pre_confirmation_is_honoured(self):
        m = await self.create([waypoint(FIRST, confirmation=True)])
        result = await self.coordinator.start(m['id'])
        self.assertEqual(result['mission']['phase'], 'before_departure_confirmation')
        self.assertEqual(self.navigation.sent, [])
        await self.coordinator.resume(m['id'])
        self.assertEqual(self.navigation.sent, [FIRST])

    async def test_after_confirmation_is_bound_to_current_run_visit_token(self):
        m = await self.create([{**waypoint(FIRST), 'after_arrival_confirmation': True}, waypoint(SECOND)])
        await self.coordinator.start(m['id'])
        self.navigation.goal['state'] = 'succeeded'
        await wait_for(lambda: self.coordinator.snapshot(m['id'])['mission']['phase'] == 'after_arrival_confirmation')
        s = self.coordinator.snapshot(m['id'])['mission']
        self.assertEqual(s['completed_count'], 0)
        self.assertEqual(self.navigation.sent, [FIRST])
        with self.assertRaises(MissionConflict):
            await self.coordinator.resume(m['id'], confirmation_token='f'*32)
        await self.coordinator.resume(m['id'], confirmation_token=s['confirmation_token'])
        self.assertEqual(self.navigation.sent, [FIRST, SECOND])
        with self.assertRaises(MissionConflict):
            await self.coordinator.resume(m['id'], confirmation_token=s['confirmation_token'])

    async def test_other_goal_terminal_success_never_advances_current_visit(self):
        m = await self.create()
        await self.coordinator.start(m['id'])
        self.navigation.goal = {'state': 'succeeded', 'goal_id': 'f'*32}
        await wait_for(lambda: self.coordinator.snapshot(m['id'])['mission']['state'] == 'canceling')
        s = self.coordinator.snapshot(m['id'])['mission']
        self.assertEqual(s['completed_count'], 0)
        self.assertTrue(s['ownership_active'])
        self.assertEqual(self.navigation.sent, [FIRST])
        with self.assertRaises(MissionConflict):
            await self.coordinator.abort(m['id'])

    async def test_unimplemented_tolerance_rejected_before_goal_and_ownership(self):
        m = await self.create([{**waypoint(FIRST), 'arrival_tolerance': .15}])
        with self.assertRaisesRegex(MissionConflict, 'ARRIVAL_TOLERANCE_UNSUPPORTED'):
            await self.coordinator.start(m['id'])
        self.assertFalse(self.coordinator.blocks_navigation_goal())
        self.assertEqual(self.navigation.sent, [])

    async def test_repeated_poi_has_distinct_persistent_visit_ids(self):
        m = await self.create([waypoint(FIRST), waypoint(FIRST)])
        ids = [w['visit_id'] for w in m['waypoints']]
        self.assertNotEqual(*ids)
        restored = MissionCoordinator(self.navigation, self.saved_maps, self.root)
        self.assertEqual(ids, [w['visit_id'] for w in restored.snapshot(m['id'])['mission']['waypoints']])
        await restored.close()

    async def test_paused_restart_is_interrupted_and_not_resumable(self):
        m = await self.create()
        await self.coordinator.start(m['id'])
        await self.coordinator.pause(m['id'])
        restored = MissionCoordinator(self.navigation, self.saved_maps, self.root)
        s = restored.snapshot(m['id'])['mission']
        self.assertEqual(s['outcome'], 'interrupted')
        self.assertFalse(s['ownership_active'])
        with self.assertRaises(MissionConflict):
            await restored.resume(m['id'])
        with self.assertRaises(MissionConflict):
            await restored.retry(m['id'])
        with self.assertRaises(MissionConflict):
            await restored.skip(m['id'])
        unchanged = restored.snapshot(m['id'])['mission']
        self.assertEqual(unchanged['outcome'], 'interrupted')
        self.assertEqual(unchanged['current_index'], 0)
        self.assertFalse(unchanged['ownership_active'])
        self.assertEqual(self.navigation.sent, [FIRST])
        await restored.close()

    async def test_aborted_run_cannot_skip_to_next_visit(self):
        mission = await self.create()
        await self.coordinator.start(mission['id'])
        await self.coordinator.abort(mission['id'])
        with self.assertRaisesRegex(MissionConflict, 'require a new run'):
            await self.coordinator.skip(mission['id'])
        unchanged = self.coordinator.snapshot(mission['id'])['mission']
        self.assertEqual(unchanged['outcome'], 'aborted')
        self.assertEqual(unchanged['current_index'], 0)
        self.assertFalse(unchanged['ownership_active'])
        self.assertFalse(self.coordinator.blocks_navigation_goal())
        self.assertEqual(self.navigation.sent, [FIRST])

    async def test_non_mapping_stored_waypoint_disables_owner_and_preserves_bytes(self):
        await self.create()
        state_file = self.root / 'missions.json'
        original = state_file.read_text(encoding='utf-8')
        for invalid in (None, 7, [], 'waypoint'):
            with self.subTest(waypoint=invalid):
                document = json.loads(original)
                document['missions'][0]['waypoints'][0] = invalid
                corrupted = json.dumps(document, ensure_ascii=False).encode('utf-8')
                state_file.write_bytes(corrupted)
                restored = MissionCoordinator(self.navigation, self.saved_maps, self.root)
                self.assertFalse(restored.snapshot()['available'])
                self.assertEqual(restored.snapshot()['missions'], [])
                self.assertFalse(restored.blocks_navigation_goal())
                await restored.close()
                self.assertEqual(state_file.read_bytes(), corrupted)
        self.assertEqual(self.navigation.sent, [])

    async def test_cancel_timeout_retains_owner_and_blocks_new_run(self):
        async def no_cancel(**kwargs):
            return {'navigation': self.navigation.view()}
        self.navigation.cancel_goal = no_cancel
        m = await self.create()
        await self.coordinator.start(m['id'])
        with self.assertRaises(MissionConflict):
            await self.coordinator.pause(m['id'])
        self.assertEqual(self.coordinator.snapshot(m['id'])['mission']['state'], 'pausing')
        self.assertTrue(self.coordinator.blocks_navigation_goal())
        self.navigation.goal['state'] = 'canceled'

    async def test_skipped_required_visit_is_not_clean_completion(self):
        m = await self.create([waypoint(FIRST)])
        await self.coordinator.start(m['id'])
        r = await self.coordinator.skip(m['id'])
        self.assertEqual(r['mission']['outcome'], 'completed_with_skips')
        self.assertEqual(r['mission']['completed_count'], 0)

    async def managed_mission(self, *, preflight=None):
        admission = object()
        self.coordinator._managed_admission = admission
        async def accepted(_mission):
            return None
        self.coordinator._dispatch_preflight = preflight or accepted
        response = await self.coordinator.create(
            label='Managed mission', map_id=legacy.MAP_ID,
            map_revision=legacy.MAP_REVISION,
            annotation_revision=legacy.ANNOTATION_REVISION,
            waypoints=[waypoint(FIRST)], context_revision='f'*64,
        )
        return response['mission'], admission

    async def test_managed_run_rejects_legacy_start_resume_retry_skip(self):
        mission, admission = await self.managed_mission()
        for action in ('start', 'resume', 'retry', 'skip'):
            with self.subTest(action=action):
                with self.assertRaisesRegex(MissionConflict, 'MISSION_ROUTE_API_REQUIRED'):
                    await getattr(self.coordinator, action)(mission['id'])
        self.assertEqual(self.navigation.sent, [])
        self.assertFalse(self.coordinator.blocks_navigation_goal())
        await self.coordinator.start(mission['id'], admission=admission)
        await self.coordinator.pause(mission['id'])
        with self.assertRaisesRegex(MissionConflict, 'MISSION_ROUTE_API_REQUIRED'):
            await self.coordinator.resume(mission['id'], admission=object())
        self.assertEqual(self.navigation.sent, [FIRST])

    async def test_abort_ready_run_preserves_other_active_run_and_monitor(self):
        active = await self.create()
        draft = await self.create([waypoint(SECOND)])
        await self.coordinator.start(active['id'])
        task = self.coordinator._task
        generation = self.coordinator._generation
        result = await self.coordinator.abort(draft['id'])
        self.assertEqual(result['mission']['outcome'], 'aborted')
        self.assertIs(self.coordinator._task, task)
        self.assertEqual(self.coordinator._generation, generation)
        self.assertEqual(self.coordinator.snapshot()['active_mission_id'], active['id'])
        self.assertEqual(self.navigation.canceled, [])
        self.navigation.goal['state'] = 'succeeded'
        await wait_for(lambda: self.navigation.sent == [FIRST, SECOND])

    async def test_stop_during_native_preflight_never_submits_goal(self):
        for action in ('pause', 'abort'):
            with self.subTest(action=action):
                entered, release = asyncio.Event(), asyncio.Event()
                async def preflight(_mission):
                    entered.set()
                    await release.wait()
                mission, admission = await self.managed_mission(preflight=preflight)
                start = asyncio.create_task(self.coordinator.start(mission['id'], admission=admission))
                await asyncio.wait_for(entered.wait(), 1)
                self.assertTrue(self.coordinator.blocks_navigation_goal())
                stop = asyncio.create_task(getattr(self.coordinator, action)(mission['id']))
                await asyncio.sleep(0)
                release.set()
                _, result = await asyncio.gather(start, stop)
                self.assertEqual(self.navigation.sent, [])
                self.assertEqual(result['mission']['state'], 'paused' if action == 'pause' else 'failed')
                self.assertEqual(result['mission']['ownership_active'], action == 'pause')
                await self.coordinator.abort(mission['id'])

    async def test_uncertain_send_never_adopts_or_cancels_foreign_goal(self):
        mission = await self.create([waypoint(FIRST)])
        async def uncertain(**_kwargs):
            self.navigation.goal = {'state': 'active', 'goal_id': 'f'*32}
            raise RuntimeError('transport failed without accepted response')
        self.navigation.send_annotation_goal = uncertain
        with self.assertRaises(MissionConflict):
            await self.coordinator.start(mission['id'])
        current = self.coordinator.snapshot(mission['id'])['mission']
        self.assertEqual(current['phase'], 'uncertain')
        self.assertIsNone(current['current_waypoint']['goal_id'])
        self.assertTrue(current['ownership_active'])
        with self.assertRaises(MissionConflict):
            await self.coordinator.abort(mission['id'])
        self.assertEqual(self.navigation.canceled, [])
        self.assertTrue(self.coordinator.blocks_navigation_goal())

    async def test_canceled_submission_retains_uncertain_owner_through_close(self):
        mission = await self.create([waypoint(FIRST)])
        entered = asyncio.Event()
        async def pending(**_kwargs):
            self.navigation.goal = {'state': 'active', 'goal_id': 'f'*32}
            entered.set()
            await asyncio.Event().wait()
        self.navigation.send_annotation_goal = pending
        starting = asyncio.create_task(self.coordinator.start(mission['id']))
        await asyncio.wait_for(entered.wait(), 1)
        starting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await starting
        current = self.coordinator.snapshot(mission['id'])['mission']
        self.assertEqual(current['phase'], 'uncertain')
        self.assertTrue(current['ownership_active'])
        self.assertIsNone(current['current_waypoint']['goal_id'])
        await self.coordinator.close()
        self.assertTrue(self.coordinator.blocks_navigation_goal())
        self.assertEqual(self.navigation.canceled, [])

    async def test_cancel_during_preflight_has_no_unknown_goal_and_can_abort(self):
        entered = asyncio.Event()
        async def preflight(_mission):
            entered.set()
            await asyncio.Event().wait()
        mission, admission = await self.managed_mission(preflight=preflight)
        starting = asyncio.create_task(self.coordinator.start(mission['id'], admission=admission))
        await asyncio.wait_for(entered.wait(), 1)
        starting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await starting
        result = await self.coordinator.abort(mission['id'])
        self.assertEqual(result['mission']['outcome'], 'aborted')
        self.assertFalse(self.coordinator.blocks_navigation_goal())
        self.assertEqual(self.navigation.sent, [])
        self.assertEqual(self.navigation.canceled, [])

    async def test_persistence_failure_never_prevents_pause_and_abort(self):
        for action in ('pause', 'abort'):
            with self.subTest(action=action):
                mission = await self.create([waypoint(FIRST)])
                await self.coordinator.start(mission['id'])
                goal_id = self.navigation.goal['goal_id']
                save = self.coordinator._store.save
                def unavailable(_document):
                    raise OSError('disk is full')
                self.coordinator._store.save = unavailable
                try:
                    result = await getattr(self.coordinator, action)(mission['id'])
                    self.assertEqual(self.navigation.canceled[-1], goal_id)
                    self.assertEqual(result['mission']['state'], 'paused' if action == 'pause' else 'failed')
                    self.assertEqual(result['audit_warning'], 'STOP_APPLIED_WITHOUT_DURABLE_HISTORY')
                finally:
                    self.coordinator._store.save = save
                    await self.coordinator.abort(mission['id'])

    async def test_monitor_audit_failure_cancels_owned_goal_without_store(self):
        mission = await self.create([waypoint(FIRST)])
        await self.coordinator.start(mission['id'])
        goal_id = self.navigation.goal['goal_id']
        def unavailable(_mission):
            raise OSError('audit store unavailable')
        self.coordinator._run_observer = unavailable
        await wait_for(lambda: self.coordinator.snapshot(mission['id'])['mission']['state'] == 'failed')
        current = self.coordinator.snapshot(mission['id'])['mission']
        self.assertEqual(self.navigation.canceled, [goal_id])
        self.assertEqual(current['outcome'], 'monitor_failed')
        self.assertFalse(current['ownership_active'])
        self.assertEqual(current['audit_warning'], 'STOP_APPLIED_WITHOUT_DURABLE_HISTORY')

    async def test_monitor_audit_failure_retains_owner_if_cancel_unconfirmed(self):
        mission = await self.create([waypoint(FIRST)])
        await self.coordinator.start(mission['id'])
        def unavailable(_mission):
            raise OSError('audit store unavailable')
        async def pending_cancel(**_kwargs):
            return {'navigation': self.navigation.view()}
        self.coordinator._run_observer = unavailable
        self.navigation.cancel_goal = pending_cancel
        await wait_for(lambda: self.coordinator.snapshot(mission['id'])['mission']['phase'] == 'uncertain')
        self.assertTrue(self.coordinator.blocks_navigation_goal())
        self.assertEqual(self.navigation.sent, [FIRST])
        self.navigation.goal['state'] = 'canceled'

    async def test_post_acceptance_save_failure_cancels_only_accepted_goal(self):
        mission = await self.create([waypoint(FIRST)])
        send = self.navigation.send_annotation_goal
        save = self.coordinator._store.save
        def unavailable(_document):
            raise OSError('disk is full')
        async def accepted(**kwargs):
            response = await send(**kwargs)
            self.coordinator._store.save = unavailable
            return response
        self.navigation.send_annotation_goal = accepted
        try:
            with self.assertRaises(MissionConflict):
                await self.coordinator.start(mission['id'])
            self.assertEqual(self.navigation.canceled, ['1'.zfill(32)])
            self.assertFalse(self.coordinator.blocks_navigation_goal())
        finally:
            self.coordinator._store.save = save

    async def test_annotation_heading_override_is_persisted_and_sent_to_navigation(self):
        annotations = self.saved_maps.annotations
        def located(map_id):
            document = annotations(map_id)
            document['points'][0].update(x=1.25, y=2.5, yaw=0.1)
            return document
        self.saved_maps.annotations = located
        dispatched = []
        async def send_goal(**kwargs):
            dispatched.append(kwargs)
            self.navigation.goal = {'state': 'active', 'goal_id': '1'.zfill(32)}
            return {'navigation': self.navigation.view()}
        self.navigation.send_goal = send_goal
        mission = await self.create([{**waypoint(FIRST), 'heading_yaw': 1.75}])
        restored = MissionCoordinator(self.navigation, self.saved_maps, self.root)
        self.assertEqual(restored.snapshot(mission['id'])['mission']['waypoints'][0]['heading_yaw'], 1.75)
        await restored.close()
        await self.coordinator.start(mission['id'])
        self.assertEqual(len(dispatched), 1)
        self.assertEqual((dispatched[0]['x'], dispatched[0]['y'], dispatched[0]['yaw']), (1.25, 2.5, 1.75))
        self.assertEqual(self.navigation.sent, [])

    async def test_annotation_heading_override_rejects_invalid_or_local_pose_target(self):
        for invalid in (True, float('nan'), float('inf'), 3.2, '1.0'):
            with self.subTest(heading=invalid):
                with self.assertRaises(MissionValidationError):
                    await self.create([{**waypoint(FIRST), 'heading_yaw': invalid}])
        with self.assertRaises(MissionValidationError):
            await self.create([{'mission_local_pose': {'x': 1., 'y': 2., 'yaw': 0.}, 'heading_yaw': 1.0}])
