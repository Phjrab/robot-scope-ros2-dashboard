"""Bounded synthetic lifecycle integration; signed link, real thread executor."""
import asyncio
import time
import unittest
from types import SimpleNamespace

from test_fastlio_observation import session_runtime
from test_observation_bridge_transport import SignedLoop
from robot_dashboard.application.lifecycle_coordinator import LifecycleCoordinator, LifecycleTransitionBusy
from robot_dashboard.application.navigation_preparation_inputs import observation_start_blockers
from robot_dashboard.application.fastlio_observation import ObservationSessionConflict


def active_session():
    runtime, owner, service = session_runtime()
    # A systemd invocation has one fixed activation timestamp, unlike the
    # general legacy fake's fresh now-minus-five value on every status call.
    read_status=service.status
    started=time.monotonic()-5
    def status():
        result=read_status()
        result['started_monotonic_s']=started if result['active'] else 0.
        return result
    service.status=status
    loop=SignedLoop();runtime.agent._control_transport=loop.transport
    systemd=dict(available=True,active_state='active',sub_state='running',invocation_id='c'*32)
    runtime.lifecycle.control_bridge_snapshot=lambda: {'systemd':dict(systemd)}
    bridge=runtime.lifecycle._control_bridge_lifecycle
    bridge._read_systemd=lambda:dict(systemd)
    bridge.is_busy=lambda:False
    runtime.lifecycle.control_bridge_lifecycle=bridge
    runtime.lifecycle.service_lifecycle=SimpleNamespace(is_busy=lambda:False)
    runtime.lifecycle._observation_active=owner.busy
    runtime.lifecycle.require_idle=lambda:LifecycleCoordinator.require_idle(runtime.lifecycle)
    return runtime,owner,service,loop,systemd


class ActiveBridgeSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_signed_bridge_allows_start_and_exact_stop_releases(self):
        runtime,owner,service,loop,_=active_session()
        await owner.refresh()
        self.assertEqual(observation_start_blockers(runtime)['items'],[])
        state=await owner.start()
        self.assertEqual(state['state'],'READY',state)
        self.assertEqual(state['bridge_guard']['state'],'HELD')
        self.assertFalse(state['map_registration_applied'])
        self.assertEqual(observation_start_blockers(runtime)['items'],['OBSERVATION_SESSION_NOT_STARTABLE'])
        owner.reserve_handoff_receipt('h',state['session_id'],state['started_monotonic_s'])
        stopped=await owner.stop(state['session_id'])
        self.assertEqual(stopped['state'],'STOPPED')
        self.assertFalse(owner.busy())
        self.assertEqual(owner.handoff_receipt('h')['state'],'INACTIVE_CONFIRMED')
        self.assertIsNone(loop.core._observation_inhibit)
        self.assertEqual(service.calls,['start','stop'])
        self.assertEqual([p['type'] for p in loop.sent],['observation_inhibit','observation_inhibit'])

    async def test_arm_and_observation_serialized_both_orders(self):
        for first in ('arm','observation'):
            with self.subTest(first=first):
                runtime,owner,service,loop,_=active_session();await owner.refresh()
                async def arm():
                    async with runtime.pipeline_coordination_lock:
                        runtime.lifecycle.require_idle()
                        return loop.transport.manager.acquire_lease('keyboard')
                if first=='arm':
                    await arm()
                    with self.assertRaises(ObservationSessionConflict):await owner.start()
                    self.assertEqual(service.calls,[])
                else:
                    entered=asyncio.create_task(owner.start())
                    await asyncio.sleep(0)
                    armed=asyncio.create_task(arm())
                    state=await entered
                    with self.assertRaises(LifecycleTransitionBusy):await armed
                    self.assertEqual(state['state'],'READY')
                    self.assertIsNone(loop.transport.manager._lease)
                    await owner.stop(state['session_id'])

    async def test_loss_latches_and_preserves_stop_but_invalidates_handoff(self):
        runtime,owner,service,loop,_=active_session();state=await owner.start()
        owner.reserve_handoff_receipt('h',state['session_id'],state['started_monotonic_s'])
        loop.transport.set_unready('synthetic link loss');loop.status()
        self.assertEqual(owner.snapshot()['state'],'INVALIDATED')
        await owner.refresh()
        self.assertEqual(owner.snapshot()['state'],'INVALIDATED')
        self.assertTrue(owner.snapshot()['can_stop'])
        await owner.stop(state['session_id'])
        self.assertEqual(service.calls,['start','stop'])
        self.assertEqual(owner.handoff_receipt('h')['state'],'OUTCOME_UNKNOWN')

    async def test_service_invocation_change_and_owner_unknown_fail_closed(self):
        for change in ('invocation','owner'):
            runtime,owner,service,loop,systemd=active_session();state=await owner.start()
            if change=='invocation':systemd['invocation_id']='d'*32
            else:runtime.navigation._state_lock=None
            await owner.refresh()
            self.assertEqual(owner.snapshot()['state'],'INVALIDATED')
            self.assertTrue(owner.snapshot()['can_stop'])
            await owner.stop(state['session_id'])

    async def test_accepted_start_unknown_retains_inhibit_and_blocks_new_work(self):
        runtime,owner,service,loop,_=active_session()
        dispatch=service.dispatch
        def uncertain(action):
            dispatch(action)
            if action=='start':service.failure=True
        service.dispatch=uncertain
        state=await owner.start()
        self.assertEqual(state['state'],'UNKNOWN')
        self.assertTrue(owner.busy())
        self.assertIsNotNone(loop.core._observation_inhibit)
        with self.assertRaises(LifecycleTransitionBusy):runtime.lifecycle.require_idle()
        service.failure=False
        await owner.refresh()
        await owner.stop(owner.snapshot()['session_id'])

    async def test_stop_unknown_does_not_release_or_claim_stop_receipt(self):
        runtime,owner,service,loop,_=active_session();state=await owner.start()
        owner.reserve_handoff_receipt('h',state['session_id'],state['started_monotonic_s'])
        service.dispatch=lambda action:(service.calls.append(action),setattr(service,'failure',True))
        result=await owner.stop(state['session_id'])
        self.assertEqual(result['state'],'UNKNOWN')
        self.assertTrue(owner.busy())
        self.assertIsNotNone(loop.core._observation_inhibit)
        self.assertEqual(owner.handoff_receipt('h')['state'],'OUTCOME_UNKNOWN')

    async def test_missing_release_ack_retains_lifecycle_blocker(self):
        runtime,owner,service,loop,_=active_session();state=await owner.start()
        loop.ack=False
        result=await owner.stop(state['session_id'])
        self.assertEqual(result['state'],'STOPPED')
        self.assertTrue(owner.busy())
        self.assertFalse(result['can_start'])
        with self.assertRaises(LifecycleTransitionBusy):runtime.lifecycle.require_idle()
        loop.status();await owner.refresh()
        self.assertFalse(owner.busy())


if __name__ == '__main__':unittest.main()
