"""Opt-in immutable OccupancyGrid publication; no TF, velocity or goal writes."""
from __future__ import annotations

import json
import math
import time
import uuid

from ..navigation_collision_profile import (
    BINDING_TOPIC, MASK_TOPIC, PUBLISHER_NAME, mask_binding,
)


def source_authorities(node) -> dict:
    """Require one fixed-node publisher on each topic, including no foreign one."""
    result = {}
    for key, topic in (("mask", MASK_TOPIC), ("binding", BINDING_TOPIC)):
        endpoints = node.get_publishers_info_by_topic(topic)
        if len(endpoints) != 1:
            raise ValueError("MASK_SOURCE_NOT_UNIQUE")
        endpoint = endpoints[0]
        gid = bytes(endpoint.endpoint_gid)
        if (endpoint.node_name != PUBLISHER_NAME or endpoint.node_namespace != "/"
                or len(gid) != 24 or not any(gid)):
            raise ValueError("MASK_SOURCE_NOT_UNIQUE")
        result[key] = gid.hex()
    return result


class CollisionMaskPublisher:
    """Own exactly two publishers and cease publication on source conflict.

    The runner destroys this node if tick raises. A disappeared publisher cannot
    leave a fresh binding heartbeat, even if a native costmap retains old data.
    """
    def __init__(self, node, artifact, *, clock=time.monotonic):
        from nav_msgs.msg import OccupancyGrid
        from std_msgs.msg import String
        from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
        self.node, self.artifact, self.clock = node, artifact, clock
        self.started = clock()
        self.incarnation, self.sequence = uuid.uuid4().hex, 0
        self._string = String
        self._source = None
        self._sent = False
        self.mask = OccupancyGrid()
        geometry = json.loads(artifact.manifest)["geometry"]
        self.mask.header.frame_id = geometry["frame_id"]
        self.mask.info.width, self.mask.info.height = geometry["width"], geometry["height"]
        self.mask.info.resolution = float(geometry["resolution"])
        ox, oy, yaw = geometry["origin"]
        self.mask.info.origin.position.x, self.mask.info.origin.position.y = float(ox), float(oy)
        self.mask.info.origin.orientation.z = math.sin(yaw / 2)
        self.mask.info.origin.orientation.w = math.cos(yaw / 2)
        self.mask.data = list(artifact.mask)
        self._mask_publisher = node.create_publisher(OccupancyGrid, MASK_TOPIC,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self._binding_publisher = node.create_publisher(String, BINDING_TOPIC,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.VOLATILE))

    def tick(self):
        try:
            current = source_authorities(self.node)
        except ValueError:
            # Discovery may not have delivered our own writers yet. A foreign
            # or duplicate writer fails immediately; zero writers get a bounded
            # discovery window, during which nothing is published.
            endpoints = [self.node.get_publishers_info_by_topic(topic)
                         for topic in (MASK_TOPIC, BINDING_TOPIC)]
            if (not self._sent and self.clock() - self.started <= 3.0
                    and all(not items or len(items) == 1
                            and items[0].node_name == PUBLISHER_NAME
                            and items[0].node_namespace == "/" for items in endpoints)
                    and any(not items for items in endpoints)):
                return
            raise
        if self._source is not None and current != self._source:
            raise ValueError("MASK_SOURCE_CHANGED")
        self._source = current
        if not self._sent:
            now = self.node.get_clock().now().to_msg()
            self.mask.header.stamp = now
            self.mask.info.map_load_time = now
            self._mask_publisher.publish(self.mask)
            self._sent = True
        if self.sequence == 2**63 - 1:
            raise ValueError("MASK_SEQUENCE_EXHAUSTED")
        self.sequence += 1
        message = self._string()
        message.data = json.dumps(mask_binding(self.artifact, incarnation=self.incarnation,
                                              sequence=self.sequence), sort_keys=True, separators=(",", ":"))
        self._binding_publisher.publish(message)


def run(artifact) -> int:
    import rclpy
    from rclpy.node import Node
    rclpy.init(args=[])
    node = None
    try:
        node = Node(PUBLISHER_NAME, namespace="/", use_global_arguments=False)
        publisher = CollisionMaskPublisher(node, artifact)
        node.create_timer(0.25, publisher.tick)
        rclpy.spin(node)
        return 0
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
