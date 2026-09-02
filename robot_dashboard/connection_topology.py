"""Fixed dashboard connection topology derived from an allowlisted profile."""

from __future__ import annotations


ONBOARD_GATEWAY_TOPOLOGY = "onboard_gateway"
DIRECT_ROBOT_TOPOLOGY = "direct_robot"
WIRELESS_GO2_PROFILES = frozenset(
    {
        "go2-xt16-wireless",
        "go2-xt16-wireless-competition-fastlio",
    }
)


def connection_topology_for(robot_type: str, mapping_profile: str) -> str:
    """Return the immutable network boundary for the running dashboard."""

    if (
        str(robot_type).strip().casefold() == "go2"
        and str(mapping_profile).strip() in WIRELESS_GO2_PROFILES
    ):
        return ONBOARD_GATEWAY_TOPOLOGY
    return DIRECT_ROBOT_TOPOLOGY


__all__ = [
    "DIRECT_ROBOT_TOPOLOGY",
    "ONBOARD_GATEWAY_TOPOLOGY",
    "WIRELESS_GO2_PROFILES",
    "connection_topology_for",
]
