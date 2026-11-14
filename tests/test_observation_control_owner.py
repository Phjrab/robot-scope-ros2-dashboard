"""Fresh control copies under real native contention; synthetic signed link only."""
import asyncio
import threading
import time
import unittest

from test_observation_bridge_session import active_session
from robot_dashboard.application.ownership_readback import _control, OwnerLockBusy


class ObservationControlOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_monitor_yields_for_control_reader_and_rechecks_signed_guard(self):
        for site in ('operation', 'manager'):
            for lose_guard in (False, True):
                with self.subTest(site=site, lose_guard=lose_guard):
                    runtime, owner, service, link, _ = active_session()
                    state = await owner.start()
                    lock = link.transport.operation_lock if site == 'operation' else link.transport.manager._lock
                    entered, release = threading.Event(), threading.Event()

                    def reader():
                        with lock:
                            entered.set()
                            release.wait(2)

                    worker = threading.Thread(target=reader)
                    worker.start()
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))

                    def finish_read():
                        release.set()
                        if lose_guard:
                            link.transport.set_unready('synthetic loss while waiting')
                            link.status()

                    asyncio.get_running_loop().call_later(.025, finish_read)
                    try:
                        current = await owner.refresh()
                        self.assertEqual(current['state'], 'INVALIDATED' if lose_guard else 'READY', current)
                        self.assertEqual(current['session_id'], state['session_id'])
                        self.assertEqual(service.calls, ['start'])
                    finally:
                        release.set()
                        await asyncio.to_thread(worker.join, 1)
                    await owner.stop(state['session_id'])

    async def test_brief_contention_reads_current_owner_without_latching_unknown(self):
        for site in ('operation', 'manager'):
            for become_busy in (False, True):
                with self.subTest(site=site, become_busy=become_busy):
                    runtime, owner, service, link, _ = active_session()
                    state = await owner.start()
                    manager = link.transport.manager
                    lock = link.transport.operation_lock if site == 'operation' else manager._lock
                    entered, release = threading.Event(), threading.Event()

                    def reader():
                        with lock:
                            entered.set()
                            release.wait(2)
                            if become_busy:
                                with manager._lock:
                                    manager._lease = {'input_source': 'keyboard', 'heartbeat_at': time.monotonic()}

                    worker = threading.Thread(target=reader)
                    worker.start()
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    timer = threading.Timer(.025, release.set)
                    try:
                        # The general ownership contract remains nonblocking.
                        with self.assertRaises(OwnerLockBusy):
                            _control(runtime.agent)
                        timer.start()
                        reason = await asyncio.to_thread(owner.bridge_safety_error)
                        expected = 'CONTROL_OWNER_CHANGED_DURING_OBSERVATION' if become_busy else None
                        self.assertEqual(reason, expected)
                        current = owner.snapshot()
                        self.assertEqual(current['session_id'], state['session_id'])
                        self.assertEqual(current['state'], 'INVALIDATED' if become_busy else 'READY')
                        self.assertEqual(current['bridge_guard']['state'], 'HELD')
                        self.assertIsNone(current['owner_failure'])
                        self.assertEqual(service.calls, ['start'])
                    finally:
                        release.set()
                        timer.cancel()
                        await asyncio.to_thread(worker.join, 1)
                        with manager._lock:
                            manager._lease = None
                    await owner.stop(state['session_id'])
                    self.assertTrue(all(p['type'] == 'observation_inhibit' for p in link.sent))

    async def test_long_contention_still_latches_unknown_and_preserves_first_site(self):
        for site in ('operation', 'manager'):
            with self.subTest(site=site):
                runtime, owner, service, link, _ = active_session()
                state = await owner.start()
                lock = link.transport.operation_lock if site == 'operation' else link.transport.manager._lock
                entered, release = threading.Event(), threading.Event()

                def reader():
                    with lock:
                        entered.set()
                        release.wait(2)

                worker = threading.Thread(target=reader)
                worker.start()
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                try:
                    started = time.monotonic()
                    reason = await asyncio.to_thread(owner.bridge_safety_error)
                    self.assertLess(time.monotonic() - started, .4)
                    self.assertEqual(reason, 'CONTROL_OWNER_UNKNOWN_DURING_OBSERVATION')
                    evidence = dict(owner._owner_failure)
                    self.assertEqual(evidence['control_lock_site'], site)
                    self.assertEqual(evidence['unknown_reasons'], {'control': 'OWNER_LOCK_BUSY'})
                    self.assertEqual(owner.bridge_safety_error(), reason)
                    self.assertEqual(owner._owner_failure, evidence)
                finally:
                    release.set()
                    await asyncio.to_thread(worker.join, 1)
                self.assertEqual(owner.snapshot()['state'], 'INVALIDATED')
                self.assertEqual(owner.snapshot()['bridge_guard']['state'], 'HELD')
                await owner.stop(state['session_id'])


if __name__ == '__main__':
    unittest.main()
