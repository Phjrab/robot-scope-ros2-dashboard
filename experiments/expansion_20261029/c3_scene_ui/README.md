# C3 offline scene lab

This directory contains a runtime synthetic reference/packet generator and a dependency-injected fixture host using the repository's **existing** RobotScene3D and official URDF-derived web renderer. It has no ROS, application API, camera, sensor, command, service or remote map connection. Generated points, literal paths, costmaps and risk boxes are SYNTHETIC fixtures; they do not prove Nav2 replanning, ingestion or real collision clearance.

From repository root:

```sh
python3 experiments/expansion_20261029/c3_scene_ui/serve.py --port 4183
```

Open `http://127.0.0.1:4183/experiments/expansion_20261029/c3_scene_ui/fixture.html`. Choose scenarios, move the existing scene camera, toggle layers, inspect objects/risk, pause the browser display or consume the latest pending packet. The top replay button cycles synthetic scenarios; it never changes provenance to LIVE. No generated PCD or map file is saved.

```sh
node tests/expansion_c3/test_consumer.mjs
python3 -m unittest tests.expansion_c3.test_module -v
C3_PLAYWRIGHT=/absolute/path/to/node_modules/playwright \
PLAYWRIGHT_BROWSERS_PATH=/absolute/path/to/browsers \
node tests/expansion_c3/browser.mjs
```

Playwright 1.62.1 and its Chromium are used without changing root package/lockfiles. Install in an isolated environment if unavailable; the exact executed environment and paths are in HANDOFF. `C3_FIXTURE_URL` and `C3_EVIDENCE` can change the loopback test URL/output. The server has to run in a second terminal. Browser output records actual PASS/FAIL, requests, measured packet rate, event-loop/render/interaction timing, post-GC heap sizes and retention bounds. A functional trace stops before stress to bound its size. Screenshots cover dark/light/390px/HiDPI and mismatch UI. These are VM browser measurements, not Jetson performance.

The full mandatory regression commands and unresolved dependency/device checks are in `docs/parallel-expansion-20261029/C3/HANDOFF.md`; future host hooks and the explicit consumer field profile are in `INTEGRATION_POINTS.md` there.

## Round 2: exact producers and actual offline HTTP

The original page still defaults to `SOURCE MODE: FIXTURE`. The actual service
mode is opt-in, uses the same renderer and feature, and has no fixture replay
controls. It shows SYNTHETIC evidence separately from ACTUAL_C1_SERVICE transport.
See `docs/parallel-expansion-20261029/C3/ROUND2.md` for measured results and limits.

Prepare read-only dependencies outside the repository (no merge/cherry-pick):

```sh
git fetch --no-tags origin 54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 c0d266e290a2d29c173d3b83520f8c96efea9447 09b68b692fa4b7ccdea39b1a16e3ff150794e12d
mkdir -p /tmp/c3-round2-deps
git archive 54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 robot_dashboard/expansion_contracts robot_dashboard/expansion_services experiments/expansion_20261029/c1_service_host | tar -x -C /tmp/c3-round2-deps
git archive c0d266e290a2d29c173d3b83520f8c96efea9447 robot_dashboard/obstacle_fusion_core | tar -x -C /tmp/c3-round2-deps
git archive 09b68b692fa4b7ccdea39b1a16e3ff150794e12d robot_dashboard/collision_geometry_core | tar -x -C /tmp/c3-round2-deps
chmod -R a-w /tmp/c3-round2-deps
python3 experiments/expansion_20261029/c3_scene_ui/actual_service.py --deps /tmp/c3-round2-deps --out /tmp/c3-round2-results --port 4184
```

Use repository Python requirements plus `requirements-competition-offline.txt` in
an external venv. No ROS, model weights or robot network is required. The runner
verifies all imported role files against the exact Git blobs before running.
C1's existing `create_test_host`/router/SceneSnapshotService execute unchanged.
Temporary PCDs from that test host are deleted with its temporary directory.

Open `http://127.0.0.1:4184/experiments/expansion_20261029/c3_scene_ui/fixture.html?actual=UNKNOWN_PARTIAL`.
Only the local test bearer constant is used; it is public synthetic test data,
not a product credential. The browser polls only the authenticated snapshot GET.
Each scene freezes its virtual source/host clock intentionally, allowing repeated
HTTP reads to expose accidental TTL renewal. C3 still advances local elapsed age.
`EXPIRED` has a server clock already 2 seconds past receipt.

In another shell with Playwright/Chromium installed externally:

```sh
node tests/expansion_c3/test_consumer.mjs
node tests/expansion_c3/test_canonical.mjs
C3_EVIDENCE=/tmp/c3-round2-results node tests/expansion_c3/actual_browser.mjs
# C3_PLAYWRIGHT may name the external playwright package;
# PLAYWRIGHT_BROWSERS_PATH may select its external browser cache.
```

`actual_browser.mjs` audits GET-only loopback traffic, hashes the exact endpoint
response bytes and connects those hashes to six displayed cases and screenshots.
`NEAR` is a test scenario name: the pinned D3 producer returns UNKNOWN with a
positive distance, not a NEAR enum. `PREDICTED_CONTACT` displays the producer's
PREDICTED_COLLISION reason as modeled contact; physical contact is unconfirmed.
The sole CLEAR case is explicitly COMPLETE_SYNTHETIC for a limited body-box
model and the supplied one-second path, not real free-space evidence.

The runner is test wiring, not a proposed universal producer schema. C1 generic
`robot_pose.data`, `global_path.data` and `costmap_snapshot.data` accept dictionaries
but define no geometry sub-schema. Here those supplied synthetic payloads use
existing C3 metre/radian fields; `robot_pose.data.joint_state` animates the visual
URDF only. Raw synthetic LiDAR points/origin are passed into actual D2 and retained
in its `input_sources`; C3 uses them only when explicitly supplied. No reference
cloud, merged map, local trajectory, drawable D3 envelopes or native costmap data
is invented. Large data has no canonical bulk resolver in this C1 SHA; C3 does not
fetch arbitrary references. Immutable slot sequence/epoch revisions reuse bounded
normalized geometry; stale rendering never reparses incoming JSON each frame.

The raw D3 interval fails the pinned C1 validator. The runner records that failure
and retains the original interval in `freshness.original_validity_interval` while
applying an explicit SYNTHETIC identity source-to-host clock correspondence.
It also projects D3's full obstacle reference to the exact two-key reference C1
snapshot requires. This conversion does not establish real host-clock alignment.
`parseC1SceneJSON` preserves canonical integer ns tokens as decimal strings before
JS Number conversion; already-rounded unsafe Numbers are rejected. C1's Python
validator still consumes canonical integers, not a new string-valued wire version.

Round 1's bootstrap-only compatibility scripts have been updated: run
`c1_compatibility.py` on an actual endpoint JSON using the pinned C1 PYTHONPATH,
and `check_c1.mjs <response.json> <trusted-context.json>` for the consumer. The
original fixture browser checks remain in `browser.mjs`; the old optional
bootstrap check is replaced by the stronger actual HTTP suite above.
