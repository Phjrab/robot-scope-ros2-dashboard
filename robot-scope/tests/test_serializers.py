import unittest
from types import SimpleNamespace as NS

from robot_dashboard.serializers import classify_type, summarize_message


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
        self.assertEqual(result["imu_rpy"], [1.0, 2.0, 3.0])


if __name__ == "__main__":
    unittest.main()

