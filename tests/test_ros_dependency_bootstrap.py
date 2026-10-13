import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "ros_dependencies_humble.json"
JAZZY_MANIFEST = ROOT / "config" / "ros_dependencies_jazzy.json"
SCRIPT = ROOT / "scripts" / "bootstrap_ros_dependencies.sh"


class RosDependencyManifestTests(unittest.TestCase):
    def test_manifest_pins_supported_repositories(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["ros_distro"], "humble")
        self.assertEqual(payload["ubuntu_codename"], "jammy")
        self.assertEqual(payload["supported_architectures"], ["x86_64", "aarch64"])
        apt_source = payload["ros_apt_source"]
        self.assertRegex(apt_source["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(apt_source["url"].startswith("https://github.com/ros-infrastructure/"))
        self.assertRegex(apt_source["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            set(payload["repositories"]),
            {
                "unitree_ros2",
                "hesai_ros2",
                "livox_sdk2",
                "livox_ros_driver2",
                "fast_lio",
            },
        )
        for item in payload["repositories"].values():
            self.assertRegex(item["url"], r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git$")
            self.assertRegex(item["commit"], r"^[0-9a-f]{40}$")
            self.assertFalse(Path(item["target"]).is_absolute())
            self.assertNotIn("..", Path(item["target"]).parts)
            self.assertTrue(item["modes"])

    def test_fast_lio_copyleft_is_explicit(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(payload["repositories"]["fast_lio"]["license"], "GPL-2.0-only")

    def test_fast_lio_initializes_the_pinned_ikd_tree_gitlink(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        fast_lio = payload["repositories"]["fast_lio"]
        self.assertTrue(fast_lio["recursive"])
        self.assertEqual(fast_lio["commit"], "2fffc570a25d0df172720bac034fbdb6a13d2162")
        self.assertEqual(fast_lio["submodule_commit"], "e2e3f4e9d3b95a9e66b1ba83dc98d4a05ed8a3c4")

    def test_jazzy_manifest_is_noble_observer_only(self) -> None:
        payload = json.loads(JAZZY_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["ros_distro"], "jazzy")
        self.assertEqual(payload["ubuntu_codename"], "noble")
        self.assertEqual(payload["verified_reference"]["scope"], "observer-runtime")
        self.assertEqual(payload["repositories"], {})
        self.assertIn("ros-jazzy-ros-base", payload["apt_groups"]["ros"])
        self.assertRegex(payload["ros_apt_source"]["sha256"], r"^[0-9a-f]{64}$")

    def test_livox_sdk_precedes_the_ros_driver_in_private_prefix(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        sdk = payload["repositories"]["livox_sdk2"]
        self.assertEqual(sdk["license"], "MIT")
        self.assertEqual(
            sdk["commit"], "08f523c930b2f0ba1e98a6afaa8d7476bf479908"
        )
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertLess(
            source.index("install_repository livox_sdk2"),
            source.index("install_repository livox_ros_driver2"),
        )
        self.assertIn("CMAKE_INSTALL_PREFIX", source)
        self.assertIn("CMAKE_LIBRARY_PATH", source)
        self.assertIn("CMAKE_INCLUDE_PATH", source)


class RosDependencyBootstrapTests(unittest.TestCase):
    def test_build_jobs_bound_package_and_native_parallelism(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_script("--mode", "go2-nav", "--workspace-root", temporary,
                                     "--build-jobs", "3", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("--parallel-workers 3"), 5)
            self.assertIn("--parallel 3", result.stdout)
            self.assertEqual(result.stdout.count("CMAKE_BUILD_PARALLEL_LEVEL=3"), 5)
            self.assertEqual(result.stdout.count("MAKEFLAGS=-j3"), 5)
            self.assertFalse((Path(temporary) / "unitree_ros2").exists())

    def test_build_jobs_rejects_unbounded_and_shell_values_before_work(self) -> None:
        for value in ("0", "17", "-1", "2;id", "all", "1.5", "02"):
            with self.subTest(value=value):
                result = self.run_script("--mode", "go2", "--build-jobs", value)
                self.assertEqual(result.returncode, 2)
                self.assertIn("integer from 1 to 16", result.stderr)
                self.assertNotIn("git clone", result.stdout)

    def run_script(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["LC_ALL"] = "C"
        return subprocess.run(
            ["bash", str(SCRIPT), *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_observer_dry_run_has_no_clone(self) -> None:
        result = self.run_script("--mode", "observer", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no vendor source dependencies", result.stdout)
        self.assertNotIn("git clone", result.stdout)

    def test_observer_apply_does_not_require_vendor_build_tools(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        observer_exit = source.index('if [[ "$MODE" == "observer" ]]')
        build_tool_checks = source.index('command -v colcon')
        self.assertLess(observer_exit, build_tool_checks)

    def test_jazzy_manifest_allows_observer_but_rejects_vendor_modes(self) -> None:
        observer = self.run_script(
            "--mode", "observer", "--manifest", str(JAZZY_MANIFEST), "--dry-run"
        )
        self.assertEqual(observer.returncode, 0, observer.stderr)
        self.assertIn("no vendor source dependencies", observer.stdout)

        go2 = self.run_script(
            "--mode", "go2", "--manifest", str(JAZZY_MANIFEST), "--dry-run"
        )
        self.assertEqual(go2.returncode, 2)
        self.assertIn("supported only with ROS 2 Humble", go2.stderr)

    def test_colcon_setup_files_are_sourced_without_nounset(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        function_body = source[
            source.index("run_with_setups() {") : source.index(
                'install_repository unitree_ros2'
            )
        ]
        disable_nounset = function_body.index("set +u")
        source_setup = function_body.index('source "$1"')
        restore_nounset = function_body.index("set -u", source_setup)
        self.assertLess(disable_nounset, source_setup)
        self.assertLess(source_setup, restore_nounset)

    def test_full_dry_run_uses_all_pinned_commits_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspaces"
            result = self.run_script(
                "--mode",
                "go2-nav",
                "--workspace-root",
                str(root),
                "--dry-run",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(root.exists())
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            for item in manifest["repositories"].values():
                self.assertIn(item["url"], result.stdout)
                self.assertIn(item["commit"], result.stdout)
            self.assertIn("colcon build --symlink-install", result.stdout)
            self.assertIn("robot_scope_xt16_bridge", result.stdout)
            self.assertIn("xt16_bridge_ws", result.stdout)
            self.assertIn("Livox-SDK2", result.stdout)
            self.assertIn("sdk2_install", result.stdout)
            self.assertIn("cmake --install", result.stdout)
            self.assertIn("prepare_livox_ros2_source.py", result.stdout)
            self.assertIn("-DROS_EDITION=ROS2 -DDISTRO_ROS=humble", result.stdout)
            self.assertNotIn("build.sh humble", result.stdout)

    def test_unknown_mode_fails_without_side_effects(self) -> None:
        result = self.run_script("--mode", "everything", "--dry-run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unsupported mode", result.stderr)

    def test_xt16_rejects_workspace_paths_upstream_build_script_cannot_quote(self) -> None:
        result = self.run_script(
            "--mode",
            "go2-xt16",
            "--workspace-root",
            "/tmp/robot scope workspaces",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot contain whitespace", result.stderr)

    def test_private_livox_sdk_prefix_override_is_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            prefix = Path(temporary) / "private-sdk"
            environment = dict(os.environ)
            environment["LC_ALL"] = "C"
            environment["ROBOT_SCOPE_LIVOX_SDK_PREFIX"] = str(prefix)
            result = subprocess.run(
                [
                    "bash",
                    str(SCRIPT),
                    "--mode",
                    "go2-xt16",
                    "--workspace-root",
                    str(workspace),
                    "--dry-run",
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(prefix), result.stdout)
            self.assertFalse(prefix.exists())

    def test_dangling_repository_symlink_fails_without_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            target = workspace / "unitree_ros2"
            missing = workspace / "missing-unitree-workspace"
            target.symlink_to(missing)

            result = self.run_script(
                "--mode",
                "go2",
                "--workspace-root",
                str(workspace),
                "--dry-run",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("target is a dangling symbolic link", result.stderr)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.readlink(), missing)
            self.assertFalse(missing.exists())

    def test_script_uses_no_reset_or_force_checkout(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"git[^\n]*(?:reset|clean)")
        self.assertNotIn("checkout --force", source)
        self.assertIn("--untracked-files=no", source)


class ExistingPinnedSubmoduleTests(unittest.TestCase):
    """Exercise the source verifier against real, isolated local repositories."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = dict(os.environ, GIT_ALLOW_PROTOCOL="file", LC_ALL="C")
        self.dependency = self.root / "dependency"
        self.parent = self.root / "parent"
        self.target = self.root / "target"
        for path in (self.dependency, self.parent):
            self.git("init", "--quiet", str(path))
            self.git("-C", str(path), "config", "user.name", "Bootstrap fixture")
            self.git("-C", str(path), "config", "user.email", "fixture@example.invalid")
        (self.dependency / "ikd_Tree.cpp").write_text("pinned source\n", encoding="utf-8")
        self.git("-C", str(self.dependency), "add", "ikd_Tree.cpp")
        self.git("-C", str(self.dependency), "commit", "--quiet", "-m", "pinned dependency")
        self.dependency_commit = self.git("-C", str(self.dependency), "rev-parse", "HEAD").stdout.strip()
        self.git("-C", str(self.parent), "submodule", "add", "--quiet", str(self.dependency), "include/ikd-Tree")
        self.git("-C", str(self.parent), "commit", "--quiet", "-am", "pinned parent")
        self.parent_commit = self.git("-C", str(self.parent), "rev-parse", "HEAD").stdout.strip()
        self.git("clone", "--quiet", str(self.parent), str(self.target))
        source = SCRIPT.read_text(encoding="utf-8")
        self.verifier = source[source.index("verify_existing_repository() {"):source.index("install_repository() {")]

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *arguments], env=self.environment, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def verify(self) -> subprocess.CompletedProcess[str]:
        script = 'set -euo pipefail\ndie() { echo "$*" >&2; exit 2; }\nrun() { "$@"; }\n' + self.verifier
        script += '\nverify_existing_repository "$1" "$2" "$3" "$4" "$5"\n'
        return subprocess.run(["bash", "-c", script, "bootstrap-fixture", "fast_lio",
                               str(self.parent), self.parent_commit, str(self.target), "1"],
                              env=self.environment, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)

    def test_nonrecursive_existing_clone_initializes_only_missing_gitlink(self) -> None:
        before = self.git("-C", str(self.target), "submodule", "status", "--recursive").stdout
        self.assertTrue(before.startswith("-"))
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("initializing missing pinned submodules", result.stdout)
        actual = self.git("-C", str(self.target / "include/ikd-Tree"), "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(actual, self.dependency_commit)
        self.assertEqual(self.git("-C", str(self.target), "rev-parse", "HEAD").stdout.strip(), self.parent_commit)
        self.assertEqual(self.git("-C", str(self.target), "status", "--porcelain=v1").stdout, "")
        again = self.verify()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("initializing", again.stdout)

    def test_existing_mismatched_submodule_is_not_reset(self) -> None:
        self.assertEqual(self.verify().returncode, 0)
        child = self.target / "include/ikd-Tree"
        self.git("-C", str(child), "config", "user.name", "Bootstrap fixture")
        self.git("-C", str(child), "config", "user.email", "fixture@example.invalid")
        (child / "ikd_Tree.cpp").write_text("local different commit\n", encoding="utf-8")
        self.git("-C", str(child), "commit", "--quiet", "-am", "retain different commit")
        changed = self.git("-C", str(child), "rev-parse", "HEAD").stdout
        result = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.git("-C", str(child), "rev-parse", "HEAD").stdout, changed)
        self.assertEqual((child / "ikd_Tree.cpp").read_text(), "local different commit\n")

    def test_submodule_tracked_edits_are_refused_even_when_git_config_ignores_them(self) -> None:
        self.assertEqual(self.verify().returncode, 0)
        child = self.target / "include/ikd-Tree"
        (child / "ikd_Tree.cpp").write_text("retain local edits\n", encoding="utf-8")
        self.git("-C", str(self.target), "config", "submodule.include/ikd-Tree.ignore", "all")
        result = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertIn("tracked local modifications", result.stderr)
        self.assertEqual((child / "ikd_Tree.cpp").read_text(), "retain local edits\n")

    def test_wrong_parent_pin_fails_before_initialization(self) -> None:
        self.parent_commit = "f" * 40
        result = self.verify()
        self.assertEqual(result.returncode, 2)
        self.assertIn("no automatic reset", result.stderr)
        self.assertTrue(self.git("-C", str(self.target), "submodule", "status").stdout.startswith("-"))


if __name__ == "__main__":
    unittest.main()
