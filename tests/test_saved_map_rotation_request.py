import unittest

from pydantic import ValidationError

from robot_dashboard.api.models import SavedMapEditedCopyRequest


class SavedMapRotationRequestTests(unittest.TestCase):
    def test_arbitrary_rotation_can_create_a_copy_without_brush_runs(self):
        request = SavedMapEditedCopyRequest(
            name="rotated_map",
            source_revision="a" * 64,
            runs=[],
            rotation_degrees=27.5,
        )
        self.assertEqual(request.rotation_degrees, 27.5)
        self.assertEqual(request.runs, [])

    def test_noop_and_out_of_range_rotations_are_rejected(self):
        base = {"name": "rotated_map", "source_revision": "a" * 64, "runs": []}
        for value in (0.0, -180.1, 180.1, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                SavedMapEditedCopyRequest(**base, rotation_degrees=value)

    def test_brush_only_request_remains_backward_compatible(self):
        request = SavedMapEditedCopyRequest(
            name="brushed_map",
            source_revision="b" * 64,
            runs=[{"start": 0, "length": 1, "value": 100}],
        )
        self.assertEqual(request.rotation_degrees, 0.0)


if __name__ == "__main__":
    unittest.main()
