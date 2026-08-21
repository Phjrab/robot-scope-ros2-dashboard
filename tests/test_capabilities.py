import unittest

from robot_dashboard.capabilities import (
    CAPABILITY_NAMES,
    CAPABILITY_PROFILES,
    UnknownCapability,
    UnknownCapabilityProfile,
    capabilities_for_robot_type,
    capability_profile_id,
    supports_capability,
)


class MobileRobotCapabilityTests(unittest.TestCase):
    def test_fixed_vocabulary_and_strict_boolean_declarations(self):
        self.assertEqual(
            CAPABILITY_NAMES,
            (
                "observability",
                "camera",
                "pointcloud",
                "mapping",
                "localization",
                "navigation",
                "manual_control",
                "autonomous_control",
            ),
        )
        for declaration in CAPABILITY_PROFILES.values():
            self.assertEqual(tuple(declaration), CAPABILITY_NAMES)
            self.assertTrue(all(type(value) is bool for value in declaration.values()))

    def test_go2_is_the_full_reference_profile(self):
        self.assertEqual(
            capabilities_for_robot_type("go2"),
            {name: True for name in CAPABILITY_NAMES},
        )

    def test_turtlebot_and_generic_declare_observation_support_only(self):
        expected = {
            "observability": True,
            "camera": True,
            "pointcloud": True,
            "mapping": False,
            "localization": False,
            "navigation": False,
            "manual_control": False,
            "autonomous_control": False,
        }
        self.assertEqual(capabilities_for_robot_type("turtlebot"), expected)
        self.assertEqual(capabilities_for_robot_type("generic"), expected)
        self.assertEqual(capabilities_for_robot_type(""), expected)
        self.assertEqual(capability_profile_id("turtlebot3"), "turtlebot")

    def test_callers_receive_copies_and_cannot_mutate_authority(self):
        first = capabilities_for_robot_type("go2")
        first["manual_control"] = False
        self.assertTrue(capabilities_for_robot_type("go2")["manual_control"])
        with self.assertRaises(TypeError):
            CAPABILITY_PROFILES["go2"]["manual_control"] = False

    def test_unknown_profiles_and_capabilities_fail_closed(self):
        with self.assertRaises(UnknownCapabilityProfile):
            capabilities_for_robot_type("so-101")
        with self.assertRaises(UnknownCapability):
            supports_capability("go2", "arbitrary_plugin")
        self.assertTrue(supports_capability("go2", "navigation"))
        self.assertFalse(supports_capability("turtlebot", "navigation"))


if __name__ == "__main__":
    unittest.main()
