"""Real signed codec, transport and bridge core in an in-memory test link."""
import time
import unittest
from types import SimpleNamespace

from robot_dashboard.control_protocol import encode_signed, decode_signed
from robot_dashboard.go2_bridge import Go2BridgeCore, BridgeCommandError


class SignedLoop:
    def __init__(self):
        # Defer the legacy test module's ROS-stub reload until discovery ends;
        # importing it at collection changes RosAgent's class identity.
        from test_ros_control_transport import ControlTransport, KEY
        self.key = KEY
        self.core = Go2BridgeCore()
        self.sent = []
        self.ack = True
        self.transport = ControlTransport({'name':'Unitree Go2','robot_type':'go2','control':{'enabled':True}},
            environ={'ROBOT_SCOPE_CONTROL_ENABLED':'1','ROBOT_SCOPE_CONTROL_BRIDGE_KEY':KEY},
            go2_target=lambda:True,ensure_target=lambda:None)
        self.transport.command_publisher = SimpleNamespace(publish=self.publish)
        self.status()

    def publish(self, message):
        payload = decode_signed(message.data,self.key)
        self.sent.append(payload)
        try:
            self.core.accept(payload,now=time.monotonic())
        except BridgeCommandError:
            self.core.force_stop('test receiver rejected command')
        if self.ack:self.status()

    def payload(self):
        return dict(self.core.snapshot(now=time.monotonic(),lowstate_age_s=.01,
                    sport_subscribers=1,sport_publishers=1),type='bridge_status',bridge_role='control')

    def status(self, payload=None):
        payload=self.payload() if payload is None else payload
        msg=SimpleNamespace(data=encode_signed(payload,self.key))
        self.transport.status_callback(msg)
        return payload


class TransportInhibitTests(unittest.TestCase):
    def test_real_signed_acquire_ack_release_and_legacy_capability_block(self):
        loop=SignedLoop();t=loop.transport
        self.assertIsNone(t.observation_inhibit_preflight())
        token=t.begin_observation_inhibit()
        self.assertEqual(t.observation_inhibit_status(token)['state'],'HELD')
        self.assertEqual(loop.core._observation_inhibit['source_id'],t.source_id)
        t.release_observation_inhibit(token)
        self.assertEqual(t.observation_inhibit_status(token)['state'],'RELEASED')
        self.assertIsNone(loop.core._observation_inhibit)
        payload=loop.payload();payload.pop('observation_inhibit');loop.status(payload)
        self.assertEqual(t.observation_inhibit_preflight(),'CONTROL_BRIDGE_INHIBIT_UNSUPPORTED')

    def test_no_implicit_flush_or_lease_expiry_in_admission(self):
        for field,value in [('_lease',{}),('_drive',{}),('_outputs',[{'type':'stop'}]),
                            ('_actions',[{}]),('_motion_active',True),('_action_guard_until',time.monotonic()+10)]:
            with self.subTest(field=field):
                loop=SignedLoop();t=loop.transport;setattr(t.manager,field,value)
                self.assertEqual(t.observation_inhibit_preflight(),'CONTROL_BRIDGE_COMMAND_BUSY')
                self.assertEqual(loop.sent,[])
                self.assertIs(getattr(t.manager,field),value)

    def test_local_motion_outputs_blocked_but_stop_delivered(self):
        loop=SignedLoop();t=loop.transport;token=t.begin_observation_inhibit()
        t.publish_outputs([{'type':'drive','velocity':{'vx':.1,'vy':0,'wz':0}},
                           {'type':'action','action':'stand_up'},{'type':'stop','reason':'estop'}])
        self.assertEqual([p['type'] for p in loop.sent],['observation_inhibit','stop'])
        self.assertEqual(t.observation_inhibit_status(token)['state'],'INVALID')
        loop.status()
        self.assertEqual(t.observation_inhibit_status(token)['state'],'INVALID')

    def test_replayed_status_and_epoch_change_are_latched(self):
        for change in ['replay','epoch']:
            loop=SignedLoop();t=loop.transport;token=t.begin_observation_inhibit()
            payload=loop.status()
            if change=='replay':loop.status(payload)
            else:loop.core=Go2BridgeCore();loop.status()
            self.assertEqual(t.observation_inhibit_status(token)['state'],'INVALID')
            loop.status()
            self.assertEqual(t.observation_inhibit_status(token)['state'],'INVALID')

    def test_stale_receipt_and_unready_cannot_revive_a_hold(self):
        for change in ['stale','unready']:
            loop=SignedLoop();t=loop.transport;token=t.begin_observation_inhibit()
            if change=='stale':t.status_received-=2
            else:t.set_unready('synthetic transport loss')
            self.assertEqual(t.observation_inhibit_status(token)['state'],'INVALID')
            loop.status()
            self.assertEqual(t.observation_inhibit_status(token)['state'],'INVALID')

    def test_missing_acquire_or_release_ack_never_claims_completion(self):
        loop=SignedLoop();t=loop.transport;loop.ack=False
        token=t.begin_observation_inhibit()
        self.assertEqual(t.observation_inhibit_status(token)['state'],'WAITING')
        loop.status()
        self.assertEqual(t.observation_inhibit_status(token)['state'],'HELD')
        t.release_observation_inhibit(token)
        self.assertEqual(t.observation_inhibit_status(token)['state'],'RELEASING')
        count=len(loop.sent);t.release_observation_inhibit(token)
        self.assertEqual(len(loop.sent),count)
        loop.status()
        self.assertEqual(t.observation_inhibit_status(token)['state'],'RELEASED')

    def test_bridge_violation_seen_even_when_local_owner_returns_idle(self):
        loop=SignedLoop();t=loop.transport;token=t.begin_observation_inhibit()
        try:
            loop.core.accept(dict(type='drive',source_id=t.source_id,seq=100,
                bridge_epoch=loop.core.bridge_epoch,deadman=True,linear_x=.2,linear_y=0,angular_z=0),
                now=time.monotonic())
        except BridgeCommandError:pass
        loop.status()
        self.assertEqual(t.observation_inhibit_status(token)['reason'],'CONTROL_BRIDGE_INHIBIT_VIOLATED')

    def test_release_requires_ack_for_exact_release_command_not_any_off_status(self):
        loop=SignedLoop();t=loop.transport;token=t.begin_observation_inhibit()
        loop.ack=False;t.release_observation_inhibit(token)
        payload=loop.payload();payload['observation_inhibit']['release_ack']=None
        loop.status(payload)
        self.assertEqual(t.observation_inhibit_status(token)['state'],'RELEASING')
        loop.status()
        self.assertEqual(t.observation_inhibit_status(token)['state'],'RELEASED')


if __name__ == '__main__':unittest.main()
