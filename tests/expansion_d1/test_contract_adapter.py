"""Set D1_C1_EXPORT to an exact-SHA read-only C1 export for compatibility."""

import importlib
import os
import sys
import tempfile
import unittest
import numpy as np
from robot_dashboard.multimap_core.contract_adapter import (
    to_core_request,
    proposal_to_contract,
)
from robot_dashboard.multimap_core.solver import solve
from experiments.expansion_20261029.d1_multimap.generate import fixture


@unittest.skipUnless(
    os.environ.get("D1_C1_EXPORT"), "C1 exact-SHA dependency export not supplied"
)
class ContractAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.environ["D1_C1_EXPORT"])
        cls.messages = importlib.import_module("expansion_contracts.messages")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sources, resolver, self.truth = fixture(self.tmp.name, count=100)
        self.paths = {}
        self.sources = []
        for i, source in enumerate(sources[:2], 1):
            self.paths[f"{i:024x}"] = resolver(source)
            s = dict(
                source,
                schema_version="0.1",
                evidence_kind="SYNTHETIC",
                producer="d1-test",
                sequence=0,
                source_epoch="test-epoch",
                map_id=f"{i:024x}",
                revision=f"{i:064x}",
                mapping_session_id=None,
                gravity_or_plane=None,
                point_count=100,
                point_schema=[
                    dict(name=n, size=4, type="F", count=1)
                    for n in (
                        "x",
                        "y",
                        "z",
                        "normal_x",
                        "normal_y",
                        "normal_z",
                        "intensity",
                    )
                ],
                acquisition={"origin": "generated"},
            )
            self.sources.append(self.messages.MapSourceDescriptor.from_dict(s))
        self.request = self.messages.FusionRequest(
            schema_version="0.1",
            evidence_kind="SYNTHETIC",
            producer="d1-test",
            sequence=3,
            source_epoch="test-epoch",
            request_id="request-3",
            anchor_source_key=self.sources[0].key,
            sources=[s.to_dict() for s in self.sources],
            source_pins={s.key: s.sha256 for s in self.sources},
            mode="seeded",
            options={"voxel_size": 0.05},
            correspondences=[],
            initial_guesses=[
                dict(
                    source_key=self.sources[1].key,
                    T_anchor_source=self.truth[1].reshape(16).tolist(),
                )
            ],
        )

    def test_real_validator_round_trip(self):
        request = to_core_request(self.request, job_id="a" * 24, proposal_revision=7)
        result = solve(request, lambda d: self.paths[d["map_id"]])
        wire = proposal_to_contract(result, self.request, self.messages.FusionProposal)
        validated = self.messages.FusionProposal.from_dict(wire.to_dict())
        self.assertEqual(validated.state, "SOLVED_CANDIDATE")
        self.assertEqual(validated.proposal_revision, 7)
        self.assertEqual(validated.sequence, 3)
        self.assertEqual(validated.source_epoch, "test-epoch")
        self.assertEqual(validated.input_pins, self.request.source_pins)
        np.testing.assert_allclose(
            np.array(validated.T_fused_source[self.sources[1].key]).reshape(4, 4),
            self.truth[1],
            atol=0.005,
        )

    def test_budget_options_explicitly_rejected(self):
        for option in ("max_iterations", "max_runtime_s"):
            value = self.request.to_dict()
            value["options"][option] = 10
            request = self.messages.FusionRequest.from_dict(value)
            with self.assertRaisesRegex(ValueError, "worker budget"):
                to_core_request(request, job_id="a" * 24)

    def test_correspondences_reverse_for_later_anchor(self):
        value = self.request.to_dict()
        value["anchor_source_key"] = self.sources[1].key
        value["initial_guesses"] = []
        value["correspondences"] = [
            dict(source_key=self.sources[0].key, source_xyz=p, anchor_xyz=p)
            for p in ([0, 0, 0], [1, 0, 0], [0, 1, 0])
        ]
        request = self.messages.FusionRequest.from_dict(value)
        result = to_core_request(request, job_id="a" * 24)
        self.assertTrue(
            result["correspondences"][0]["target"].startswith(self.sources[0].map_id)
        )
