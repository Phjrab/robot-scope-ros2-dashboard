"""Actual solver/full-export incremental lineage, no mocked numerical modules."""

from pathlib import Path
import tempfile
import unittest
import numpy as np
from experiments.expansion_20261029.d1_multimap.generate import fixture
from robot_dashboard.multimap_core import solve, source_key
from robot_dashboard.multimap_core.exporter import export, ExportError
from robot_dashboard.relocalization.experimental_se3 import inverse


class IncrementalTests(unittest.TestCase):
    def test_actual_ab_plus_c_and_shared_root_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources, resolver, truth = fixture(root, count=200)
            paths = {s["map_id"]: resolver(s) for s in sources}

            def resolved(d):
                return paths[d["map_id"]]

            def fuse(selected, T, job):
                proposal = solve(
                    dict(
                        request_id=job,
                        sources=selected,
                        source_pins=selected,
                        anchor_source_key=source_key(selected[0]),
                        mode="seeded",
                        initial_guesses=[
                            dict(
                                target=source_key(selected[0]),
                                source=source_key(selected[1]),
                                T=T.tolist(),
                            )
                        ],
                    ),
                    resolved,
                )
                self.assertEqual(proposal["status"], "SOLVED_CANDIDATE")
                return proposal

            def materialize(proposal, job):
                manifest = export(proposal, 1, resolved, root / job)
                descriptor = dict(
                    map_id=manifest["result_id"],
                    revision=manifest["revision"],
                    sha256=manifest["output_hashes"]["merged.pcd"],
                    frame_id="fused",
                    units="m",
                    asset_role="full_source",
                    provenance=dict(
                        id=manifest["result_id"],
                        parents=[dict(id=k) for k in manifest["root_sources"]],
                    ),
                )
                paths[descriptor["map_id"]] = (
                    root / job / manifest["revision"] / "merged.pcd"
                )
                return descriptor, manifest

            ab, abm = materialize(fuse(sources[:2], truth[1], "ab"), "ab")
            self.assertEqual(abm["point_count"], 400)
            abc, abcm = materialize(fuse([ab, sources[2]], truth[2], "abc"), "abc")
            self.assertEqual(abcm["point_count"], 600)
            self.assertEqual(
                set(abcm["root_sources"]), {source_key(s) for s in sources}
            )
            self.assertTrue(paths[ab["map_id"]].is_file())
            bc, bcm = materialize(
                fuse(sources[1:], inverse(truth[1]) @ truth[2], "bc"), "bc"
            )
            shared = fuse([ab, bc], truth[1], "shared")
            with self.assertRaisesRegex(ExportError, "Duplicate root"):
                export(shared, 1, resolved, root / "shared")
            # A transform disagreement does not bypass the duplicate-root gate.
            shared["T_fused_source"][1]["T"] = np.eye(4).tolist()
            with self.assertRaisesRegex(ExportError, "Duplicate root"):
                export(shared, 1, resolved, root / "shared")
            self.assertFalse((root / "shared").exists())


if __name__ == "__main__":
    unittest.main()
