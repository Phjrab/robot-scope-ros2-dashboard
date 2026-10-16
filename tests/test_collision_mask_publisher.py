"""SOFTWARE_TEST: ROS-shaped publisher/readback without native ingestion claims."""
from copy import deepcopy
import json
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from robot_dashboard.navigation_collision_profile import BINDING_TOPIC, MASK_TOPIC, PUBLISHER_NAME, mask_binding
from robot_dashboard.navigation_policy import RuntimePolicyProvider
from robot_dashboard.ros.collision_mask_publisher import CollisionMaskPublisher, source_authorities
from robot_dashboard.ros.policy_readback import PARAMETERS, RosPolicyReadback
from test_navigation_collision_mask import build, geometry
from test_runtime_policy import observed


def endpoint(gid=1, name=PUBLISHER_NAME):
    return NS(node_name=name, node_namespace="/", endpoint_gid=bytes([gid]) * 24)


class Harness:
    def __init__(self):
        self.now = 10.0
        self.graph = {MASK_TOPIC: [endpoint(1)], BINDING_TOPIC: [endpoint(2)]}
        self.published, self.qos = {}, {}
        self.node = NS(get_publishers_info_by_topic=lambda topic: self.graph.get(topic, []),
                       get_clock=lambda: NS(now=lambda: NS(to_msg=lambda: NS(sec=12, nanosec=34))),
                       create_publisher=self.create_publisher)

    def create_publisher(self, kind, topic, qos):
        self.qos[topic] = qos
        self.published[topic] = []
        return NS(publish=lambda message: self.published[topic].append(deepcopy(message)))

    def modules(self):
        def grid():
            return NS(header=NS(), info=NS(origin=NS(position=NS(), orientation=NS())))
        return {
            "nav_msgs.msg": NS(OccupancyGrid=grid), "std_msgs.msg": NS(String=NS),
            "rclpy.qos": NS(QoSProfile=NS, DurabilityPolicy=NS(TRANSIENT_LOCAL="transient", VOLATILE="volatile"),
                            ReliabilityPolicy=NS(RELIABLE="reliable")),
        }

    def observer(self):
        return RosPolicyReadback(self.node, clock=lambda: self.now)

    def deliver(self, observer, *, sequence=1, incarnation="a" * 32, artifact=None, gid=2):
        binding = mask_binding(artifact or build(geometry()), incarnation=incarnation, sequence=sequence)
        observer._on_mask(NS(data=json.dumps(binding)), NS(publisher_gid=bytes([gid]) * 24))


