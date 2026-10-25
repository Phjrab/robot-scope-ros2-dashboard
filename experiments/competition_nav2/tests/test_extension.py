# ruff: noqa: E402
"""Negative chronology tests and preservation of the already executed baseline."""

import copy
import json
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from configure import candidate
from fixtures import diagnostic_cases, extension_cases, reference_feasibility, digest
from observations import grid_payload, replan_evidence, grid_values
from rpp_contract import manifest
from run_extension import ORDER


class ExtensionTests(unittest.TestCase):
    def evidence(self):
        fixture = dict(
            obstacles=[dict(appears_s=3.0, polygon=[[2, 2], [3, 2], [3, 3], [2, 3]])],
            goal=[4, 2.5, 0],
        )

        def cm(t, occupied):
            data = [0] * 25
            data[12] = occupied
            return dict(
                kind="costmap",
                frame="map",
                width=5,
                height=5,
                resolution=1.0,
                origin=[0, 0],
                source_sim_s=t,
                source_elapsed_s=t,
                data_zlib_base64=grid_payload(data),
            )

        events = [
            dict(kind="appearance", elapsed_s=3.0),
            cm(2, 0),
            cm(3.5, 100),
            dict(
                kind="path",
                frame="map",
                source_sim_s=2,
                source_elapsed_s=2,
                points=[[1, 2.5], [4, 2.5]],
            ),
            dict(
                kind="path",
                frame="map",
                source_sim_s=4,
                source_elapsed_s=4,
                points=[[1, 2.5], [1, 1], [4, 1], [4, 2.5]],
            ),
        ]
        ranges = [8.0] * 360
        ranges[180] = 1.1
        scan = dict(
            source_pose=[1, 2.5, 0],
            ranges=ranges,
            source_sim_s=3.1,
            source_elapsed_s=3.1,
            sim_t=3.2,
        )
        return fixture, events, [scan]

    def test_observed_causal_chain_and_detour(self):
        result = replan_evidence(*self.evidence())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["first_scan_hit_beams"], 1)
        self.assertEqual(result["first_detour_path_elapsed_s"], 4)

    def test_costmap_only_injection_cannot_claim_sensor_replan(self):
        f, e, s = self.evidence()
        s[0]["ranges"] = [8.0] * 360
        self.assertIn(
            "virtual scan first hit absent", replan_evidence(f, e, s)["errors"]
        )

    def test_unchanged_native_path_rejected(self):
        f, e, s = self.evidence()
        e[-1]["points"] = copy.deepcopy(e[-2]["points"])
        self.assertIn(
            "no subsequent native detour path", replan_evidence(f, e, s)["errors"]
        )

    def test_costmap_before_scan_rejected(self):
        f, e, s = self.evidence()
        s[0].update(source_sim_s=3.6, source_elapsed_s=3.6)
        self.assertIn(
            "costmap precedes sensor observation", replan_evidence(f, e, s)["errors"]
        )

    def test_corrupt_map_dimensions_rejected(self):
        _, e, _ = self.evidence()
        e[1]["width"] = 6
        with self.assertRaises(ValueError):
            grid_values(e[1])

    def test_baseline_and_extension_policy_preserved(self):
        baseline = diagnostic_cases()[0]
        baseline["map_sha256"] = (
            "faa47a95e1be2ebf3400918df2c2f717a68c8294b2b49aa365f4baba754c620f"
        )
        self.assertEqual(
            digest(baseline),
            "631f19f08a426f4ba91666fadea3b38488580259fabde589b8532854a7ba873a",
        )
        for fixture in extension_cases():
            for key in (
                "start",
                "goal",
                "footprint",
                "timeout_s",
                "parking_allowed",
                "resolution_m",
                "sensor_period_s",
                "sensor_delay_s",
                "pose_source",
                "world_kind",
            ):
                self.assertEqual(fixture[key], baseline[key])
            self.assertEqual(reference_feasibility(fixture)["status"], "PASS")
        self.assertEqual(
            [s for _, s, _ in ORDER[:3]], ["diagnostic_single_obstacle"] * 3
        )

    def test_config_matches_executed_rpp_and_contract_is_sim_only(self):
        preserved = yaml.safe_load((ROOT / "repro/rpp-native-params.yaml").read_text())
        generated = candidate("rpp")
        for node, fields in (
            ("map_server", ["yaml_filename"]),
            (
                "bt_navigator",
                ["default_nav_to_pose_bt_xml", "default_nav_through_poses_bt_xml"],
            ),
        ):
            for field in fields:
                preserved[node]["ros__parameters"].pop(field)
        self.assertEqual(generated, preserved)
        contract = manifest()
        self.assertEqual(contract["pose_source"], "SIM_GT")
        self.assertFalse(contract["live_import_allowed"])
        self.assertEqual(contract["runtime"]["network"], "none")
        lock = json.loads((ROOT / "repro/image-lock.json").read_text())
        self.assertEqual(
            lock["packages_sha256"],
            "45f626571f4fd5388d7bc174cae017e5482a4c2396254a5adfb461342076a5de",
        )


if __name__ == "__main__":
    unittest.main()
