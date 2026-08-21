"""Fixed product capability declarations for supported mobile robot profiles.

Capabilities describe Robot Scope product support, not transient runtime
readiness.  They are intentionally code-owned and closed: configuration files,
ROS graph data, and browser input cannot grant a capability.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Dict, Mapping


CAPABILITY_NAMES = (
    "observability",
    "camera",
    "pointcloud",
    "mapping",
    "localization",
    "navigation",
    "manual_control",
    "autonomous_control",
)


class UnknownCapabilityProfile(ValueError):
    """Raised when no fixed capability declaration exists for a profile."""


class UnknownCapability(ValueError):
    """Raised when callers ask for a capability outside the fixed vocabulary."""


def _validated(values: Mapping[str, bool]) -> Mapping[str, bool]:
    if set(values) != set(CAPABILITY_NAMES):
        raise RuntimeError("capability declaration must contain the exact fixed vocabulary")
    if any(type(values[name]) is not bool for name in CAPABILITY_NAMES):
        raise RuntimeError("capability declarations must use strict booleans")
    return MappingProxyType({name: values[name] for name in CAPABILITY_NAMES})


_OBSERVATION_ONLY = {
    "observability": True,
    "camera": True,
    "pointcloud": True,
    "mapping": False,
    "localization": False,
    "navigation": False,
    "manual_control": False,
    "autonomous_control": False,
}


CAPABILITY_PROFILES: Mapping[str, Mapping[str, bool]] = MappingProxyType(
    {
        "go2": _validated({name: True for name in CAPABILITY_NAMES}),
        "turtlebot": _validated(_OBSERVATION_ONLY),
        "generic": _validated(_OBSERVATION_ONLY),
    }
)


def capability_profile_id(robot_type: str | None) -> str:
    """Normalize startup/selection identifiers to a fixed capability profile."""

    key = str(robot_type or "").strip().lower().replace("_", "-")
    aliases = {"": "generic", "turtlebot3": "turtlebot"}
    key = aliases.get(key, key)
    if key not in CAPABILITY_PROFILES:
        raise UnknownCapabilityProfile("지원하지 않는 capability profile입니다.")
    return key


def capabilities_for_robot_type(robot_type: str | None) -> Dict[str, bool]:
    """Return a JSON-safe copy of the fixed declaration for *robot_type*."""

    return dict(CAPABILITY_PROFILES[capability_profile_id(robot_type)])


def supports_capability(robot_type: str | None, capability: str) -> bool:
    name = str(capability).strip().lower()
    if name not in CAPABILITY_NAMES:
        raise UnknownCapability("지원하지 않는 capability입니다.")
    return CAPABILITY_PROFILES[capability_profile_id(robot_type)][name]
