#!/usr/bin/env python3
"""Send the minimum authenticated Go2 IMU envelope over the fixed Wi-Fi peer."""

from __future__ import annotations

import math
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from wireless_imu_protocol import (
    ConnectedImuDatagram,
    ImuEnvelope,
    MAX_COUNTER,
    WirelessImuError,
    encode_envelope,
    load_private_key,
    read_boot_id,
    system_clock_synchronized,
)


REPORT_INTERVAL_S = 5.0


@dataclass(frozen=True)
class LowStateImu:
    quaternion_wxyz: tuple[float, float, float, float]
    gyroscope_xyz: tuple[float, float, float]
    accelerometer_xyz: tuple[float, float, float]
    source_tick: int | None


def _fixed_finite(value: object, length: int) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise WirelessImuError("nonfinite")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WirelessImuError("nonfinite") from exc
    if len(result) != length or not all(math.isfinite(item) for item in result):
        raise WirelessImuError("nonfinite")
    return result


def extract_lowstate_imu(message: Any) -> LowStateImu:
    """Extract only the minimum fixed IMU fields from one LowState message."""

    try:
        imu_state = message.imu_state
        quaternion = _fixed_finite(imu_state.quaternion, 4)
        gyroscope = _fixed_finite(imu_state.gyroscope, 3)
        accelerometer = _fixed_finite(imu_state.accelerometer, 3)
    except AttributeError as exc:
        raise WirelessImuError("nonfinite") from exc

    source_tick: int | None = None
    for owner, field_name in ((message, "tick"), (imu_state, "timestamp")):
        candidate = getattr(owner, field_name, None)
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            if 0 <= candidate <= 0xFFFFFFFFFFFFFFFF:
                source_tick = candidate
                break
    return LowStateImu(
        quaternion_wxyz=quaternion,  # type: ignore[arg-type]
        gyroscope_xyz=gyroscope,  # type: ignore[arg-type]
        accelerometer_xyz=accelerometer,  # type: ignore[arg-type]
        source_tick=source_tick,
    )


def _increment(value: int, amount: int = 1) -> int:
    return min(MAX_COUNTER, value + max(0, amount))


def main() -> int:
    if os.geteuid() == 0:
        raise SystemExit("wireless IMU sender refuses to run as root")

    try:
        import rclpy  # type: ignore[import-not-found]
        from rclpy.node import Node  # type: ignore[import-not-found]
        from rclpy.qos import (  # type: ignore[import-not-found]
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
        from unitree_go.msg import LowState  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError) as exc:
        raise SystemExit("ROS 2 Foxy or unitree_go messages are unavailable") from exc

    key = load_private_key()
    boot_id = read_boot_id()
    transport = ConnectedImuDatagram("sender")

    class WirelessImuSender(Node):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__("robot_scope_wireless_imu_sender")
            input_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._sequence = max(1, time.monotonic_ns())
            self._input_ready = False
            self._received = 0
            self._sent = 0
            self._invalid = 0
            self._send_errors = 0
            self._clock_blocks = 0
            self.create_subscription(
                LowState, "/lowstate", self._handle_lowstate, input_qos
            )
            self.create_timer(1.0, self._update_graph_state)
            self.create_timer(REPORT_INTERVAL_S, self._report)

        def _update_graph_state(self) -> None:
            self._input_ready = self.count_publishers("/lowstate") == 1

        def _handle_lowstate(self, message: Any) -> None:
            self._received = _increment(self._received)
            if not self._input_ready:
                return
            if not system_clock_synchronized():
                self._clock_blocks = _increment(self._clock_blocks)
                return
            try:
                values = extract_lowstate_imu(message)
                realtime_ns = time.time_ns()
                monotonic_ns = time.monotonic_ns()
                self._sequence = min(0xFFFFFFFFFFFFFFFF, self._sequence + 1)
                sample = ImuEnvelope(
                    boot_id=boot_id,
                    sequence=self._sequence,
                    realtime_ns=realtime_ns,
                    monotonic_ns=monotonic_ns,
                    source_tick=values.source_tick,
                    quaternion_wxyz=values.quaternion_wxyz,
                    gyroscope_xyz=values.gyroscope_xyz,
                    accelerometer_xyz=values.accelerometer_xyz,
                )
                transport.send(encode_envelope(sample, key))
                self._sent = _increment(self._sent)
            except WirelessImuError:
                self._invalid = _increment(self._invalid)
            except OSError:
                self._send_errors = _increment(self._send_errors)

        def _report(self) -> None:
            self.get_logger().info(
                "wireless_imu_sender "
                f"input_ready={str(self._input_ready).lower()} "
                f"clock_synchronized={str(system_clock_synchronized()).lower()} "
                f"received={self._received} sent={self._sent} "
                f"invalid={self._invalid} send_errors={self._send_errors} "
                f"clock_blocks={self._clock_blocks}"
            )

    rclpy.init(args=None)
    node = WirelessImuSender()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        transport.close()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
