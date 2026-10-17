"""Compatibility imports for the original offline prototype.

The canonical implementation lives in robot_dashboard.mount_calibration. Keep the
full repository checkout: this shim also supports running ``uvicorn app:app``
from this experiment directory, without a manual PYTHONPATH change.
"""

from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from robot_dashboard.mount_calibration import (  # noqa: E402
    COORDINATE_CONVENTION,
    MAX_DEPTH_M,
    MAX_HEIGHT,
    MAX_JSON_DEPTH,
    MAX_JSON_VALUES,
    MAX_POINTS,
    MAX_SAMPLES,
    MAX_WIDTH,
    MIN_DEPTH_M,
    MIN_POINTS,
    NEIGHBORHOOD_RADIUS,
    SCHEMA_VERSION,
    CalibrationError,
    _validate_sample,
    estimate,
    export_analysis,
)

__all__ = [
    "COORDINATE_CONVENTION", "MAX_DEPTH_M", "MAX_HEIGHT", "MAX_JSON_DEPTH",
    "MAX_JSON_VALUES", "MAX_POINTS", "MAX_SAMPLES", "MAX_WIDTH", "MIN_DEPTH_M",
    "MIN_POINTS", "NEIGHBORHOOD_RADIUS", "SCHEMA_VERSION", "CalibrationError",
    "_validate_sample", "estimate", "export_analysis",
]
