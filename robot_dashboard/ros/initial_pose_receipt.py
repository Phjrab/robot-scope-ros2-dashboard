"""Wait for actual 3D seed application, without treating ROS publish as ACK."""
from __future__ import annotations

import math
import time

from ..control import ControlDisabled


def operational_initial_pose_context(health):
    source = health.get('operational_3d')
    if source is None:
        return None  # Preserve the existing 2D path.
    stopped = source.get('stopped_seconds')
    if (not health.get('fresh') or type(stopped) not in (float, int)
            or not math.isfinite(stopped) or stopped < 2.):
        raise ControlDisabled('RESEED_REQUIRES_OBSERVED_STOP: wait for 2 seconds of measured stop')
    return (health.get('runtime_instance_generation'), source['bundle_generation'])


def wait_initial_pose_receipt(snapshot, context, stamp_ns, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 1.5
    while clock() < deadline:
        health = snapshot(clock())
        source = health.get('operational_3d') or {}
        if (health.get('runtime_instance_generation'), source.get('bundle_generation')) != context:
            raise ControlDisabled('INITIAL_POSE_SOURCE_CHANGED')
        receipt = source.get('initial_pose_receipt') or {}
        if health.get('fresh') and receipt.get('stamp_ns') == str(stamp_ns):
            if receipt.get('accepted') is not True:
                raise ControlDisabled('3D initial pose rejected: ' + str(receipt.get('reason', 'UNKNOWN')))
            if receipt.get('localization_generation') != source.get('localization_generation'):
                raise ControlDisabled('INITIAL_POSE_INVALIDATED_AFTER_APPLY')
            return
        sleep(.025)
    raise ControlDisabled('INITIAL_POSE_APPLICATION_UNCONFIRMED: no matching runtime receipt')


def wait_match_receipt(snapshot, context, request_id, generation, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 1.5
    while clock() < deadline:
        health = snapshot(clock())
        source = health.get('operational_3d') or {}
        if ((health.get('runtime_instance_generation'), source.get('bundle_generation')) != context
                or source.get('localization_generation') != generation):
            raise ControlDisabled('MAP_MATCH_SOURCE_CHANGED')
        receipt = source.get('match_receipt') or {}
        if health.get('fresh') and receipt.get('request_id') == request_id:
            if receipt.get('accepted') is not True:
                raise ControlDisabled('3D map match rejected: ' + str(receipt.get('reason', 'UNKNOWN')))
            if receipt.get('localization_generation') != generation:
                raise ControlDisabled('MAP_MATCH_SOURCE_CHANGED')
            return receipt
        sleep(.025)
    raise ControlDisabled('MAP_MATCH_APPLICATION_UNCONFIRMED: no matching runtime receipt')


def wait_manual_seed_receipt(snapshot, expected_context, stamp_ns, *, clock=time.monotonic, sleep=time.sleep):
    """Confirm the exact runtime seed and its dynamic TF readback."""
    from .manual_navigation import context, stamp_string

    deadline = clock() + 1.5
    while clock() < deadline:
        health = snapshot(clock())
        if context(health) != expected_context:
            raise ControlDisabled("MANUAL_INITIAL_POSE_SOURCE_CHANGED")
        seed = health["manual_seed"]
        receipt = seed.get("receipt") or {}
        if health.get("fresh") and receipt.get("stamp_ns") == str(stamp_ns):
            if receipt.get("accepted") is not True:
                raise ControlDisabled(str(receipt.get("reason", "MANUAL_INITIAL_POSE_REJECTED")))
            if (receipt.get("source_epoch") != seed.get("source_epoch")
                    or receipt.get("seed_generation") != seed.get("seed_generation")):
                raise ControlDisabled("MANUAL_INITIAL_POSE_INVALIDATED")
            if (seed.get("state") == "ready_manual" and seed.get("tf_readback") is True
                    and seed.get("inputs_ready") is True and health.get("ready") is True):
                accepted_at, odom_stamp = (receipt.get(key) for key in ("accepted_ros_ns", "odometry_stamp_ns"))
                tf_stamp = seed.get("tf_readback_stamp_ns")
                if (not stamp_string(accepted_at) or not stamp_string(odom_stamp)
                        or not stamp_string(tf_stamp)
                        or not 0 <= int(accepted_at) - int(stamp_ns) <= 500_000_000
                        or int(odom_stamp) > min(int(accepted_at), int(tf_stamp))):
                    raise ControlDisabled("MANUAL_INITIAL_POSE_RECEIPT_STAMP_INVALID")
                return receipt
        sleep(.025)
    raise ControlDisabled("MANUAL_INITIAL_POSE_APPLICATION_UNCONFIRMED")
