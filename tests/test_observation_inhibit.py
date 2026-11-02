"""Synthetic protocol checks; no ROS entities, hardware or physical-stop claim."""
import unittest
from robot_dashboard.go2_bridge import Go2BridgeCore, BridgeCommandError, API_STOP_MOVE


class InhibitCoreTests(unittest.TestCase):
    def setUp(self):
        self.core = Go2BridgeCore()
        self.seq = 0
        self.now = 10.
        self.token = 'a' * 32

    def send(self, kind, **values):
        self.seq += 1
        self.core.accept(dict(type=kind, source_id='dashboard-a', seq=self.seq,
                             bridge_epoch=self.core.bridge_epoch, **values), now=self.now)

    def status(self, **values):
        return self.core.snapshot(now=self.now, lowstate_age_s=.01,
                                  sport_subscribers=1, sport_publishers=1, **values)

    def hold(self):
        self.send('observation_inhibit', token=self.token, enabled=True)

    def test_hold_proof_and_exact_release(self):
        self.hold()
        proof = self.status()['observation_inhibit']
        self.assertEqual(proof['token'], self.token)
        self.assertEqual(proof['source_id'], 'dashboard-a')
        self.assertFalse(proof['violated'])
        self.assertGreater(self.status()['observation_inhibit']['sequence'], proof['sequence'])
        self.send('observation_inhibit', token=self.token, enabled=False)
        self.assertIsNone(self.status()['observation_inhibit']['token'])

    def test_rejects_drive_and_action_and_latches_even_after_stop(self):
        self.hold()
        for kind, values in [('drive',dict(deadman=True,linear_x=.1,linear_y=0.,angular_z=0.)),
                             ('action',dict(action_id='stand_up'))]:
            with self.assertRaisesRegex(BridgeCommandError, 'observation'):
                self.send(kind, **values)
        self.send('stop')
        self.assertTrue(self.status()['observation_inhibit']['violated'])
        requests = self.core.tick(now=12.,lowstate_age_s=.01,sport_subscribers=1,sport_publishers=1)
        self.assertTrue(all(r.api_id == API_STOP_MOVE for r in requests))

    def test_does_not_erase_preexisting_drive_or_pending_action_to_acquire(self):
        for kind,values in [('drive',dict(deadman=True,linear_x=.1,linear_y=0.,angular_z=0.)),
                            ('action',dict(action_id='stand_up'))]:
            self.setUp();self.send(kind,**values)
            before=(self.core._target,self.core._pending_action)
            with self.assertRaisesRegex(BridgeCommandError,'busy'):
                self.hold()
            self.assertEqual((self.core._target,self.core._pending_action),before)

    def test_wrong_token_or_source_cannot_release_and_hold_has_no_timeout(self):
        self.hold();self.now=100.
        with self.assertRaises(BridgeCommandError):
            self.send('observation_inhibit',token='b'*32,enabled=False)
        self.assertEqual(self.status()['observation_inhibit']['token'],self.token)
        with self.assertRaises(BridgeCommandError):
            self.core.accept(dict(type='observation_inhibit',source_id='dashboard-b',seq=50,
                bridge_epoch=self.core.bridge_epoch,token=self.token,enabled=False),now=100.)
        self.assertEqual(self.status()['observation_inhibit']['token'],self.token)

    def test_transient_graph_loss_stays_invalid_after_recovery(self):
        self.hold()
        self.core.tick(now=10.1,lowstate_age_s=.01,sport_subscribers=0,sport_publishers=1)
        self.core.tick(now=10.2,lowstate_age_s=.01,sport_subscribers=1,sport_publishers=1)
        self.assertTrue(self.status()['observation_inhibit']['violated'])

    def test_stop_always_passes_and_cannot_release_inhibit(self):
        self.hold();self.send('stop',reason='estop')
        self.assertEqual(self.status()['observation_inhibit']['token'],self.token)
        requests=self.core.tick(now=10.1,lowstate_age_s=.01,sport_subscribers=1,sport_publishers=1)
        self.assertIn(API_STOP_MOVE,[r.api_id for r in requests])


if __name__ == '__main__': unittest.main()