class CollisionMaskPublisherTests(unittest.TestCase):
    def publisher(self, harness, artifact=None):
        with patch.dict(sys.modules, harness.modules()):
            return CollisionMaskPublisher(harness.node, artifact or build(geometry()), clock=lambda: harness.now)

    def test_real_grid_order_pose_mask_and_transient_qos_with_volatile_heartbeat(self):
        h = Harness()
        artifact = build(geometry(origin=(2., -3., .2), occupancy=bytes([0, 255, 100] + [0] * 61)))
        publisher = self.publisher(h, artifact)
        publisher.tick()
        message = h.published[MASK_TOPIC][0]
        self.assertEqual(message.header.frame_id, "map")
        self.assertEqual(message.data[:3], [0, 100, 100])
        self.assertEqual((message.info.width, message.info.height), (8, 8))
        self.assertEqual((message.info.origin.position.x, message.info.origin.position.y), (2., -3.))
        self.assertAlmostEqual(message.info.origin.orientation.z, .09983341664682815)
        self.assertEqual(h.qos[MASK_TOPIC].durability, "transient")
        self.assertEqual(h.qos[BINDING_TOPIC].durability, "volatile")
        self.assertEqual(h.qos[MASK_TOPIC].depth, 1)
        self.assertEqual(set(h.published), {MASK_TOPIC, BINDING_TOPIC})
        self.assertFalse(json.loads(h.published[BINDING_TOPIC][0].data)["runtime_policy_enforced"])

    def test_one_immutable_grid_and_monotonic_heartbeats(self):
        h = Harness()
        publisher = self.publisher(h)
        for i in range(4):
            h.now += .25
            publisher.tick()
        self.assertEqual(len(h.published[MASK_TOPIC]), 1)
        values = [json.loads(message.data) for message in h.published[BINDING_TOPIC]]
        self.assertEqual([value["sequence"] for value in values], [1, 2, 3, 4])
        self.assertEqual(len({value["incarnation"] for value in values}), 1)

    def test_duplicate_foreign_zero_gid_and_changed_authority_stop_publication(self):
        for mutation in (
            lambda h: h.graph[MASK_TOPIC].append(endpoint(3)),
            lambda h: h.graph.update({MASK_TOPIC: [endpoint(3, "foreign")]}),
            lambda h: h.graph.update({MASK_TOPIC: [endpoint(0)]}),
            lambda h: h.graph.update({MASK_TOPIC: [endpoint(3)]}),
            lambda h: h.graph.update({BINDING_TOPIC: []}),
        ):
            h = Harness()
            publisher = self.publisher(h)
            publisher.tick()
            mutation(h)
            with self.assertRaises(ValueError):
                publisher.tick()
            self.assertEqual(len(h.published[MASK_TOPIC]), 1)
            self.assertEqual(len(h.published[BINDING_TOPIC]), 1)

    def test_startup_discovery_is_bounded_and_foreign_writer_is_immediate_failure(self):
        h = Harness()
        h.graph[MASK_TOPIC] = []
        publisher = self.publisher(h)
        publisher.tick()
        self.assertEqual(h.published[MASK_TOPIC], [])
        self.assertEqual(h.published[BINDING_TOPIC], [])
        h.now += 3.001
        with self.assertRaises(ValueError):
            publisher.tick()
        h = Harness()
        h.graph[MASK_TOPIC] = [endpoint(3, "foreign")]
        publisher = self.publisher(h)
        with self.assertRaises(ValueError):
            publisher.tick()
        self.assertEqual(h.published[BINDING_TOPIC], [])

    def test_publication_incarnation_changes_on_new_publisher(self):
        h = Harness()
        first = self.publisher(h)
        second = self.publisher(h)
        self.assertNotEqual(first.incarnation, second.incarnation)

    def test_source_authority_genuine_humble_shape(self):
        self.assertEqual(source_authorities(Harness().node), {"mask": "01" * 24, "binding": "02" * 24})


