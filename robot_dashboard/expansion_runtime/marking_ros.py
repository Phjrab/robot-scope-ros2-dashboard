"""Injected review-node publisher, raw marking only; creates no subscription."""
from robot_dashboard.obstacle_runtime_adapter.isolation import NAMESPACE
from robot_dashboard.obstacle_runtime_adapter.nav2 import Observation, ros_pointcloud
import os

TOPIC = NAMESPACE+'/c4/marking'


class MarkingRosPublisher:
    def __init__(self, node, *, context_provider, clock_ns):
        # The harness performs network-none/local-domain preflight before init.
        if (node.get_namespace() != NAMESPACE or os.environ.get('C4_NETWORK_NONE') != '1'
                or os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '194'
                or any(os.environ.get(k) for k in ('ROS_DISCOVERY_SERVER','FASTRTPS_DEFAULT_PROFILES_FILE',
                                                   'FASTDDS_DEFAULT_PROFILES_FILE','CYCLONEDDS_URI'))):
            raise ValueError('ISOLATED_REVIEW_NODE_REQUIRED')
        from sensor_msgs.msg import PointCloud2
        from rclpy.qos import qos_profile_sensor_data
        self.publisher = node.create_publisher(PointCloud2, TOPIC, qos_profile_sensor_data)
        self.context_provider, self.clock_ns = context_provider, clock_ns
        # A native costmap does not inherit C1's generation reset. This publisher
        # stays bound to its initial native session; recreate it only after an
        # independently observed native reset. No automatic cross-map reuse.
        self.native_context_key = context_provider().key
        self.published = 0

    def __call__(self, completed):
        from sensor_msgs.msg import PointCloud2, PointField
        ctx = self.context_provider()
        identity = completed.sample.identity
        if ctx.key != self.native_context_key:
            raise ValueError('NATIVE_CONTEXT_RESET_REQUIRED')
        if (completed.work.context.key != ctx.key or completed.error
                or identity.receipt_clock_id != ctx.host_clock_id
                or not 0 <= self.clock_ns()-identity.received_ns <= 150_000_000):
            raise ValueError('STALE_OR_REBOUND_PUBLICATION_REJECTED')
        message = ros_pointcloud(Observation(completed.sample,TOPIC,True,False),
                                 pointcloud_type=PointCloud2,field_type=PointField)
        self.publisher.publish(message)
        self.published += 1
        # This counter proves publication only. Nav2 cells/path need readback.
