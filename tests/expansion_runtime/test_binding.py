import unittest
from dataclasses import replace
from robot_dashboard.expansion_runtime.binding import (ClockMapping, RuntimeContext, D3_PROFILE, C1_PROFILE, browser_safe)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.ctx = RuntimeContext(1,'a'*24,'b'*64,0,'family','r1','f1','c'*64,'goal',1,'lease','scope','epoch','odom','tf','clock-epoch','host')
        self.map = ClockMapping('sensor','epoch','clock-epoch','host',100,5,0,10**20,'calibration-evidence')

    def test_offset_uncertainty_no_reception_ttl(self):
        interval = self.map.interval(dict(clock_domain='sensor',from_ns='1000',until_ns='2000'),profile=D3_PROFILE,context=self.ctx)
        self.assertEqual(interval,dict(host_clock_id='host',start_monotonic_ns=1105,end_monotonic_ns=2095))
        self.assertEqual(self.map.interval(interval,profile=C1_PROFILE,context=self.ctx),interval)

    def test_unknown_version_domain_epoch_and_legacy_rejected(self):
        for value, profile, ctx in [
            ({'clock_id':'host','valid_from_ns':1,'valid_until_ns':2}, D3_PROFILE,self.ctx),
            ({'clock_domain':'other','from_ns':'1','until_ns':'20'},D3_PROFILE,self.ctx),
            ({'clock_domain':'sensor','from_ns':'1','until_ns':'20'},D3_PROFILE,replace(self.ctx,clock_epoch='restart')),
            ({},'0.1',self.ctx),
        ]:
            with self.assertRaises(ValueError): self.map.interval(value,profile=profile,context=ctx)

    def test_browser_integer_precision_no_silent_rounding(self):
        browser_safe({'stamp_ns':str(2**63),'received_monotonic_ns':2**53-1})
        with self.assertRaisesRegex(ValueError,'UNSAFE_JS_INTEGER'): browser_safe({'end_monotonic_ns':2**53})
        large=2**63
        mapping=replace(self.map,offset_ns=-large+10000,uncertainty_ns=0)
        value=mapping.interval(dict(clock_domain='sensor',from_ns=str(large),until_ns=str(large+1)),profile=D3_PROFILE,context=self.ctx)
        self.assertEqual(value['end_monotonic_ns'],10001)

    def test_family_footprint_goal_authority_tf_epoch_changes_key(self):
        for key,value in dict(family_revision='r2',footprint_revision='f2',controller_goal_id='goal2',authority_generation=2,
                              map_generation=1,tf_epoch='tf2',clock_epoch='clock2',command_scope='new').items():
            self.assertNotEqual(self.ctx.key,replace(self.ctx,**{key:value}).key)
