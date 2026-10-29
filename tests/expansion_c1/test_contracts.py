import unittest
from robot_dashboard.expansion_contracts import (
    ContractError,
    FusionRequest,
    validate_transform,
)
from robot_dashboard.expansion_contracts.fixtures import request, source, obstacle
from robot_dashboard.expansion_contracts.messages import IDENTITY


class ContractsTest(unittest.TestCase):
    def test_roundtrip_pins_and_session_frame_keys(self):
        r = request()
        self.assertEqual(FusionRequest.from_dict(r.to_dict()), r)
        self.assertNotEqual(source(1).key, source(2).key)
        self.assertEqual(obstacle().stamp_ns, "0")

    def test_reject_invalid_transform_path_pin_nan_oversize(self):
        for transform in ([1] * 16, [float("nan")] * 16, [x * 2 for x in IDENTITY]):
            with self.assertRaises(ContractError):
                validate_transform(transform)
        for change in (
            {"path": "/tmp/map.pcd"},
            {"request_id": "../map"},
            {"options": {"voxel_size": float("nan")}},
            {"options": {"shell": "x"}},
            {"source_pins": {}},
            {"correspondences": [{}] * 257},
        ):
            with self.assertRaises(ContractError):
                FusionRequest.from_dict({**request().to_dict(), **change})
