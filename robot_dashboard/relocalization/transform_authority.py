"""Bound the operational TF graph to a verified device topology.

Humble does not reliably deliver MessageInfo to ordinary callbacks. This
monitor therefore records graph endpoint identities and checks target edges
before this runtime starts publishing them. It never attributes a TF message
to a publisher from its node name or from a matching transform value.
"""
from __future__ import annotations

import math
import re
import time
from collections.abc import Mapping


TOPICS = ('/tf', '/tf_static')
PROTECTED_EDGES = frozenset({('map', 'odom'), ('odom', 'base_link')})
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')


def _field(value, key):
    return value.get(key) if isinstance(value, Mapping) else getattr(value, key, None)


def _node(value):
    name, namespace = _field(value, 'node_name'), _field(value, 'node_namespace')
    if (not isinstance(name, str) or not _NAME.fullmatch(name)
            or not isinstance(namespace, str) or len(namespace) > 256
            or not namespace.startswith('/') or '//' in namespace
            or (namespace != '/' and namespace.endswith('/'))
            or any(not _NAME.fullmatch(part) for part in namespace.split('/') if part)):
        raise ValueError('TF_AUTHORITY_NODE_INVALID')
    return name, namespace


def _gid(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        result = bytes(value)
    elif isinstance(value, (list, tuple)) and all(type(x) is int and 0 <= x <= 255 for x in value):
        result = bytes(value)
    else:
        raise ValueError('TF_GRAPH_ENDPOINT_ID_UNAVAILABLE')
    if len(result) not in (16, 24) or not any(result):
        raise ValueError('TF_GRAPH_ENDPOINT_ID_UNAVAILABLE')
    return result.hex()


class TransformAuthorityMonitor:
    """One process-lifetime preflight; graph changes revoke its authority.

    ``allowed`` has exactly /tf and /tf_static keys. Each value is a list of
    server-verified ``node_name``/``node_namespace`` objects, excluding this
    runtime. A steady graph contains exactly one own endpoint per topic and
    exactly one endpoint for each configured external node on that topic.
    """

    def __init__(self, allowed, *, own_name='robot_scope_navigation_runtime',
                 own_namespace='/', clock=time.monotonic, settle_s=1.,
                 maximum_graph_age_s=.5):
        self.clock = clock
        self.own = _node({'node_name': own_name, 'node_namespace': own_namespace})
        if (not isinstance(allowed, Mapping) or set(allowed) != set(TOPICS)
                or type(settle_s) not in (int, float) or not math.isfinite(settle_s)
                or not .1 <= settle_s <= 5.
                or type(maximum_graph_age_s) not in (int, float)
                or not math.isfinite(maximum_graph_age_s) or not .1 <= maximum_graph_age_s <= 2.):
            raise ValueError('TF_AUTHORITY_CALIBRATION_REQUIRED')
        self.allowed = {}
        for topic in TOPICS:
            rows = allowed[topic]
            if not isinstance(rows, list) or len(rows) > 32:
                raise ValueError('TF_AUTHORITY_CALIBRATION_REQUIRED')
            identities = []
            for row in rows:
                if not isinstance(row, Mapping) or set(row) != {'node_name', 'node_namespace'}:
                    raise ValueError('TF_AUTHORITY_CALIBRATION_REQUIRED')
                identities.append(_node(row))
            if len(set(identities)) != len(identities) or self.own in identities:
                raise ValueError('TF_AUTHORITY_CALIBRATION_DUPLICATE')
            self.allowed[topic] = frozenset(identities)
        self.settle_s, self.maximum_graph_age_s = float(settle_s), float(maximum_graph_age_s)
        self.signature = None
        self.observed_at = None
        self.stable_since = None
        self._blocked = None
        self._reason = 'TF_GRAPH_UNAVAILABLE'
        self.publishing = False
        self._streams = set()

    def _block(self, reason):
        self._blocked = reason
        self._reason = reason
        return False

    def observe_graph(self, infos_tf, infos_static, *, own_name=None, own_namespace=None):
        """Observe actual ROS graph endpoints, rejecting substitutions and gaps.

        Discovery may be incomplete before the first valid snapshot. Once a
        graph is bound, any missing or changed endpoint requires a new monitor
        and an explicit source/seed initialization by the runtime owner.
        """
        if self._blocked:
            return False
        if own_name is not None or own_namespace is not None:
            supplied = _node({'node_name': own_name or self.own[0],
                              'node_namespace': own_namespace or self.own[1]})
            if supplied != self.own:
                return self._block('TF_OWN_AUTHORITY_CHANGED')
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            return self._block('TF_GRAPH_CLOCK_INVALID')
        if self.observed_at is not None and now < self.observed_at:
            return self._block('TF_GRAPH_CLOCK_REVERSED')
        signature = []
        reason = None
        try:
            for topic, infos in zip(TOPICS, (infos_tf, infos_static)):
                if not isinstance(infos, (list, tuple)) or len(infos) > 64:
                    raise ValueError('TF_GRAPH_UNAVAILABLE')
                entries = [(_node(info), _gid(_field(info, 'endpoint_gid'))) for info in infos]
                nodes = [entry[0] for entry in entries]
                if len(nodes) != len(set(nodes)):
                    raise ValueError('TF_GRAPH_DUPLICATE_AUTHORITY')
                if nodes.count(self.own) != 1:
                    raise ValueError('TF_GRAPH_OWN_AUTHORITY_NOT_UNIQUE')
                external = set(nodes) - {self.own}
                if external - self.allowed[topic]:
                    raise ValueError('TF_GRAPH_UNEXPECTED_AUTHORITY')
                if external != self.allowed[topic]:
                    raise ValueError('TF_GRAPH_REQUIRED_AUTHORITY_MISSING')
                signature.append((topic, tuple(sorted(entries))))
        except (ValueError, TypeError) as exc:
            reason = str(exc) or 'TF_GRAPH_UNAVAILABLE'
        if reason:
            if self.signature is not None:
                return self._block(reason)
            self._reason = reason
            return False
        signature = tuple(signature)
        if self.signature is not None and signature != self.signature:
            return self._block('TF_GRAPH_ENDPOINT_CHANGED')
        if self.signature is None:
            self.signature = signature
            self.stable_since = now
        self.observed_at = now
        self._reason = 'TF_PREFLIGHT_SETTLING'
        return self.ready

    def observe_transforms(self, message, *, topic='/tf'):
        """Inspect edges while protected-edge output is still suppressed.

        After ``begin_publication`` own echoes cannot be attributed on Humble;
        the stable verified graph remains the authority evidence in that phase.
        """
        if self._blocked:
            return False
        if topic not in TOPICS:
            return self._block('TF_TOPIC_INVALID')
        transforms = _field(message, 'transforms')
        if not isinstance(transforms, (list, tuple)) or len(transforms) > 256:
            return self._block('TF_MESSAGE_INVALID')
        if not self.publishing:
            for transform in transforms:
                parent = _field(_field(transform, 'header'), 'frame_id')
                child = _field(transform, 'child_frame_id')
                if not isinstance(parent, str) or not isinstance(child, str):
                    return self._block('TF_MESSAGE_INVALID')
                edge = (parent.lstrip('/'), child.lstrip('/'))
                if edge in PROTECTED_EDGES or edge[1] in {'odom', 'base_link'}:
                    return self._block('TF_PROTECTED_EDGE_ALREADY_PUBLISHED')
        if transforms:
            self._streams.add(topic)
        return True

    @property
    def ready(self):
        if self._blocked or self.signature is None or self.observed_at is None:
            return False
        now = self.clock()
        if not 0 <= now - self.observed_at <= self.maximum_graph_age_s:
            self._reason = 'TF_GRAPH_STALE'
            return False
        if not self.publishing and any(self.allowed[t] and t not in self._streams for t in TOPICS):
            self._reason = 'TF_PREFLIGHT_STREAM_NOT_OBSERVED'
            return False
        if now - self.stable_since < self.settle_s:
            self._reason = 'TF_PREFLIGHT_SETTLING'
            return False
        self._reason = 'TF_AUTHORITY_READY'
        return True

    @property
    def reason(self):
        self.ready
        return self._reason

    def begin_publication(self):
        if not self.ready:
            raise ValueError(self.reason)
        self.publishing = True

    def snapshot(self):
        ready = self.ready
        return {'ready': ready, 'reason': self.reason, 'publishing': self.publishing,
                'verification': 'VERIFIED_TOPOLOGY_AND_STABLE_GRAPH',
                'per_message_publisher_verified': False}
