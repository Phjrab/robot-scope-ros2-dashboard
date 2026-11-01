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

## Round 2 continuation: C1 0.2, exact cores and recorded native replay

The default page remains the original fixture. `?actual=UNKNOWN_PARTIAL` selects
actual authenticated C1 HTTP with generated D2/D3 input; `?actual=NATIVE_REPLAY`
selects original D3 hosted native records. Neither mode connects the product or a
robot. Current pins and results: [ROUND2_V02](../../../docs/parallel-expansion-20261029/C3/ROUND2_V02.md).
Historical 0.1 results remain in ROUND2.md and Git; current `actual_service.py`
uses the new pins below and the real owner normalization API.

```sh
git fetch origin 50600c7bce6f5fae743cd836ca1d8ee68d91b05a 203c144f6b4a90966839c34b603ae12ee676cb12 7313f0a31c00ae87ae216b84ca41a23804e91917 356d0a036eb62d546e159e12a0691d7f5ea278f6 47a1d031d797c098c38a0147894523d07d30db8f
python3 experiments/expansion_20261029/c3_scene_ui/prepare_dependencies.py /tmp/c3-next-deps-v2
# Optional exact native artifact (975251 bytes; no local ROS execution):
gh api repos/Phjrab/robot-scope-ros2-dashboard/actions/artifacts/12882393645/zip > /tmp/c3-d3-native-fa8e26e.zip
# Python environment: requirements.txt + requirements-competition-offline.txt.
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 experiments/expansion_20261029/c3_scene_ui/actual_service.py --deps /tmp/c3-next-deps-v2 --out /tmp/c3-next-results --native-zip /tmp/c3-d3-native-fa8e26e.zip --port 4184
```

The exporter requires a new directory and makes every file read-only. The runner
verifies each owner Git blob before importing it. Temporary D1/C1 maps, merged
PCD and manifests are private to TemporaryDirectory and never committed. One
short actual D1 seeded solve -> C1 save/reload supplies the merged map identity
and 160-point display preview of its 800-point result. C2's exact host wiring is
reused read-only; its UI remains frozen. All service limits stay unchanged.

Omit `--native-zip` to run only the six generated-core cases. An unavailable or
expired GitHub artifact is INPUT_REQUIRED; a mismatched hash fails. Never create
a replacement recording and call it this native run. Expected ZIP SHA256:
`0f09cf101555dbef3368fc6913acd9cdd61e380ad45c51472ea5e6b1b3cdc6aa`.

In another shell, after the server reports READY:

```sh
node tests/expansion_c3/test_consumer.mjs
node tests/expansion_c3/test_canonical.mjs
node tests/expansion_c3/test_assets.mjs
C3_NATIVE_REPLAY=1 C3_EVIDENCE=/tmp/c3-next-results node tests/expansion_c3/actual_browser.mjs
# Set C3_PLAYWRIGHT and PLAYWRIGHT_BROWSERS_PATH for the external installation.
# Without native artifact, omit C3_NATIVE_REPLAY=1.
C3_FIXTURE_URL=http://127.0.0.1:4184/experiments/expansion_20261029/c3_scene_ui/fixture.html C3_EVIDENCE=/tmp/c3-next-fixture-results node tests/expansion_c3/browser.mjs
```

Run heavy checks sequentially. Node 24.22.1 / Playwright 1.62.1 / Chromium
151.0.7922.34 were used. Python's mandatory discovery also executes all three
C3 unit files. Remote common CI does not fetch these peer pins or replay the
native artifact: local actual integration and remote regression are separate.

C1 supplies the canonical 0.2 decimal timestamps and fixed authenticated asset
route. D3 `canonical_assessment` calls C1 `normalize_collision_assessment` with
an explicit epoch-bound `ClockBinding`; C3 no longer renames validity keys or
narrows full refs. The six core cases use an explicitly synthetic identity clock
mapping, not measured sensor clock calibration. The scoped CLEAR case passes a
finite generated closed-scene volume, horizon and source identity to D3's real
coverage qualifier. NEAR remains a scenario name; its actual risk is UNKNOWN.

Asset content is opaque in C1. `createC1AssetCache` only fetches fixed opaque IDs,
checks byte limits/media/SHA256, and caches a host-injected decoder. This isolated
host explicitly selects `c3-test-display-v1`; that is NOT a C1 public geometry
schema. Its native occupancy grid uses percent values, preserves -1 unknown,
and downsamples 200x150 -> 40x30 with exact grid bounds for display only. No D2,
D3 or native safety input is modified. Original native plan points are unchanged.

Native records keep their sim stamps and host receipt values. Host receipt in
that artifact is floating seconds, explicitly rounded to ns, never described as
nanosecond capture precision. A recording-specific host alias and the original
recorded maximum receipt define the paused historical snapshot; no source/host
clock equality is assumed. Local browser age continues and cannot renew frozen
data. Native joint state, calibration and C3 collision assessment were not
recorded and remain unavailable; UI never infers native 3D protection from them.

## 2026-10-30: paused freshness regression

[Current results and policy](../../../docs/parallel-expansion-20261029/C3/PAUSED_FRESHNESS.md).
Use a **new** dependency/output directory for this run, e.g. `/tmp/c3-pause-deps`
and `/tmp/c3-pause-results/actual`. C1 now pins `50600c7bce6f5fae743cd836ca1d8ee68d91b05a`;
its executed service/contract blobs are unchanged from the preceding pin.

With the fixture loopback host running on 4183 (or set `C3_FIXTURE_URL`):

```sh
C3_EVIDENCE=/tmp/c3-pause-results/after node tests/expansion_c3/paused_browser.mjs
```

This runs Chromium and WebKit, including **real 2600ms waits**, missing inputs,
map revision/source epoch/reconnect, late responses, current snapshot reads and
canonical server invalidation during pause. It uses the existing official model
and fixture; the canonical notification case replays archived 0.2 HTTP bytes.
It does not load C5's helper or assign C5 any timing responsibility.

With `actual_service.py` running on 4184 using the current exact export:

```sh
C3_NATIVE_REPLAY=1 C3_EVIDENCE=/tmp/c3-pause-results/actual node tests/expansion_c3/actual_browser.mjs
# Copy the same core-results.json into a distinct WebKit output directory first.
C3_BROWSER=webkit C3_NATIVE_REPLAY=1 C3_EVIDENCE=/tmp/c3-pause-results/actual-webkit node tests/expansion_c3/actual_browser.mjs
C3_EVIDENCE=/tmp/c3-pause-results/fixture node tests/expansion_c3/browser.mjs
node --test tests/expansion_c3/test_consumer.mjs tests/expansion_c3/test_canonical.mjs tests/expansion_c3/test_assets.mjs
```

Set `C3_PLAYWRIGHT` and `PLAYWRIGHT_BROWSERS_PATH` for the external installation.
Actual HTTP checks capture the first completed DOM render and consumer snapshot
in a MutationObserver before test automation clicks can outlast the original
250ms collision interval. They separately assert actual 2.6s pause expiry and
no renewal by subsequent HTTP requests. No clock mocking, TTL extension, skipped
assertions or enlarged timeouts are used. Run heavy suites sequentially.
