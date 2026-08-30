import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Wp08ReleaseContractTests(unittest.TestCase):
    def test_release_cli_has_no_update_install_activation_or_service_action(self):
        source = (ROOT / "scripts" / "robot_scope_release.py").read_text(encoding="utf-8")
        for command in ("validate-manifest", "build", "verify"):
            self.assertIn(f'add_parser("{command}")', source)
        for command in ("update-all", "git-pull", "install", "activate", "restart", "rebuild"):
            self.assertNotIn(f'add_parser("{command}")', source)

    def test_runbook_preserves_safety_runtime_and_private_artifacts(self):
        source = (ROOT / "docs" / "WP08_RELEASE_LOCK_ROLLBACK_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        for invariant in (
            "not a physical stop",
            "does not grant motion authority",
            "Closing the browser is not finalize or robot stop",
            "Preserve",
            "Dataset",
            "maps",
            "model registry",
            "private logs",
            "do not ARM or enable AUTO",
        ):
            self.assertIn(invariant, source)

    def test_runbook_covers_every_locked_release_mutation_and_field_stage(self):
        source = (ROOT / "docs" / "WP08_RELEASE_LOCK_ROLLBACK_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        for mutation in (
            "Git pull/source update",
            "Python/Node/system package install",
            "Model activation/rollback",
            "Engine rebuild",
            "Robot network target",
            "Camera profile",
            "PointCloud RAW/limit",
            "Service topology",
            "AUTO speed/timeout",
        ):
            self.assertIn(mutation, source)
        for stage in range(1, 14):
            self.assertIn(f"{stage}.", source)
        for evidence in (
            "internet removed",
            "laptop-browser disconnect",
            "model rollback",
            "cold boot",
            "soak",
            "storage reserve",
            "field-checklist dry run",
        ):
            self.assertIn(evidence, source)


if __name__ == "__main__":
    unittest.main()
