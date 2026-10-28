"""Operational TF authority uses actual endpoint identities, without ROS."""
import types
import unittest

from robot_dashboard.relocalization.transform_authority import TransformAuthorityMonitor


def endpoint(name, number, namespace='/'):
    return types.SimpleNamespace(node_name=name, node_namespace=namespace,
                                 endpoint_gid=bytes([number]) * 24)


def transforms(parent='camera_init', child='body'):
    return types.SimpleNamespace(transforms=[types.SimpleNamespace(
        header=types.SimpleNamespace(frame_id=parent), child_frame_id=child)])


class TransformAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.allowed = {'/tf': [{'node_name': 'laserMapping', 'node_namespace': '/'}], '/tf_static': []}
        self.monitor = TransformAuthorityMonitor(self.allowed, clock=lambda: self.now,
                                                settle_s=.2, maximum_graph_age_s=.5)
        self.tf = [endpoint('robot_scope_navigation_runtime', 1), endpoint('laserMapping', 2)]
        self.static = [endpoint('robot_scope_navigation_runtime', 3)]

    def settled(self):
        self.monitor.observe_transforms(transforms())
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))
        self.now += .21
        self.assertTrue(self.monitor.observe_graph(self.tf, self.static))

    def test_verified_fastlio_graph_settles_before_first_publication(self):
        self.settled()
        self.monitor.begin_publication()
        self.assertTrue(self.monitor.snapshot()['ready'])
        self.assertEqual(self.monitor.snapshot()['verification'], 'VERIFIED_TOPOLOGY_AND_STABLE_GRAPH')
        self.assertFalse(self.monitor.snapshot()['per_message_publisher_verified'])

    def test_preflight_target_edges_are_rejected_including_leading_slash(self):
        for parent, child in [('map', 'odom'), ('odom', 'base_link'), ('/map', '/odom'),
                              ('another_parent', 'base_link'), ('another_parent', 'odom')]:
            with self.subTest(parent=parent, child=child):
                monitor = TransformAuthorityMonitor(self.allowed, clock=lambda: self.now)
                self.assertFalse(monitor.observe_transforms(transforms(parent, child)))
                self.assertEqual(monitor.reason, 'TF_PROTECTED_EDGE_ALREADY_PUBLISHED')
                self.assertFalse(monitor.observe_graph(self.tf, self.static))

    def test_unexpected_authority_before_first_publish_never_becomes_ready(self):
        self.tf.append(endpoint('amcl', 4))
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_UNEXPECTED_AUTHORITY')

    def test_replaced_allowed_endpoint_revokes_the_existing_session(self):
        self.settled()
        self.monitor.begin_publication()
        self.tf[-1] = endpoint('laserMapping', 4)
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_ENDPOINT_CHANGED')
        self.tf[-1] = endpoint('laserMapping', 2)
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))

    def test_new_graph_node_revokes_even_if_it_might_publish_unrelated_edges(self):
        self.settled()
        self.tf.append(endpoint('another_localizer', 4))
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_UNEXPECTED_AUTHORITY')

    def test_duplicate_fixed_runtime_name_is_not_accepted_as_own_echo(self):
        self.tf.append(endpoint('robot_scope_navigation_runtime', 4))
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_DUPLICATE_AUTHORITY')

    def test_own_echo_after_publication_does_not_create_fake_conflict(self):
        self.settled()
        self.monitor.begin_publication()
        self.assertTrue(self.monitor.observe_transforms(transforms('map', 'odom')))
        self.assertTrue(self.monitor.ready)

    def test_unavailable_graph_or_empty_gid_cannot_grant_authority(self):
        self.assertFalse(self.monitor.observe_graph(None, self.static))
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_UNAVAILABLE')
        self.tf[-1].endpoint_gid = bytes(24)
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_ENDPOINT_ID_UNAVAILABLE')

    def test_missing_required_node_after_binding_stays_revoked(self):
        self.settled()
        self.assertFalse(self.monitor.observe_graph(self.tf[:1], self.static))
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_REQUIRED_AUTHORITY_MISSING')
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))

    def test_graph_expiry_and_clock_regression_are_not_fresh_evidence(self):
        self.settled()
        self.now += .6
        self.assertFalse(self.monitor.ready)
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_STALE')
        self.now = 99.
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))
        self.assertEqual(self.monitor.reason, 'TF_GRAPH_CLOCK_REVERSED')

    def test_unobserved_external_tf_stream_keeps_initialization_blocked(self):
        self.monitor.observe_graph(self.tf, self.static)
        self.now += .21
        self.assertFalse(self.monitor.observe_graph(self.tf, self.static))
        self.assertEqual(self.monitor.reason, 'TF_PREFLIGHT_STREAM_NOT_OBSERVED')

    def test_calibration_rejects_own_node_duplicates_and_unbounded_input(self):
        for allowed in ({}, {'/tf': [], '/tf_static': [], '/other': []},
                        {'/tf': [{'node_name': 'robot_scope_navigation_runtime', 'node_namespace': '/'}], '/tf_static': []},
                        {'/tf': self.allowed['/tf'] * 2, '/tf_static': []}):
            with self.subTest(allowed=allowed), self.assertRaises(ValueError):
                TransformAuthorityMonitor(allowed)


if __name__ == '__main__':
    unittest.main()
