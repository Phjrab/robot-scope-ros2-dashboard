"""SOFTWARE_TEST: gateway consumes ROS-shaped runtime envelopes, no graph run."""
import json
from types import SimpleNamespace as NS
import unittest

from test_ros_navigation_gateway import gateway
from robot_dashboard.localization_diagnostics import LocalizationInputDiagnostics


def payload(sequence, *, pid=123, instance='123:1000', envelope=None):
    return dict(schema='robot-scope.navigation-runtime-health.v1', ready=True,
        cloud_fresh=True, odom_fresh=True, localized=False,
        cloud_topic='/velodyne_points', scan_topic='/scan', odometry_topic='/Odometry',
        cloud_frame='hesai_lidar', publisher_counts={'/velodyne_points':1,'/Odometry':1},
        input_points=100, accepted_points=100, cloud_sequence=sequence, odometry_sequence=sequence,
        cloud_frequency_hz=10., cloud_jitter_s=.01, cloud_age_s=.02,
        odometry_frequency_hz=10., odometry_jitter_s=.01, odometry_age_s=.02,
        process_generation=pid, runtime_instance_generation=instance, health_sequence=sequence if envelope is None else envelope)


class GatewayGenerationTests(unittest.TestCase):
    def test_same_job_restart_resets_sequence_and_rewarms_without_old_count(self):
        g = gateway()
        def send(v): g._navigation_runtime_health_callback(NS(data=json.dumps(v)))
        for seq in (100,101,102): send(payload(seq))
        self.assertEqual(g._navigation_runtime_health['fresh_sequence_count'],3)
        send(payload(1,pid=124,instance='124:2000'))
        self.assertEqual(g._navigation_runtime_health['fresh_sequence_count'],1)
        send(payload(2,pid=124,instance='124:2000'))
        self.assertEqual(g._navigation_runtime_health['fresh_sequence_count'],2)
        # PID reuse is a distinct incarnation even when the job and PID match.
        send(payload(1,pid=124,instance='124:3000'))
        self.assertEqual(g._navigation_runtime_health['fresh_sequence_count'],1)

    def test_retired_invocation_cannot_replace_new_runtime_or_renew_receipt(self):
        g = gateway()
        for value in (payload(100),payload(1,pid=124,instance='124:2000')):
            g._navigation_runtime_health_callback(NS(data=json.dumps(value)))
        receipt = g._navigation_runtime_health_received
        g._navigation_runtime_health_callback(NS(data=json.dumps(payload(101))))
        self.assertEqual(g._navigation_runtime_health['runtime_instance_generation'],'124:2000')
        self.assertEqual(g._navigation_runtime_health_received,receipt)

    def test_duplicate_health_envelope_does_not_renew_receipt(self):
        g = gateway()
        g._navigation_runtime_health_callback(NS(data=json.dumps(payload(10))))
        receipt = g._navigation_runtime_health_received
        g._navigation_runtime_health_callback(NS(data=json.dumps(payload(11,envelope=10))))
        self.assertEqual(g._navigation_runtime_health_received,receipt)
        self.assertEqual(g._navigation_health_sequences,(10,10))

    def test_invalid_optional_diagnostic_cannot_poison_core_health(self):
        g = gateway()
        v = payload(1)
        v['localization_diagnostics'] = {'schema':'bad','secret':'untrusted'}
        g._navigation_runtime_health_callback(NS(data=json.dumps(v)))
        self.assertTrue(g._navigation_runtime_health['ready'])
        self.assertNotIn('localization_diagnostics',g._navigation_runtime_health)

    def test_diagnostic_snapshot_retained_only_for_matching_invocation(self):
        g = gateway()
        diagnostics = dict(schema='robot-scope.localization-input-diagnostics.v1', process_generation=123,
            runtime_instance_generation='123:1000', health_sequence=1, observed_wall_ns=1000,
            observed_monotonic_s=10., executor_lock_wait_s=None, initialization_wait_reason='cloud_not_fresh',
            inputs={name: LocalizationInputDiagnostics(name).snapshot(10.) for name in ('cloud','odometry')})
        def send(v): g._navigation_runtime_health_callback(NS(data=json.dumps(v)))
        first = payload(1); first['localization_diagnostics'] = diagnostics; send(first)
        self.assertEqual(g._navigation_runtime_health['localization_diagnostics']['health_sequence'],1)
        send(payload(2))
        self.assertEqual(g._navigation_runtime_health['localization_diagnostics']['health_sequence'],1)
        changed = payload(1,pid=124,instance='124:2000')
        changed['localization_diagnostics'] = diagnostics
        send(changed)
        self.assertNotIn('localization_diagnostics',g._navigation_runtime_health)
