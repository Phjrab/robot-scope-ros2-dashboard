"""Process-isolated import of the unchanged D0 sensor; no native command producer."""

import json
from pathlib import Path
import sys

fixture_path = Path(sys.argv[1])
sys.path.insert(0, str(fixture_path.parent.parent))
import export_fixtures as d0  # noqa: E402

scene = json.loads(fixture_path.read_text())
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    observation = d0.observe(scene, request["pose"], request["stamp_s"])
    print(json.dumps(observation, allow_nan=False), flush=True)
