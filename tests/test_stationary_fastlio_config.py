import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StationaryFastlioConfigTests(unittest.TestCase):
    def select(self, profile, opt_in, requested=""):
        return subprocess.run(
            ["bash", "-c", 'source "$1"; robot_scope_fastlio_query_config "$2" "$3" "$4"',
             "config-test", str(ROOT / "scripts/select_fastlio_query_config.sh"),
             profile, opt_in, requested], capture_output=True, text=True, check=False,
        )

    def test_onboard_dense_opt_in_and_normal_config(self):
        for opt, expected in [("1", "fastlio_xt16_d2_relocalization.yaml"),
                              ("0", "fastlio_xt16.yaml"), ("", "fastlio_xt16.yaml")]:
            with self.subTest(opt=opt):
                result = self.select("go2-onboard", opt)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout.strip(), expected)
        self.assertEqual(self.select("go2-onboard", "1", "fastlio_xt16_d2_relocalization.yaml").returncode, 0)

    def test_conflicting_config_invalid_opt_in_and_unlisted_path_reject(self):
        for opt, requested in [("1", "fastlio_xt16.yaml"), ("2", ""), ("0", "../../other.yaml")]:
            with self.subTest(opt=opt, requested=requested):
                result = self.select("go2-onboard", opt, requested)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_other_profiles_preserve_explicit_config_selection(self):
        for profile in ("go2-xt16-wired", "go2-xt16-wireless-competition-fastlio"):
            self.assertEqual(self.select(profile, "1").stdout.strip(), "fastlio_xt16.yaml")
            self.assertEqual(self.select(profile, "1", "fastlio_xt16_d2_relocalization.yaml").stdout.strip(),
                             "fastlio_xt16_d2_relocalization.yaml")
