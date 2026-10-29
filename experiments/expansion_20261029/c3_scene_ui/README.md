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
