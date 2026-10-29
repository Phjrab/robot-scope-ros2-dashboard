# Current owner compatibility continuation

Use this directory in addition to the historical `../round2` profile, in a
separate interpreter. No owner code is copied into this branch. From repository
root, fetch only the exact SHAs in `dependencies.py`, then export read-only:

```sh
export C4_LATEST_DEP_ROOT=/tmp/c4-followup-deps
python -m experiments.expansion_20261029.c4_runtime.followup.dependencies
export C4_LATEST_REQUIRED=1
export C4_NODE=/absolute/path/to/node-24
PYTHONPATH=tests:. python -m unittest expansion_runtime.latest_cases -v
python -m experiments.expansion_20261029.c4_runtime.followup.report \
  --node "$C4_NODE" \
  --output experiments/expansion_20261029/c4_runtime/followup/composition.json
```

The report deliberately exits **2**: the actual current C3 adapter rejects the
canonical C1 **0.2** HTTP bytes. The regression assertion confirms that rejection;
it is not an end-to-end integration PASS. Explicit safe-integer 0.1 projection
is separately reported as partial display only (objects PASS; command collision
UNAVAILABLE because actual pose/joints/global-path references were not supplied).

For the unfiltered full suite also set the historical `C4_ROUND2_DEP_ROOT` and
`C4_ROUND2_REQUIRED=1` per `../round2/README.md`. `test_latest.py` launches the
current 15 tests in another interpreter, avoiding mixed-SHA module caches. Both
profiles are required in the recorded local run; ordinary CI without exports
visibly skips them. The CI workflow is unchanged.

The recorded environment uses the existing temporary Python 3.12 venv, Node
24.22.1 and `../offline_test_guard.py` as `sitecustomize.py` on `PYTHONPATH`.
This blocks external connects, binds, DNS and datagram sends; ASGI uses no TCP
server. A local elevated test process was necessary for asyncio self-pipe
wakeups blocked in the restricted sandbox. No robot/device endpoints are used.

Current host integration is explicit:

```python
from robot_dashboard.expansion_runtime.canonical_ports import CanonicalCorePorts
ports = CanonicalCorePorts.from_installed(geometry)
# Construct Runtime with trusted context/mapping, then process an InputFramePacket.
# C1 service must explicitly use schema_version="0.2".
snapshot = ports.ingest_scene(service, result)
# Only a host explicitly selecting C1's supported safe 0.1 profile may request:
# snapshot = ports.ingest_scene(legacy_service, result, legacy_profile=True)
```

The existing `CorePorts` remains the prior exact-SHA 0.1 profile. There is no
automatic detection or fallback between profiles. D3 receives the generator's
volume certificate in `SyntheticCoverage.evidence`; C4 cannot create real
observed-free coverage. D2 compaction removes duplicate provenance only and
rejects oversized delivery at the unchanged C1 16 KiB limit. The full obstacle
frame remains available for actual collision assessment.
