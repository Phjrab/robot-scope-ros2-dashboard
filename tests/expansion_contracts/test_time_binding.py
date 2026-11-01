import copy
import unittest
from robot_dashboard.expansion_contracts import (
    CollisionAssessment,
    ContractError,
    ObstacleFrame,
)
from robot_dashboard.expansion_contracts.fixtures import obstacle
from robot_dashboard.expansion_contracts.time_binding import (
    ClockBinding,
    normalize_collision_assessment,
    upgrade_observation,
)


def assessment():
    o = obstacle().to_dict()
    keys = (
        "schema_version",
        "evidence_kind",
        "producer",
        "sequence",
        "source_epoch",
        "frame_key",
        "stamp_ns",
        "clock_domain",
        "host_clock_id",
        "received_monotonic_ns",
        "map_binding",
    )
    return dict(
        **{k: o[k] for k in keys},
        robot_pose_ref=None,
        joint_state_ref=None,
        robot_geometry_hash=None,
        obstacle_frame_ref=copy.deepcopy(o),
        path_ref=None,
        padded_envelope=None,
        unpadded_envelope=None,
        min_clearance=1.0,
        predicted_overlap=False,
        modeled_ttc=None,
        freshness={"coverage": "PARTIAL"},
        validity_interval={
            "clock_domain": "fixture-clock",
            "from_ns": "100",
            "until_ns": "200",
        },
        reason="UNKNOWN",
        severity="UNKNOWN",
        recommendation="ADVISORY_ONLY",
    )


class TimeBindingTests(unittest.TestCase):
    def setUp(self):
        self.binding = ClockBinding(
            "fixture-clock",
            "fixture-epoch",
            "test-host",
            2**53,
            2,
            "explicit-synthetic",
        )

    def test_lossless_conservative_conversion_preserves_evidence(self):
        raw = assessment()
        out = normalize_collision_assessment(raw, binding=self.binding)
        self.assertEqual(
            out["validity_interval"]["start_monotonic_ns"], str(2**53 + 102)
        )
        self.assertEqual(out["validity_interval"]["end_monotonic_ns"], str(2**53 + 198))
        self.assertEqual(
            out["obstacle_frame_ref"], upgrade_observation(raw["obstacle_frame_ref"])
        )
        self.assertEqual(
            out["freshness"]["time_conversion"]["original_interval"],
            raw["validity_interval"],
        )
        self.assertEqual(out["severity"], "UNKNOWN")
        self.assertEqual(out["freshness"]["coverage"], "PARTIAL")
        self.assertEqual(normalize_collision_assessment(out), out)
        CollisionAssessment.from_dict(out)

    def test_wrong_clock_epoch_host_aliases_and_ttl_fail_closed(self):
        for patch in (
            {"clock_domain": "other"},
            {"source_epoch": "restart"},
            {"host_clock_id": "browser"},
        ):
            with self.subTest(patch=patch), self.assertRaises(ContractError):
                normalize_collision_assessment(
                    {**assessment(), **patch}, binding=self.binding
                )
        with self.assertRaises(ContractError):
            normalize_collision_assessment(assessment())
        for interval in (
            {
                "clock_domain": "fixture-clock",
                "from_ns": "100",
                "until_ns": "999999999",
            },
            {"clock_domain": "fixture-clock", "from_ns": "200", "until_ns": "100"},
            {**assessment()["validity_interval"], "valid_until_ns": "200"},
        ):
            with self.subTest(interval=interval), self.assertRaises(ContractError):
                normalize_collision_assessment(
                    {**assessment(), "validity_interval": interval},
                    binding=self.binding,
                )

    def test_unknown_interval_and_decimal_types(self):
        raw = assessment()
        raw["validity_interval"] = {}
        self.assertEqual(normalize_collision_assessment(raw)["validity_interval"], {})
        o = obstacle().to_dict()
        o["received_monotonic_ns"] = 2**53 + 1
        v2 = upgrade_observation(o)
        self.assertEqual(v2["received_monotonic_ns"], "9007199254740993")
        ObstacleFrame.from_dict(v2)
        with self.assertRaises(ContractError):
            ObstacleFrame.from_dict({**v2, "received_monotonic_ns": 2**53 + 1})
