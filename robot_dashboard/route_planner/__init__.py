"""Competition Route Planner domain package.

This package is deliberately free of ROS command and control ownership.  It
produces revision-pinned plans, advisory guidance, and Mission drafts only.
"""

from .catalog import competition_catalog
from .orders import OrderValidationError, normalize_order

__all__ = ["OrderValidationError", "competition_catalog", "normalize_order"]