class CollisionMaskReadbackTests(unittest.TestCase):
    def test_missing_source_preserves_previous_readback_shape(self):
        h = Harness()
        observer = h.observer()
        observer._check_mask_source()
        self.assertNotIn("collision_mask_source", observer.snapshot())

    def test_freshness_uses_receipt_and_expires_without_changing_identity(self):
        h = Harness()
        observer = h.observer()
        h.deliver(observer)
        first = observer.snapshot()["collision_mask_source"]
        self.assertEqual(first["status"], "current")
        h.now += .75
        self.assertEqual(observer.snapshot()["collision_mask_source"]["status"], "current")
        h.now += .000001
        stale = observer.snapshot()["collision_mask_source"]
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["binding"], first["binding"])

    def test_wrong_message_gid_and_duplicate_sources_never_fresh(self):
        h = Harness()
        observer = h.observer()
        h.deliver(observer, gid=9)
        self.assertEqual(observer.snapshot()["collision_mask_source"]["status"], "unavailable")
        h.graph[BINDING_TOPIC].append(endpoint(3))
        h.deliver(observer, sequence=2)
        self.assertEqual(observer.snapshot()["collision_mask_source"]["status"], "unavailable")

    def test_replayed_sequence_mutated_artifact_and_source_loss_invalidate(self):
        for mutation in ("replay", "artifact", "loss", "incarnation_gid"):
            with self.subTest(mutation=mutation):
                h = Harness()
                observer = h.observer()
                h.deliver(observer)
                h.now += .2
                if mutation == "replay":
                    h.deliver(observer)
                elif mutation == "artifact":
                    h.deliver(observer, sequence=2, artifact=build(geometry(occupancy=bytes([100] + [0] * 63))))
                elif mutation == "loss":
                    h.graph[MASK_TOPIC] = []
                    observer._check_mask_source()
                else:
                    h.graph[MASK_TOPIC] = [endpoint(3)]
                    observer._check_mask_source()
                source = observer.snapshot()["collision_mask_source"]
                self.assertEqual(source["status"], "invalid")
                self.assertAlmostEqual(source["age_s"], .2)

    def test_new_incarnation_accepted_as_new_source_not_old_evidence(self):
        h = Harness()
        observer = h.observer()
        h.deliver(observer)
        h.graph[MASK_TOPIC], h.graph[BINDING_TOPIC] = [endpoint(3)], [endpoint(4)]
        h.deliver(observer, incarnation="b" * 32, gid=4)
        source = observer.snapshot()["collision_mask_source"]
        self.assertEqual(source["status"], "current")
        self.assertEqual(source["binding"]["incarnation"], "b" * 32)
        self.assertEqual(source["authorities"]["binding"], "04" * 24)

    def test_malformed_remote_data_not_leaked(self):
        h = Harness()
        observer = h.observer()
        observer._on_mask(NS(data="private/path"), NS(publisher_gid=bytes([2]) * 24))
        source = observer.snapshot()["collision_mask_source"]
        self.assertNotIn("private", repr(source))
        self.assertEqual(source["reason"], "MASK_SOURCE_INVALID")

    def test_provider_projects_only_publication_evidence_and_never_scope_true(self):
        h = Harness()
        observer = h.observer()
        h.deliver(observer)
        raw = observed()
        raw["policy_readback"]["collision_mask_source"] = observer.snapshot()["collision_mask_source"]
        provider = RuntimePolicyProvider(lambda: raw)
        first = provider()
        source = first["evidence"]["collision_mask_source"]
        self.assertEqual(source["status"], "current")
        self.assertFalse(source["native_ingestion_verified"])
        self.assertFalse(first["runtime_policy_enforced"])
        self.assertEqual(set(first["scopes"].values()), {False})
        self.assertIn("POLICY_MASK_INGESTION_UNVERIFIED", first["blocking_reasons"])
        h.deliver(observer, sequence=2)
        raw["policy_readback"]["collision_mask_source"] = observer.snapshot()["collision_mask_source"]
        self.assertEqual(first["semantic"], provider()["semantic"])
        h.now += 1
        raw["policy_readback"]["collision_mask_source"] = observer.snapshot()["collision_mask_source"]
        self.assertEqual(first["semantic"], provider()["semantic"])
        h.deliver(observer, sequence=1, incarnation="b" * 32)
        raw["policy_readback"]["collision_mask_source"] = observer.snapshot()["collision_mask_source"]
        self.assertNotEqual(first["semantic"], provider()["semantic"])

    def test_forged_binding_and_invalid_authorities_are_not_projected(self):
        h = Harness()
        observer = h.observer()
        h.deliver(observer)
        source = observer.snapshot()["collision_mask_source"]
        for mutate in (
            lambda value: value["binding"].update(runtime_policy_enforced=True),
            lambda value: value["authorities"].update(mask="x" * 48),
            lambda value: value["authorities"].update(binding="0" * 48),
        ):
            raw = observed()
            altered = deepcopy(source)
            mutate(altered)
            raw["policy_readback"]["collision_mask_source"] = altered
            result = RuntimePolicyProvider(lambda: raw)()
            self.assertFalse(result["runtime_policy_enforced"])
            self.assertEqual(result["evidence"]["collision_mask_source"]["status"], "unavailable")
            self.assertNotIn("collision_mask_source", result["semantic"])

    def test_observer_reads_effective_policy_fields_without_extra_service_requests(self):
        self.assertEqual(len(PARAMETERS), 5)
        for node in ("/global_costmap/global_costmap", "/local_costmap/local_costmap"):
            for parameter in ("policy_layer.map_topic", "policy_layer.footprint_clearing_enabled", "use_maximum",
                              "unknown_cost_value", "lethal_cost_threshold", "trinary_costmap"):
                self.assertIn(parameter, PARAMETERS[node])


if __name__ == "__main__":
    unittest.main()
