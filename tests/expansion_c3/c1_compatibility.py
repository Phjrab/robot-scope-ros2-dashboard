"""Validate a real C1 snapshot using the externally pinned canonical validator.

Usage: PYTHONPATH=<C1 git archive export> python c1_compatibility.py
       endpoint-response.json validated-wire.json
Round 1's bootstrap-only sources.display fixture is superseded by actual_service.py.
"""
import json
from pathlib import Path
import sys
from robot_dashboard.expansion_contracts import ScenePacket

raw = json.loads(Path(sys.argv[1]).read_text())
validated = ScenePacket.from_dict(raw).to_dict()
Path(sys.argv[2]).write_text(json.dumps(validated, indent=2) + "\n")
print("PASS C1 canonical ScenePacket.from_dict; not native ROS evidence")
