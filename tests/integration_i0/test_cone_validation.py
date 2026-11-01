"""Teammate 447d45e9 rejection cases, adapted to the canonical ingress."""

import unittest
from robot_dashboard.expansion_integration.cone_input import (
    SCHEMA,
    MAX_CONES,
    validate_legacy_cones,
    ObstacleValidationError,
)


def cone(identifier=0, x=1.0, y=2.0, n=3, radius_m=0.1, height_m=0.25):
    return {
        "id": identifier,
        "x": x,
        "y": y,
        "n": n,
        "radius_m": radius_m,
        "height_m": height_m,
    }


def payload(**overrides):
    value = {
        "schema_version": SCHEMA,
        "stamp": 10.0,
        "frame": "map",
        "model": {"path": "models/cone.onnx", "sha256_12": "0123456789ab"},
        "health": {"stale": False, "fps": 12.5},
        "cones": [cone()],
    }
    value.update(overrides)
    return value


class LegacyValidationTests(unittest.TestCase):
    def assert_rejected(self, code, **overrides):
        with self.assertRaises(ObstacleValidationError) as caught:
            validate_legacy_cones(payload(**overrides))
        self.assertEqual(caught.exception.code, code)

    def test_non_finite_numbers_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            self.assert_rejected("INVALID_JSON_VALUE", cones=[cone(x=value)])
            self.assert_rejected("INVALID_JSON_VALUE", cones=[cone(y=value)])
            self.assert_rejected("INVALID_JSON_VALUE", cones=[cone(radius_m=value)])
            self.assert_rejected("INVALID_JSON_VALUE", cones=[cone(height_m=value)])
            self.assert_rejected("INVALID_JSON_VALUE", stamp=value)
            self.assert_rejected(
                "INVALID_JSON_VALUE", health={"stale": False, "fps": value}
            )

    def test_booleans_are_not_accepted_as_numbers(self):
        self.assert_rejected("COORDINATE_OUT_OF_RANGE", cones=[cone(x=True)])
        self.assert_rejected("INVALID_OBSERVATION_COUNT", cones=[cone(n=True)])
        self.assert_rejected("INVALID_CONE_ID", cones=[cone(identifier=True)])
        self.assert_rejected("INVALID_STAMP", stamp=True)

    def test_more_than_the_cone_ceiling_is_rejected(self):
        cones = [cone(identifier=index) for index in range(MAX_CONES + 1)]
        self.assert_rejected("CONE_LIMIT", cones=cones)

    def test_cone_list_must_be_a_list(self):
        self.assert_rejected("CONE_LIMIT", cones={"id": 0})

    def test_duplicate_cone_identity_is_rejected(self):
        self.assert_rejected(
            "DUPLICATE_CONE_ID", cones=[cone(identifier=7), cone(identifier=7)]
        )

    def test_coordinates_beyond_the_arena_bound_are_rejected(self):
        self.assert_rejected("COORDINATE_OUT_OF_RANGE", cones=[cone(x=1000.1)])
        self.assert_rejected("COORDINATE_OUT_OF_RANGE", cones=[cone(y=-1000.1)])

    def test_cone_size_outside_the_physical_range_is_rejected(self):
        self.assert_rejected("RADIUS_OUT_OF_RANGE", cones=[cone(radius_m=0.0)])
        self.assert_rejected("RADIUS_OUT_OF_RANGE", cones=[cone(radius_m=2.01)])
        self.assert_rejected("HEIGHT_OUT_OF_RANGE", cones=[cone(height_m=0.0)])
        self.assert_rejected("HEIGHT_OUT_OF_RANGE", cones=[cone(height_m=3.01)])

    def test_unknown_schema_is_rejected(self):
        self.assert_rejected(
            "UNKNOWN_SCHEMA", schema_version="robot-scope.obstacle-map/v2"
        )
        self.assert_rejected("UNKNOWN_SCHEMA", schema_version="")

    def test_invalid_frame_identifiers_are_rejected(self):
        for frame in ("", " map", "map frame", "/", "-map", "a" * 65, "map\n", 7):
            self.assert_rejected("INVALID_FRAME", frame=frame)

    def test_extra_or_missing_payload_keys_are_rejected(self):
        extended = payload()
        extended["unexpected"] = 1
        with self.assertRaises(ObstacleValidationError) as caught:
            validate_legacy_cones(extended)
        self.assertEqual(caught.exception.code, "MALFORMED_PAYLOAD")
        reduced = payload()
        reduced.pop("cones")
        with self.assertRaises(ObstacleValidationError) as caught:
            validate_legacy_cones(reduced)
        self.assertEqual(caught.exception.code, "MALFORMED_PAYLOAD")

    def test_extra_cone_keys_are_rejected(self):
        extended = cone()
        extended["confidence"] = 0.9
        self.assert_rejected("MALFORMED_CONE", cones=[extended])

    def test_model_identity_must_be_a_bounded_path_and_short_digest(self):
        self.assert_rejected("MALFORMED_MODEL", model={"path": "a"})
        self.assert_rejected(
            "INVALID_MODEL_DIGEST", model={"path": "a", "sha256_12": "0123456789AB"}
        )
        self.assert_rejected(
            "INVALID_MODEL_DIGEST", model={"path": "a", "sha256_12": "0123456789ab0"}
        )
        self.assert_rejected(
            "INVALID_MODEL_PATH", model={"path": "a" * 257, "sha256_12": "0123456789ab"}
        )
        self.assert_rejected(
            "INVALID_MODEL_PATH", model={"path": "", "sha256_12": "0123456789ab"}
        )

    def test_health_shape_is_exact_and_stale_must_be_boolean(self):
        self.assert_rejected("MALFORMED_HEALTH", health={"stale": False})
        self.assert_rejected(
            "INVALID_HEALTH_STALE", health={"stale": "false", "fps": 1.0}
        )
        self.assert_rejected("INVALID_HEALTH_STALE", health={"stale": 0, "fps": 1.0})

    def test_non_mapping_payload_is_rejected(self):
        for value in ([], "payload", 7, None):
            with self.assertRaises(ObstacleValidationError) as caught:
                validate_legacy_cones(value)
            self.assertEqual(caught.exception.code, "MALFORMED_PAYLOAD")
