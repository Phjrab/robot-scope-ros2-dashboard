import copy
import tempfile
import threading
import unittest
import numpy as np
from experiments.expansion_20261029.d1_multimap.generate import fixture, write_cloud
from robot_dashboard.multimap_core.solver import solve, source_key, optimize_graph, pair
from robot_dashboard.relocalization.experimental_se3 import inverse, transform_points


class SolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sources, self.resolver, self.truth = fixture(self.tmp.name)

    def request(self, seeded=True, n=2):
        s = self.sources[:n]
        k = [source_key(d) for d in s]
        return dict(
            request_id="test",
            sources=s,
            source_pins=s,
            anchor_source_key=k[0],
            mode="seeded" if seeded else "auto",
            initial_guesses=(
                [
                    dict(
                        target=k[i],
                        source=k[j],
                        T=(inverse(self.truth[i]) @ self.truth[j]).tolist(),
                    )
                    for i in range(n)
                    for j in range(i + 1, n)
                ]
                if seeded
                else []
            ),
        )

    def test_seeded_and_inverse(self):
        p = solve(self.request(), self.resolver)
        self.assertEqual(p["status"], "SOLVED_CANDIDATE")
        T = np.array(p["T_fused_source"][1]["T"])
        np.testing.assert_allclose(T, self.truth[1], atol=0.005)
        q = np.array([[0.1, 2, 3]])
        np.testing.assert_allclose(
            transform_points(inverse(T), transform_points(T, q)), q
        )

    def test_auto(self):
        p = solve(self.request(False), self.resolver)
        self.assertEqual(p["status"], "SOLVED_CANDIDATE")
        np.testing.assert_allclose(
            p["T_fused_source"][1]["T"], self.truth[1], atol=0.005
        )

    def test_three_and_anchor_change(self):
        r = self.request(n=3)
        p = solve(r, self.resolver)
        self.assertEqual(p["status"], "SOLVED_CANDIDATE")
        self.assertEqual(len(p["pairwise_edges"]), 3)
        r["anchor_source_key"] = source_key(self.sources[2])
        r["proposal_revision"] = 2
        p = solve(r, self.resolver)
        for e in p["T_fused_source"]:
            i = [source_key(d) for d in self.sources].index(e["source_key"])
            np.testing.assert_allclose(
                e["T"], inverse(self.truth[2]) @ self.truth[i], atol=0.008
            )
        self.assertEqual(p["proposal_revision"], 2)

    def test_partial_chain(self):
        self.sources, self.resolver, self.truth = fixture(
            self.tmp.name, 1200, partial=True
        )
        p = solve(self.request(n=3), self.resolver)
        self.assertEqual(p["status"], "SOLVED_CANDIDATE")

    def test_bad_loop(self):
        keys = ["a", "b", "c"]
        identity = np.eye(4).tolist()
        edges = [
            dict(
                target="a",
                source="b",
                T=identity,
                metrics=dict(overlap_source=1, overlap_target=1),
            ),
            dict(
                target="b",
                source="c",
                T=identity,
                metrics=dict(overlap_source=0.9, overlap_target=0.9),
            ),
        ]
        bad = np.eye(4)
        bad[0, 3] = 4
        edges.append(
            dict(
                target="a",
                source="c",
                T=bad.tolist(),
                metrics=dict(overlap_source=0.5, overlap_target=0.5),
            )
        )
        poses, _, rejected = optimize_graph(keys, edges, "a", 0.05)
        self.assertEqual(len(rejected), 1)
        np.testing.assert_allclose(poses["c"], np.eye(4))

    def test_plane_wrong_seed_and_no_overlap(self):
        rng = np.random.default_rng(7)
        p = np.c_[rng.uniform(-3, 3, (300, 2)), np.zeros(300)]
        _, _, accepted, _ = pair(p, p, [np.eye(4)], 0.05, lambda: False)
        self.assertFalse(accepted)
        r = self.request()
        r["initial_guesses"][0]["T"][0][3] = 100
        self.assertEqual(solve(r, self.resolver)["status"], "DISCONNECTED")
        a = rng.uniform(-2, 2, (300, 3))
        b = rng.uniform(-20, 20, (300, 3))
        self.assertFalse(pair(a, b, [], 0.05, lambda: False)[2])

    def test_symmetry_ambiguity(self):
        rng = np.random.default_rng(9)
        q = rng.normal(size=(100, 3))
        q[:, 0] *= 4
        a = np.concatenate([q, q @ np.diag([-1, -1, 1])])
        _, _, accepted, alternatives = pair(a, a, [], 0.03, lambda: False)
        self.assertFalse(accepted)
        self.assertTrue(alternatives)

    def test_hash_units_and_pins(self):
        for field, value in [("sha256", "bad"), ("units", "mm")]:
            r = self.request()
            r["sources"][0][field] = value
            with self.assertRaises(ValueError):
                solve(r, self.resolver)
            self.sources, self.resolver, self.truth = fixture(self.tmp.name)
        r = self.request()
        r["source_pins"] = copy.deepcopy(r["sources"])
        r["source_pins"][0]["revision"] = "other"
        with self.assertRaises(ValueError):
            solve(r, self.resolver)

    def test_cancel_and_correspondences(self):
        token = threading.Event()
        token.set()
        self.assertEqual(
            solve(self.request(), self.resolver, cancel_token=token)["status"],
            "CANCELED",
        )
        r = self.request()
        r["correspondences"] = [
            dict(
                target=source_key(self.sources[0]),
                source=source_key(self.sources[1]),
                source_points=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
                target_points=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
            )
        ]
        with self.assertRaises(ValueError):
            solve(r, self.resolver)


if __name__ == "__main__":
    unittest.main()
