"""Full dashboard fixture. ROS, process, and motion boundaries are SYNTHETIC.

Launch with uvicorn --lifespan off so production lifecycle hooks never run.
"""
import tempfile
from pathlib import Path
from types import SimpleNamespace

from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
from robot_dashboard.navigation_jobs import SAFE_TUNED_PARAMETERS
from robot_dashboard.saved_maps import SavedMapCatalog
from test_manual_navigation_api import (
    SyntheticAgent,
    SyntheticJobs,
    SyntheticMapping,
    load_synthetic_dashboard,
)


dashboard = load_synthetic_dashboard()
app = dashboard.app
runtime = dashboard.RUNTIME
temporary = tempfile.TemporaryDirectory(prefix="robot-scope-manual-navigation-test-")
root = Path(temporary.name)
(root / "synthetic-floor.pgm").write_bytes(b"P5\n30 30\n255\n" + bytes([255]) * 900)
(root / "synthetic-floor.yaml").write_text(
    "image: synthetic-floor.pgm\nresolution: 0.2\norigin: [-1, -2, 0.35]\n"
    "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n",
    encoding="utf-8",
)

runtime.saved_maps = SavedMapCatalog([root], managed_roots=[root])
runtime.agent = SyntheticAgent()
runtime.mapping = SyntheticMapping()
runtime.mapping.job_id = None
runtime.competition = SimpleNamespace(require_manual_mode=lambda: None)


class BrowserJobs(SyntheticJobs):
    def parameters_snapshot(self):
        return {"revision": self.parameters_revision, "values": dict(SAFE_TUNED_PARAMETERS)}


jobs = BrowserJobs()
runtime.navigation = NavigationCoordinator(
    runtime.agent, jobs, runtime.mapping, runtime.saved_maps,
    coordination_lock=runtime.pipeline_coordination_lock,
    require_lifecycle_idle=lambda: None,
    ready_timeout_s=0.5, localization_timeout_s=0.5, poll_interval_s=0.01,
)


@app.get("/test/manual-navigation")
def synthetic_motion_readback():
    return {
        "actions": runtime.agent.actions,
        "job_events": jobs.events,
        "mapping_events": runtime.mapping.events,
        "seed_count": sum(
            isinstance(event, tuple) and event[0] == "initial_pose"
            for event in runtime.agent.events
        ),
        "cancellations": [
            event[1] for event in runtime.agent.events
            if isinstance(event, tuple) and event[0] == "cancel"
        ],
    }
