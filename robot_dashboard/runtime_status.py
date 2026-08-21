"""Small, side-effect-free runtime status helpers."""

from __future__ import annotations

import os
import re
from typing import Mapping, Optional


_DDS_MODES = {"automatic", "go2_interface", "offline_viewer", "unknown"}
_INTERFACE_PATTERN = re.compile(r"[A-Za-z0-9_.:@-]{1,64}")


def _optional_bool(value: object) -> Optional[bool]:
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def ros_transport_status(
    environ: Mapping[str, str] | None = None,
    *,
    require_go2_interface: bool = False,
) -> dict[str, object]:
    """Return public ROS/DDS startup diagnostics without exposing the DDS URI."""

    values = os.environ if environ is None else environ
    dds_uri_configured = bool(values.get("CYCLONEDDS_URI"))
    cyclonedds_configured = (
        str(values.get("RMW_IMPLEMENTATION", "")).strip().casefold()
        == "rmw_cyclonedds_cpp"
    )
    mode = str(values.get("ROBOT_SCOPE_DDS_MODE", "unknown")).strip().casefold()
    if mode not in _DDS_MODES:
        mode = "unknown"

    interface = str(values.get("ROBOT_SCOPE_DDS_INTERFACE", "")).strip()
    if not _INTERFACE_PATTERN.fullmatch(interface):
        interface = ""

    interface_ready = _optional_bool(values.get("ROBOT_SCOPE_DDS_INTERFACE_READY"))
    if mode == "go2_interface":
        # A marker alone cannot prove a valid Go2 transport.  Both settings
        # are required by this project's Humble setup.
        interface_ready = interface_ready is not False and dds_uri_configured and cyclonedds_configured
    elif mode == "offline_viewer":
        interface_ready = False
    elif require_go2_interface:
        # Direct launches predating the wrapper markers are still diagnosable.
        # Do not apply this inference to Generic/TurtleBot profiles.
        interface_ready = dds_uri_configured and cyclonedds_configured
        mode = "go2_interface" if interface_ready else "offline_viewer"

    return {
        "mode": mode,
        "interface_ready": interface_ready,
        "interface": interface,
        "offline_viewer": mode == "offline_viewer" or (
            require_go2_interface and interface_ready is False
        ),
        "dds_uri_configured": dds_uri_configured,
        "cyclonedds_configured": cyclonedds_configured,
        "dedicated_interface_required": bool(require_go2_interface),
    }
