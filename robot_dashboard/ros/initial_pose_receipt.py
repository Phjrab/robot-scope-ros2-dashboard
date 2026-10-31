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
