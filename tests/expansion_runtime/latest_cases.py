"""Executed only in a clean interpreter with the current read-only SHA exports."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from experiments.expansion_20261029.c4_runtime.followup.dependencies import load, REPO
from robot_dashboard.expansion_runtime import FinalIntentPort
from robot_dashboard.expansion_runtime.canonical_ports import legacy_observation


class CurrentComposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = load()
        from . import latest_fixtures
        cls.f = latest_fixtures

    def test_scoped_clear_real_d2_d3_c1_and_mock_sink(self):
        rt,p,s,c = self.f.setup()
        result = self.f.run(rt,p,s,complete=True)
        self.assertEqual(result.intent.severity, 'CLEAR', result.intent.reason)
        wire = result.assessment
        self.assertEqual(wire['schema_version'], '0.2')
        self.assertEqual(wire['validity_interval']['end_monotonic_ns'], '1200000000')
        self.assertEqual(wire['freshness']['source_validity_interval']['until_ns'], '1250000000')
        self.assertEqual(wire['obstacle_frame_ref']['stamp_ns'], p.meta['stamp_ns'])
        self.assertEqual(wire['freshness']['protection_mode'], 'ACTIVE_CONSTRAINT')
        self.assertTrue(wire['freshness']['coverage']['complete_for_motion'])
        gate = FinalIntentPort(rt.context, mode=rt.mode)
        checked = gate.apply(result.intent, now_ns=c.now, issued_ns=c.now, expires_ns=c.now+100_000_000)
        self.assertFalse(checked.hold)
        self.assertEqual(checked.velocity, (.1,0.,0.))
        self.assertTrue(gate.tick(now_ns=c.now+100_000_001).hold)
        self.assertFalse(result.adapter_published)
        self.assertFalse(result.native_costmap_ingestion_observed)

    def test_no_coverage_empty_and_positive_distance_remain_unknown(self):
        for point in (None, 2.):
            rt,p,s,c = self.f.setup(point_x=point)
            result = self.f.run(rt,p,s)
            self.assertEqual(result.assessment['severity'], 'UNKNOWN', result.intent.reason)
            self.assertEqual(result.intent.severity, 'UNKNOWN')
            self.assertFalse(result.assessment['freshness']['coverage']['complete_for_motion'])

    def test_model_overlap_is_stop_not_physical_contact(self):
        rt,p,s,c = self.f.setup(point_x=.1)
        result = self.f.run(rt,p,s)
        self.assertEqual(result.assessment['reason'], 'MODEL_OVERLAP')
        self.assertEqual(result.intent.severity, 'STOP_REQUIRED')
        gate = FinalIntentPort(rt.context,mode=rt.mode)
        self.assertTrue(gate.apply(result.intent, now_ns=c.now, issued_ns=c.now, expires_ns=c.now+10).hold)

    def test_missing_volume_short_horizon_and_wrong_motion_reject(self):
        for change in ('missing', 'volume', 'horizon', 'motion', 'replay'):
            rt,p,s,c = self.f.setup()
            certificate = self.f.coverage(rt,p)
            if change == 'missing': certificate = replace(certificate, evidence=None)
            elif change == 'motion': certificate = replace(certificate, motion_hash='wrong-command')
            else:
                evidence = deepcopy(certificate.evidence)
                if change == 'volume': evidence['volume_min'] = [0,0,0]
                elif change == 'horizon': evidence['horizon_s'] = .01
                else: evidence['evidence_kind'] = 'REPLAY'
                certificate = replace(certificate, evidence=evidence)
            result = self.f.run(rt,p,s,coverage=certificate)
            self.assertEqual(result.intent.severity, 'UNKNOWN', change)
            self.assertEqual(rt.mode, 'ACTIVE_CONSTRAINT')

    def test_authority_failure_separate_from_geometric_clear(self):
        rt,p,s,c = self.f.setup()
        result = self.f.run(rt,p,s,complete=True,authority_present=False)
        self.assertEqual(result.assessment['severity'], 'CLEAR')
        self.assertEqual(result.intent.reason, 'MISSING_TRUSTED_AUTHORITY')
        self.assertEqual(result.assessment['freshness']['c4']['intent_status']['severity'], 'UNKNOWN')
        rt,p,s,c = self.f.setup(active=False)
        result = self.f.run(rt,p,s)
        gate = FinalIntentPort(rt.context)
        self.assertEqual(gate.apply(result.intent, now_ns=c.now, issued_ns=c.now, expires_ns=c.now+10)['action'], 'DIAGNOSTIC_ONLY')
        self.assertFalse(gate.sink.history)

    def test_delay_never_restarts_original_expiry(self):
        rt,p,s,c = self.f.setup()
        actual = rt.ports.assess
        def delayed(*args, **kwargs):
            assessment = actual(*args, **kwargs)
            c.now = 1_300_000_000
            return assessment
        rt.ports.assess = delayed
        result = self.f.run(rt,p,s,complete=True)
        self.assertEqual(result.intent.reason, 'ASSESSMENT_EXPIRED_OR_UNMAPPED')
        self.assertEqual(result.intent.valid_until_ns, 1_200_000_000)
        self.assertEqual(result.assessment['received_monotonic_ns'], str(s['received_monotonic_ns']))

    def test_clock_uncertainty_and_mapping_window(self):
        rt,p,s,c = self.f.setup()
        rt.mapping = replace(rt.mapping, uncertainty_ns=1000)
        result = self.f.run(rt,p,s)
        self.assertEqual(result.assessment['validity_interval']['start_monotonic_ns'], '1000001000')
        self.assertEqual(result.assessment['validity_interval']['end_monotonic_ns'], '1249999000')
        rt,p,s,c = self.f.setup()
        rt.mapping = replace(rt.mapping, source_end_ns=1_100_000_000)
        result = self.f.run(rt,p,s)
        self.assertEqual(result.intent.reason, 'OUTSIDE_CLOCK_MAPPING_WINDOW')

    def test_clock_unknown_calibration_has_no_invented_expiry(self):
        rt,p,s,c = self.f.setup()
        s['calibration_known'] = False
        result = self.f.run(rt,p,s)
        self.assertEqual(result.assessment['validity_interval'], {})
        self.assertEqual(result.intent.severity, 'UNKNOWN')

    def test_duplicate_late_rebind_and_changed_clock_reject(self):
        rt,p,s,c = self.f.setup()
        self.f.run(rt,p,s,complete=True)
        self.assertEqual(self.f.run(rt,p,s).intent.reason, 'DUPLICATE_OR_REORDERED_INPUT')
        for key,value in dict(map_generation=1, family_revision='r2', footprint_revision='r2',
                              controller_goal_id='goal2', authority_generation=2, tf_epoch='tf2', clock_epoch='clock2').items():
            rt,p,s,c = self.f.setup()
            prior = self.f.run(rt,p,s,complete=True)
            context = replace(rt.context, runtime_generation=2, **{key:value})
            rt.rebind(context,rt.mapping)
            result = self.f.run(rt,p,s)
            self.assertEqual(result.intent.severity, 'UNKNOWN')
            gate = FinalIntentPort(context,mode=rt.mode)
            self.assertTrue(gate.apply(prior.intent, now_ns=c.now, issued_ns=c.now, expires_ns=c.now+10).hold)
        rt,p,s,c = self.f.setup(); c.now += 200_000_000
        self.assertEqual(self.f.run(rt,p,s).intent.reason, 'STALE_FUTURE_OR_LATE_INPUT')

    def test_depth_rejection_preserves_lidar_no_inferred_clearing(self):
        for invalid,detected in ((False,False),(True,True)):
            rt,p,s,c = self.f.setup()
            p = self.f.fixtures.rgbd(p,invalid=invalid,detections=detected)
            result = self.f.run(rt,p,s)
            self.assertTrue(result.sensor_processed, result.intent.reason)
            self.assertTrue(any(o['sensor_support']=='LIDAR' for o in result.obstacle_frame['obstacles']))
            self.assertFalse(result.clearing_evidence)

    def test_real_geometry_object_budget_rejects_incomplete_clear(self):
        import numpy as np
        rt,p,s,c = self.f.setup()
        points = np.array([[2+i*.5, j*.5, .3] for i in range(8) for j in range(9)])
        p = replace(p, lidar_points=points)
        result = self.f.run(rt,p,s,complete=True)
        self.assertEqual(result.intent.reason, 'GEOMETRY_INCOMPLETE_OBJECT_BUDGET')
        self.assertIsNone(result.assessment)

    def test_compaction_preserves_geometry_and_default_budget(self):
        rt,p,s,c = self.f.setup(); result = self.f.run(rt,p,s)
        frame = result.obstacle_frame
        compact = rt.ports.scene_obstacle(frame)
        self.assertEqual([o['geometry'] for o in compact['obstacles']], [o['geometry'] for o in frame['obstacles']])
        self.assertEqual(compact['received_monotonic_ns'], frame['received_monotonic_ns'])
        self.assertEqual(frame['obstacles'][0]['provenance'], result.obstacle_frame['obstacles'][0]['provenance'])
        large = deepcopy(frame)
        large['obstacles'] = [dict(deepcopy(frame['obstacles'][0]), id=f'large-{i}') for i in range(32)]
        with self.assertRaisesRegex(ValueError, 'FRAME_BUDGET_EXCEEDED'):
            rt.ports.scene_obstacle(large)
        self.assertEqual(len(large['obstacles']), 32)

    def test_c1_v02_http_snapshot_full_references_and_expiry(self):
        rt,p,s,c = self.f.setup(); result = self.f.run(rt,p,s,complete=True)
        service = self.f.scene(rt,result,c)
        response = json.loads(self.f.http_snapshot(service))
        self.assertEqual(response['schema_version'], '0.2')
        self.assertEqual(response['collision_assessment']['severity'], 'CLEAR')
        self.assertEqual(response['collision_assessment']['obstacle_frame_ref'], result.assessment['obstacle_frame_ref'])
        self.assertEqual(response['obstacle_frame']['received_monotonic_ns'], str(p.meta['received_monotonic_ns']))
        c.now = 1_200_000_001
        self.assertIsNone(service.snapshot()['collision_assessment'])

    def test_high_host_nanoseconds_lossless_v02_legacy_refuses(self):
        high = 2**53+1000
        c = self.f.fixtures.Clock(high+10_000_000)
        rt,p,s,c = self.f.setup(stamp=high,clock=c)
        rt.mapping = replace(rt.mapping, source_end_ns=high+1_000_000_000)
        certificate = replace(self.f.coverage(rt,p),valid_until_ns=high+200_000_000)
        result = self.f.run(rt,p,s,coverage=certificate)
        self.assertEqual(result.intent.severity, 'CLEAR', result.intent.reason)
        response = json.loads(self.f.http_snapshot(self.f.scene(rt,result,c)))
        self.assertEqual(response['collision_assessment']['received_monotonic_ns'], str(high+1_000_000))
        with self.assertRaisesRegex(ValueError, 'C1_V01_UNSAFE_JS_INTEGER'):
            legacy_observation(result.assessment,validate=rt.ports.contracts.CollisionAssessment.from_dict)

    def test_actual_c3_direct_v02_failure_and_explicit_legacy_partial_display(self):
        node = os.environ.get('C4_NODE', 'node')
        rt,p,s,c = self.f.setup(); result = self.f.run(rt,p,s,complete=True)
        script = REPO/'experiments/expansion_20261029/c4_runtime/followup/consumer_check.mjs'
        for version in ('0.2','0.1'):
            raw = self.f.http_snapshot(self.f.scene(rt,result,c,version=version))
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'snapshot.json'; path.write_text(raw)
                check = subprocess.run([node,str(script), str(self.paths['c3']/'robot_dashboard/static/features/obstacle_scene'),str(path)],
                                       capture_output=True,text=True,timeout=20)
                data = json.loads(check.stdout)
            if version == '0.2':
                self.assertEqual(check.returncode,2)
                self.assertEqual(data,dict(status='FAIL',reason='C1_VERSION_UNSUPPORTED'))
            else:
                self.assertEqual(check.returncode,0,check.stderr+check.stdout)
                self.assertEqual(data['status'],'PASS')
                self.assertEqual(data['collision_status'],'UNAVAILABLE')
                self.assertFalse(data['references_verified'])
