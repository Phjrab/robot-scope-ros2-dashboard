"""Explicit review-only ROS attachment; constructor/import perform no ROS I/O."""
from .isolation import RuntimeConfig, NAMESPACE, require_local_ros, review_topic
from .nav2 import ros_pointcloud
import threading
import time


class ReviewRosPort:
    """Existing owner supplies identity_provider, not a new device owner.

    The provider must return the original epoch/seq/clock metadata for the
    message header. Header timestamps alone cannot identify publisher restart.
    Only synthetic/replay review topics are accepted by this candidate.
    """
    def __init__(self, *, config=RuntimeConfig(), runtime, identity_provider, owner_loop,
                 clock_ns=time.monotonic_ns):
        self.config, self.runtime, self.identity_provider = config, runtime, identity_provider
        self.owner_loop = owner_loop
        self.clock_ns = clock_ns
        self.node = self.context = None
        self.publishers = {}
        self.subscriptions = []
        self._lock = threading.Lock()
        self._pending = None
        self._scheduled = False
        self.closed = False
        self.handoff_dropped = 0

    def handoff(self, message, identity, normalize):
        """At most one scheduled loop callback and one pending message."""
        with self._lock:
            if self.closed:
                return False
            if self._pending is not None:
                self.handoff_dropped += 1
            self._pending = (message, identity, normalize)
            if not self._scheduled:
                self._scheduled = True
                self.owner_loop.call_soon_threadsafe(self._drain)
        return True

    def _drain(self):
        with self._lock:
            pending, self._pending = self._pending, None
            self._scheduled = False
            closed = self.closed
        if pending and not closed:
            message, identity, normalize = pending
            origin = (0., 0., 0.) if identity.frame_id in {"review_lidar", "review_depth"} else None
            self.runtime.offer_raw(message, identity, normalize, origin_m=origin)

    def start(self, *, input_topics):
        if self.closed or self.node is not None or not 0 < len(input_topics) <= 16:
            raise ValueError("ROS_PORT_STATE_OR_TOPIC_LIMIT")
        topics = [review_topic(t) for t in input_topics]
        require_local_ros(self.config)
        # No graph query, topic scan or ROS daemon is used for preflight.
        from ament_index_python.packages import get_package_share_directory
        from pathlib import Path
        import xml.etree.ElementTree as ET
        for package in ("nav2_costmap_2d", "nav2_planner"):
            share = Path(get_package_share_directory(package))
            if ET.parse(share/"package.xml").getroot().findtext("version") != "1.1.20":
                raise ValueError("NAV2_1_1_20_REQUIRED")
        import rclpy
        from rclpy.context import Context
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
        from sensor_msgs.msg import PointCloud2
        from .messages import pointcloud2
        self.context = Context()
        rclpy.init(args=[], context=self.context, domain_id=self.config.domain_id)
        self.node = Node("c4_readonly_port", namespace=NAMESPACE, context=self.context,
                         enable_rosout=False, start_parameter_services=False)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST)
        for topic in topics:
            def receive(message, source_topic=topic):
                identity = self.identity_provider(source_topic, message)
                if identity.evidence_kind not in {"SYNTHETIC", "REPLAY"}:
                    raise ValueError("LIVE_INPUT_FORBIDDEN")
                # Identity provider is a bounded metadata lookup. Layout/D2 work
                # occurs in RuntimeAdapter's existing latest-only worker.
                self.handoff(message, identity, pointcloud2)
            self.subscriptions.append(self.node.create_subscription(PointCloud2, topic, receive, qos))
        for topic in ("/review/lidar_points", "/review/depth_points", "/review/geometry_marking"):
            self.publishers[topic] = self.node.create_publisher(PointCloud2, topic, qos)

    def attach_observer(self, evidence, *, expected_lethal_indices=lambda scope: ()):
        """Read native snapshots only. D3 supplies occupied-cell expectations.

        Callback work is bounded message conversion; no perception/planning or
        collision algorithm executes on a subscriber. The caller serializes
        observer/snapshot reads in its ROS executor.
        """
        if self.node is None:
            raise ValueError("EXPLICIT_ROS_START_REQUIRED")
        from nav_msgs.msg import OccupancyGrid, Path
        from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)
        for scope in ("global", "local"):
            topic = f"{NAMESPACE}/{scope}_costmap/costmap"
            def receive(message, s=scope, t=topic):
                identity = self.identity_provider(t, message)
                evidence.costmap(message, identity, scope=s,
                    expected_lethal_indices=expected_lethal_indices(s), source="NATIVE_NAV2_SIM")
            self.subscriptions.append(self.node.create_subscription(OccupancyGrid, topic, receive, qos))
        def plan(message):
            evidence.path(message, self.identity_provider("/review/plan", message), source="NATIVE_NAV2_SIM")
        self.subscriptions.append(self.node.create_subscription(Path, "/review/plan", plan, qos))

    def publish(self, observation):
        if self.node is None or observation.topic not in self.publishers:
            raise ValueError("EXPLICIT_ROS_START_REQUIRED")
        expected_clear = observation.topic == "/review/lidar_points"
        if observation.clearing != expected_clear:
            raise ValueError("PROFILE_CLEARING_POLICY_MISMATCH")
        from .nav2 import observation as checked_observation
        kind = {"/review/lidar_points":"lidar", "/review/depth_points":"depth", "/review/geometry_marking":"geometry"}[observation.topic]
        checked = checked_observation(observation.sample, topic=observation.topic, source_kind=kind,
            now_ns=self.clock_ns(), receipt_clock_id=self.runtime.receipt_clock_id)
        if checked.clearing != observation.clearing:
            raise ValueError("SENSOR_ORIGIN_OR_FRAME_MISMATCH")
        from sensor_msgs.msg import PointCloud2, PointField
        message = ros_pointcloud(observation, pointcloud_type=PointCloud2, field_type=PointField)
        self.publishers[observation.topic].publish(message)
        # Only the caller may record publication; no ingestion is inferred.

    def close(self):
        with self._lock:
            self.closed = True
            self._pending = None
        if self.node is not None:
            self.node.destroy_node()
            self.node = None
        if self.context is not None:
            self.context.shutdown()
            self.context = None
        self.subscriptions.clear()
        self.publishers.clear()
