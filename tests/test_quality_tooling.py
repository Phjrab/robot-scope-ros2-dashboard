import ast
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QualityToolingTests(unittest.TestCase):
    def test_quality_requirements_are_exact_and_ros_independent(self):
        requirements = (ROOT / "requirements-quality.txt").read_text(encoding="utf-8")
        self.assertIn("coverage[toml]==7.6.4", requirements)
        self.assertIn("mypy==1.13.0", requirements)
        self.assertIn("pip-audit==2.7.3", requirements)
        self.assertIn("ruff==0.6.9", requirements)
        dependency_lines = [
            line.casefold()
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertFalse(any("rclpy" in line for line in dependency_lines))

    def test_static_configs_pin_python_310_and_incremental_scope(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        mypy = (ROOT / "mypy.ini").read_text(encoding="utf-8")
        self.assertIn('target-version = "py310"', pyproject)
        self.assertIn('select = ["E4", "E7", "E9", "F"]', pyproject)
        self.assertIn("python_version = 3.10", mypy)
        self.assertIn("robot_dashboard/public_diagnostics.py", mypy)
        self.assertIn("strict = True", mypy)

    def test_ci_runs_quality_security_coverage_and_all_frontend_syntax(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        for command in (
            "python -m ruff check robot_dashboard scripts",
            "python -m mypy --config-file mypy.ini",
            "python scripts/check_repository_secrets.py",
            "python -m pip_audit -r requirements.txt",
            "python -m coverage run -m unittest discover -s tests -v",
            "node scripts/check_frontend_syntax.mjs",
        ):
            self.assertIn(command, workflow)

    def test_secret_scan_passes_without_revealing_scanned_values(self):
        completed = subprocess.run(
            [sys.executable, "scripts/check_repository_secrets.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("secret scan passed", completed.stdout)

    def test_secret_scan_reports_a_rule_not_the_matched_value(self):
        script = ROOT / "scripts" / "check_repository_secrets.py"
        spec = importlib.util.spec_from_file_location("secret_scan", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            fixture = temporary_root / "fixture.py"
            fake_value = "AKIA" + "0" * 16
            fixture.write_text(f"credential = '{fake_value}'\n", encoding="utf-8")
            module.ROOT = temporary_root
            module._tracked_paths = lambda: [fixture]
            self.assertEqual(
                module.find_secret_like_values(),
                [("aws-access-key", "fixture.py", 1)],
            )

    def test_saved_map_json_encoder_is_defined_before_route_use(self):
        tree = ast.parse((ROOT / "robot_dashboard" / "app.py").read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        route = functions["saved_map_data"]
        names = {
            node.id
            for node in ast.walk(route)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        self.assertIn("_encode_json", functions)
        self.assertIn("_encode_json", names)


if __name__ == "__main__":
    unittest.main()
