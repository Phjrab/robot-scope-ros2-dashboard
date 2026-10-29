"""Reject real endpoints before importing ROS or constructing an acquisition port."""
from dataclasses import dataclass
from pathlib import Path
import os

NAMESPACE = "/robot_scope_review_x"


def review_topic(topic: str) -> str:
    if (not isinstance(topic, str) or not topic.startswith("/review/")
            or any(x in topic for x in ("..", "//", ":", " "))):
        raise ValueError("REVIEW_TOPIC_REQUIRED")
    return topic


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str = "offline"
    endpoint: str = "synthetic://fixture"
    namespace: str = NAMESPACE
    domain_id: int = 171

    def __post_init__(self):
        if self.mode not in {"offline", "dry_run", "synthetic", "replay", "isolated_ros"}:
            raise ValueError("LIVE_MODE_FORBIDDEN")
        # Even localhost HTTP is unnecessary here. A recorded-file reader is
        # explicitly injected; a URL/device path never causes acquisition.
        if self.endpoint not in {"synthetic://fixture", "owner://readonly", "recorded://local"}:
            raise ValueError("REAL_ENDPOINT_FORBIDDEN")
        if self.namespace != NAMESPACE or type(self.domain_id) is not int or not 1 <= self.domain_id <= 200:
            raise ValueError("ISOLATION_CONFIG_INVALID")


def require_local_ros(config: RuntimeConfig, *, environ=None, proc_root=Path("/proc/net")):
    """Local socket table only; never probe a robot, ROS graph or DDS participant.

    Call before ROS init/launch. This is a best-effort collision check, not a
    reservation. The caller must also supply a private network namespace when
    stronger isolation is required. No environment variable is changed here.
    """
    env = os.environ if environ is None else environ
    if (config.mode != "isolated_ros" or env.get("ROS_LOCALHOST_ONLY") != "1"
            or env.get("ROS_DOMAIN_ID") != str(config.domain_id)
            or env.get("RMW_IMPLEMENTATION") != "rmw_fastrtps_cpp"):
        raise ValueError("EXPLICIT_LOCAL_ROS_REQUIRED")
    if any(env.get(k) for k in ("ROS_DISCOVERY_SERVER", "FASTRTPS_DEFAULT_PROFILES_FILE",
                               "FASTDDS_DEFAULT_PROFILES_FILE", "CYCLONEDDS_URI")):
        raise ValueError("EXTERNAL_DDS_CONFIG_FORBIDDEN")
    base = 7400 + 250 * config.domain_id
    for name in ("udp", "udp6"):
        path = proc_root / name
        if not path.is_file():
            raise ValueError("LOCAL_DOMAIN_CHECK_UNAVAILABLE")
        for line in path.read_text().splitlines()[1:]:
            columns = line.split()
            if len(columns) > 1 and base <= int(columns[1].rsplit(":", 1)[1], 16) < base + 250:
                raise ValueError("LOCAL_DOMAIN_ALREADY_IN_USE")
    return {"domain_id": config.domain_id, "localhost_only": True,
            "local_socket_check": "PASS", "graph_discovery": "NOT_RUN"}
