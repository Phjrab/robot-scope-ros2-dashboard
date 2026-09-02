import math
import unittest
from types import SimpleNamespace as NS

from robot_dashboard.serializers import (
    GO2_JOINT_ORDER,
    classify_type,
    extract_go2_battery,
    extract_odometry_pose,
    extract_go2_imu_rpy,
    extract_go2_joint_positions,
    go2_joint_state_payload,
    odometry_pose_payload,
    summarize_message,
)


class SerializerTests(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(classify_type("sensor_msgs/msg/PointCloud2"), "pointcloud")
        self.assertEqual(classify_type("nav_msgs/msg/Odometry"), "odometry")
        self.assertEqual(classify_type("unitree_go/msg/Go2FrontVideoData"), "camera")

    def test_lowstate_is_bounded(self):
        message = NS(
            imu_state=NS(rpy=[1.0, 2.0, 3.0], gyroscope=[0.1] * 3, accelerometer=[9.8, 0, 0], temperature=42),
            bms_state=NS(soc=83, current=-1200),
            power_v=29.4,
            power_a=1.2,
            foot_force=[1, 2, 3, 4],
            motor_state=[NS(temperature=35, q=0.25) for _ in range(20)],
            error_code=0,
        )
        result = summarize_message(message, "unitree_go/msg/LowState")
        self.assertEqual(result["battery_soc"], 83)
        self.assertEqual(len(result["motor_position_rad"]), 12)
        self.assertEqual(result["motor_joint_order"], list(GO2_JOINT_ORDER))
        self.assertEqual(result["imu_rpy"], [1.0, 2.0, 3.0])

    def test_lowstate_battery_projection_is_finite_bounded_and_type_scoped(self):
        message = NS(
            bms_state=NS(soc=83, current=-1200),
            power_v=29.4567,
            power_a=1.2345,
        )
        self.assertEqual(
            extract_go2_battery(message, "unitree_go/msg/LowState"),
            {
                "battery_soc": 83,
                "battery_current_ma": -1200,
                "power_v": 29.457,
                "power_a": 1.234,
            },
        )
        self.assertEqual(
            extract_go2_battery(message, "sensor_msgs/msg/BatteryState"),
            {},
        )

        invalid = NS(
            bms_state=NS(soc=101, current=math.inf),
            power_v=-0.1,
            power_a=True,
        )
        self.assertEqual(
            extract_go2_battery(invalid, "unitree_go/msg/LowState"),
            {},
        )

    def test_lowstate_joint_positions_use_unitree_order_and_urdf_limits(self):
        raw = [0.1, 0.8, -1.6, -0.2, 0.9, -1.7, 0.3, 0.7, -1.8, -0.4, 0.6, -1.9]
        result = extract_go2_joint_positions(
            NS(motor_state=[NS(q=value) for value in raw] + [NS(q=99.0)] * 8),
            "unitree_go/msg/LowState",
        )
        self.assertEqual(result, raw)

        clamped = extract_go2_joint_positions(
            NS(motor_state=[NS(q=100.0) for _ in range(20)]),
            "unitree_go/msg/LowState",
        )
        self.assertEqual(clamped[0], 1.0472)
        self.assertEqual(clamped[1], 3.4907)
        self.assertEqual(clamped[2], -0.83776)

    def test_lowstate_joint_positions_reject_incomplete_or_nonfinite_samples(self):
        self.assertIsNone(
            extract_go2_joint_positions(
                NS(motor_state=[NS(q=0.0) for _ in range(11)]),
                "unitree_go/msg/LowState",
            )
        )
        values = [NS(q=0.0) for _ in range(20)]
        values[4].q = math.nan
        self.assertIsNone(extract_go2_joint_positions(NS(motor_state=values), "unitree_go/msg/LowState"))

    def test_joint_state_is_name_matched_and_reordered(self):
        by_name = {
            name: (0.1 if "hip" in name else 0.8 if "thigh" in name else -1.5)
            for name in GO2_JOINT_ORDER
        }
        reversed_names = list(reversed(GO2_JOINT_ORDER))
        message = NS(
            name=["camera_joint"] + [f"go2/{name}" for name in reversed_names],
            position=[9.0] + [by_name[name] for name in reversed_names],
        )
        result = extract_go2_joint_positions(message, "sensor_msgs/msg/JointState")
        self.assertEqual(result, [by_name[name] for name in GO2_JOINT_ORDER])

        incomplete = NS(name=list(GO2_JOINT_ORDER[:-1]), position=[0.0] * 11)
        self.assertIsNone(extract_go2_joint_positions(incomplete, "sensor_msgs/msg/JointState"))

    def test_joint_payload_nulls_waiting_and_stale_positions(self):
        positions = [0.0, 0.75, -1.5] * 4
        fresh = go2_joint_state_payload(
            topic="/lowstate",
            type_name="unitree_go/msg/LowState",
            positions=positions,
            updated_at=10.0,
            now=10.25,
            stale_after_s=1.0,
            seq=4,
            source_order="unitree_lowstate",
            imu_rpy_rad=[0.1, -0.2, 0.3],
        )
        self.assertEqual(fresh["state"], "ok")
        self.assertEqual(fresh["position_rad"], positions)
        self.assertEqual(fresh["order"], list(GO2_JOINT_ORDER))
        self.assertEqual(len(fresh["position_rad"]), 12)
        self.assertEqual(fresh["imu_rpy_rad"], [0.1, -0.2, 0.3])

        stale = go2_joint_state_payload(
            topic="/lowstate",
            type_name="unitree_go/msg/LowState",
            positions=positions,
            updated_at=10.0,
            now=11.01,
            stale_after_s=1.0,
            imu_rpy_rad=[0.1, -0.2, 0.3],
        )
        self.assertEqual(stale["state"], "stale")
        self.assertIsNone(stale["position_rad"])
        self.assertIsNone(stale["imu_rpy_rad"])

        waiting = go2_joint_state_payload(
            topic="/lowstate",
            type_name="unitree_go/msg/LowState",
            positions=None,
            updated_at=0.0,
            now=11.0,
            stale_after_s=1.0,
        )
        self.assertEqual(waiting["state"], "waiting")
        self.assertIsNone(waiting["position_rad"])
        self.assertIsNone(waiting["imu_rpy_rad"])

    def test_lowstate_imu_rpy_requires_exactly_three_finite_values(self):
        message = NS(imu_state=NS(rpy=[0.1, -0.2, 0.3]))
        self.assertEqual(extract_go2_imu_rpy(message, "unitree_go/msg/LowState"), [0.1, -0.2, 0.3])
        self.assertIsNone(extract_go2_imu_rpy(message, "sensor_msgs/msg/JointState"))
        self.assertIsNone(
            extract_go2_imu_rpy(NS(imu_state=NS(rpy=[0.1, 0.2])), "unitree_go/msg/LowState")
        )
        self.assertIsNone(
            extract_go2_imu_rpy(NS(imu_state=NS(rpy=[0.1, math.inf, 0.3])), "unitree_go/msg/LowState")
        )

    def test_odometry_pose_is_normalized_bounded_and_freshness_aware(self):
        message = NS(
            header=NS(frame_id="camera_init"),
            child_frame_id="body",
            pose=NS(pose=NS(
                position=NS(x=1.25, y=-2.5, z=0.4),
                orientation=NS(x=0.0, y=0.0, z=1.0, w=1.0),
            )),
            twist=NS(twist=NS(
                linear=NS(x=0.2, y=0.0, z=0.0),
                angular=NS(x=0.0, y=0.0, z=0.3),
            )),
        )
        pose = extract_odometry_pose(message, "nav_msgs/msg/Odometry")
        self.assertEqual(pose["frame_id"], "camera_init")
        self.assertEqual(pose["child_frame_id"], "body")
        self.assertAlmostEqual(
            sum(value * value for value in pose["orientation"].values()),
            1.0,
            places=6,
        )
        fresh = odometry_pose_payload(
            topic="/Odometry", type_name="nav_msgs/msg/Odometry", pose=pose,
            updated_at=10.0, now=10.2, stale_after_s=1.0, seq=7,
        )
        self.assertEqual(fresh["state"], "ok")
        self.assertEqual(fresh["position"]["x"], 1.25)
        stale = odometry_pose_payload(
            topic="/Odometry", type_name="nav_msgs/msg/Odometry", pose=pose,
            updated_at=10.0, now=11.1, stale_after_s=1.0, seq=7,
        )
        self.assertEqual(stale["state"], "stale")
        self.assertIsNone(stale["position"])

        message.pose.pose.position.x = 1_000_001.0
        self.assertIsNone(
            extract_odometry_pose(
                message, "nav_msgs/msg/Odometry", position_limit_m=10_000.0
            )
        )


if __name__ == "__main__":
    unittest.main()
