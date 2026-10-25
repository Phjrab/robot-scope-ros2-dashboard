"""Read pinned Git objects into a temporary test overlay, never into the checkout.

No fetch/install/network happens in tests. Set C2_CROSS_REQUIRED=1 to make a
missing exact dependency a failure rather than an explicitly reported NOT_RUN.
"""
from contextlib import contextmanager
import importlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest

C1_SHA = "765622ecbe20dd29b40296dd2ad24fa508ac9443"
C4_SHA = "380800ca9e211495769fe60ee8221e3f4fb40f16"
ROOT = Path(__file__).resolve().parents[2]


def blob(sha, path):
    result = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=ROOT, capture_output=True)
    if result.returncode:
        message = f"NOT_RUN: fetch pinned dependency {sha} ({path}) before cross tests"
        if os.environ.get("C2_CROSS_REQUIRED") == "1":
            raise RuntimeError(message)
        raise unittest.SkipTest(message)
    return result.stdout


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


@contextmanager
def pinned_dependencies():
    saved = set(sys.modules)
    native = "robot_dashboard.mission_routes.competition_native"
    previous_ingress = sys.modules.get(native + ".ingress")
    with tempfile.TemporaryDirectory(prefix="c2-round3-readonly-") as directory:
        root = Path(directory)
        for name in ("config", "projection", "pipeline", "frames"):
            (root / f"{name}.py").write_bytes(blob(C4_SHA, f"robot_dashboard/competition_traffic/{name}.py"))
        for name, path in {
            "c1_coordinator": "robot_dashboard/application/mission_coordinator.py",
            "c1_session": "robot_dashboard/mission_routes/competition_native/session.py",
            "c1_ingress": "robot_dashboard/mission_routes/competition_native/ingress.py",
        }.items():
            (root / f"{name}.py").write_bytes(blob(C1_SHA, path))
        package = ModuleType("_c2_round3_c4")
        package.__path__ = [str(root)]
        sys.modules[package.__name__] = package
        try:
            projection = importlib.import_module(package.__name__ + ".projection")
            coordinator = module("_c2_round3_c1", root / "c1_coordinator.py")
            module(native + ".ingress", root / "c1_ingress.py")
            session = module(native + "._round3_session", root / "c1_session.py")
            yield SimpleNamespace(projection=projection.signal_fragment, coordinator=coordinator,
                                  gate=session.SessionGate, c4_package=package.__name__)
        finally:
            if previous_ingress is None:
                sys.modules.pop(native + ".ingress", None)
            else:
                sys.modules[native + ".ingress"] = previous_ingress
            for name in set(sys.modules) - saved:
                if name.startswith(("_c2_round3_", native + "._round3_")):
                    sys.modules.pop(name, None)
