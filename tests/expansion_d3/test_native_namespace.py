"""Pure configuration regression: no ROS graph, Docker or socket access."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NativeNamespaceTests(unittest.TestCase):
    def test_review_namespace_allowed_production_still_rejected(self):
        import subprocess

        # Isolate legacy module names (core/configure/fixtures) in a subprocess.
        script = r"""
import sys
sys.path.insert(0,sys.argv[1])
from configure import candidate,validate_config
from fixtures import cases
f=cases()[0]
c=candidate('rpp','baseline',f)
assert not validate_config(c,'rpp',f['footprint'])
c['global_costmap']['global_costmap']['ros__parameters']['static_layer']['map_topic']='/robot_scope/production_map'
assert any('/robot_scope' in x for x in validate_config(c,'rpp',f['footprint']))
"""
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            # Copy ONLY legacy files needed by config import into this temporary
            # fixture; apply the SAME explicit namespace/guard adaptation.
            for name in ("core.py", "configure.py", "fixtures.py"):
                text = (
                    (ROOT / "experiments/competition_nav2" / name)
                    .read_text()
                    .replace("c3_nav2", "robot_scope_review_x")
                )
                if name == "configure.py":
                    text = text.replace(
                        "text = json.dumps(cfg)",
                        'text = json.dumps(cfg).replace("/robot_scope_review_x/", "/c3_nav2/")',
                    )
                (destination / name).write_text(text)
            # fixtures.REPO normally derives from its path; trusted test adjusts
            # only configuration file lookup, not any params or validator rules.
            script = script.replace(
                "f=cases()[0]",
                "import configure\nconfigure.REPO=__import__('pathlib').Path(sys.argv[2])\nf=cases()[0]",
            )
            subprocess.run(
                [sys.executable, "-c", script, str(destination), str(ROOT)], check=True
            )


if __name__ == "__main__":
    unittest.main()
