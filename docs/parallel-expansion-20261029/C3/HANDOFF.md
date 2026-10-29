# C3 scene UI handoff — 2026-10-29 (Asia/Seoul)

- **MODULE_IMPLEMENTED / OFFLINE_TESTED / PRODUCT_WIRING_DEFERRED / DEVICE_NOT_RUN**.
- Repository: https://github.com/Phjrab/robot-scope-ros2-dashboard
- Branch: `review/20261029-x-c3-scene-ui` (new independent ordinary clone, not a past C3/controller branch).
- Local clone: `/home/desktop1/Documents/ChatGPT/robot/c3-scene-ui-20261029`.
- **BASE_SHA:** `f469155c2b0c505f3e472e878f75029d7b8d39df`, latest remote main observed at clone. The pack's `05960f8…` was only a research reference. Base remained fixed for this submission.
- **Implemented/tested source SHA:** `e1224295527f72ce962ba209dec960ce1d114440`; source commit tree `730320f5c93dd5b74eb52bbd2a3803892224c8cc`. Final browser, 16 focused consumer tests, C1 compatibility, mandatory Python and JS checks ran against this source. The subsequent submission commit adds only this handoff/evidence: no implementation/test/fixture changes.
- **Final submission HEAD:** the commit containing this file, reported with its exact 40-character SHA and verified remote HEAD in the final chat response. A commit cannot contain its own SHA as literal content without changing that SHA. Resolve this file's containing commit or `git rev-parse HEAD`; do not confuse the tested source SHA above with the final evidence commit.
- Publication target: only `HEAD:refs/heads/review/20261029-x-c3-scene-ui`, no force, merge, PR, deployment or main update.

## Delivered behavior

`mountObstacleScene(host,{scene,subscribe,getMap,theme,clock})` mounts actual 3D diagnostic overlays and an accessible layer/inspect/replay control panel against injected ports. `destroy()` is idempotent and removes the subscription, pending rAF, owned canvas/panel and retained history. Existing RobotScene3D projection, official Go2 asset cache and the existing occupancy origin/yaw helper are reused. No shared scene/model/navigation file is changed, patched or copied.

The module displays supplied sensor points, oriented object boxes with unknown semantic classes, 2D ground-plane costmaps, bounded old/current supplied global plans, nullable supplied local trajectory, official URDF display and separately supplied body/leg/mount/sweep envelope boxes. Object and risk inspectors show source/frame/time/geometry/provenance and preserve separate observation/ingestion booleans. No local fusion, route planning, collision test, TTC calculation or free-space inference exists.

Trusted map/revision/frame/epoch/stream/clock/calibration pins gate incoming display data. Wrong units/frame/clock/calibration, out-of-order/late packets, temporal source/pair skew, stale pose/joints/sources and expired collision intervals explicitly suppress affected geometry/risk. Map/context changes clear overlays/history/selection even while paused. A missing local trajectory stays missing. Pause is browser display only and says so; step consumes the single pending packet. Synthetic provenance is shown in both panel and existing renderer HUD/model label.

Buffers are bounded: one pending packet, one retained normalized packet, at most 3 distinct path generations, 4 × 4096 source points, 128 objects, 2048 points per path, 2 × 4096 costmap cells, 64 envelope boxes and 12000 inspector characters. The painter reuses 192 bytes of box scratch space. It coalesces rAF updates and does not JSON-clone the packet/image on every frame. Display TTLs are documented presentation defaults, not robot safety parameters.

## Changed paths and preserved owners

Only these four owned directory roots changed:

1. `robot_dashboard/static/features/obstacle_scene/` — mount/lifecycle/painter/consumer/C1 adapter/CSS.
2. `tests/expansion_c3/` — executable consumer tests, Python discovery entry, standalone browser and exact-C1 compatibility runners.
3. `experiments/expansion_20261029/c3_scene_ui/` — generated synthetic inputs, existing-renderer host, static loopback server and reproduction notes.
4. `docs/parallel-expansion-20261029/C3/` — integration ports, this handoff and measured evidence.

`app.py`, `app.js`, `navigation.js`, `index.html`, RobotScene3D, Cockpit host, official renderer, existing Initial/Goal URDF, final-heading/TF work, existing 3D Nav2, PCD editor, camera owners, dependencies/lockfiles/CI/launch/config and all other role branches stayed read-only. The original shared checkout was an unborn `master` with no remote and an unrelated untracked `c4-runtime-20261029/`; it was neither switched nor reset/stashed/cleaned. This ordinary clone has its own index/branch.

## Dependency pin and actual compatibility call

- New C1 bootstrap: `review/20261029-x-c1-services@2402c02c6f91ba54064894b21735e01b98610acd`.
- Read-only export: `/tmp/c3-c1-export-2402c02/robot_dashboard/expansion_contracts/`, created with `git archive` then made non-writable. Only that export is used by the compatibility Python process; no C1 source is part of C3 commits.
- **PASS / SYNTHETIC:** actual exported `ObstacleFrame`, `CollisionAssessment`, `ScenePacket.from_dict` → `adaptC1ScenePacket` → C3 consumer → real browser overlay. Output: 3 supplied objects, supplied global plan, costmap and CONTACT_UNCONFIRMED. Wrong map generation, non-map frame and missing display profile are withheld.
- C1 common schema is `0.1`; the adapter explicitly maps it to the C3 display profile using the optional `sources.display` presentation payload. C1 nested dictionaries remain open in this bootstrap. This is a real bounded wire-validator call with an explicit synthetic nested profile, **not** proof that a future arbitrary producer/service already emits that profile.
- D2/D3/C4 new exact dependency SHAs were not available in the one dependency-branch observation (only C1 was published). Their geometry/native replay compatibility checks are **NOT_RUN / INPUT_REQUIRED**. No past C1–C4/D0 branch was substituted. C1 service completion and full cross-role integration are not claimed.

## Environment and input provenance

Ubuntu 24.04.5 LTS, x86_64 VM; Python 3.12.3 in `/tmp/c3-scene-env-20261029`; Node **24.22.1** from the bundled runtime, system Node 18.19.1 used for the focused consumer/discovery smoke; Playwright **1.62.1**; Chromium **151.0.7922.34**, headless, `/tmp/c3-scene-browsers`. No ROS environment was sourced and no DDS/ROS graph or robot address was used. Installed Python dependencies are pinned as actually resolved in [python-packages.txt](evidence/python-packages.txt), including NumPy 1.26.4/SciPy 1.11.4/OpenCV headless 4.10.0.84/JSONSchema 4.10.3. No shared environment or root dependency file was upgraded.

All new scene inputs are generated **SYNTHETIC** fixtures. Runtime replay of those fixtures is UI_FIXTURE/SYNTHETIC, never REPLAY_REAL. The reference cloud is generated in memory, no map/PCD is saved; paths are literal producer fixtures, not native Nav2 plans; costmap lethal cells and envelope risk are supplied examples, not computed ingestion/collision evidence. Actual map hashes/native trajectory/independently validated real robot collision geometry are INPUT_REQUIRED. Existing official URDF-derived web asset is visualization only.

SHA-256 input pins:

| Input | SHA-256 |
|---|---|
| `fixture.js` generator | `c56445a0d80dc295751e9384b2badec82e8ddd7f0577eaf49751cf4196b2d197` |
| `/tmp/c3-compat-input.json` generated C3 input | `35120463e484dc94067d72f99bf2cbe84cb0da3e7a1b369c848923901077db76` |
| `/tmp/c3-c1-wire.json` exact C1-validated generated wire | `1a63e42a20eac259e908d54c7a3432e5d30b2d52b661f2f83574b5abfcec51dc` |

Distances m, angles rad, quaternion xyzw; stamps decimal ns strings retained with BigInt arithmetic. Host monotonic clock only ages local receipts. The grid origin helper handles XY/yaw; the input declares plane Z. No mm/rad/frame conversion or hidden TF correction is guessed.

## Executed validation

All following local source tests ran on `e1224295527f72ce962ba209dec960ce1d114440`. Raw logs and result metadata are committed under `evidence/`.

| Check / evidence class | Result | Executed evidence and limits |
|---|---|---|
| Focused consumer UNIT/SYNTHETIC | **PASS, 16 tests** | `node tests/expansion_c3/test_consumer.mjs`; [consumer-unit.txt](evidence/consumer-unit.txt). Includes import without network/model work, exact ns, epoch/clock/calibration/skew, expiry, bounded history/1200 inputs and copy isolation. |
| C1 exported module compatibility / SYNTHETIC | **PASS** | Actual C1 classes and C3 adapter called; [c1-compatibility.json](evidence/c1-compatibility.json). Native D3 solver not invoked. |
| Browser / UI_FIXTURE | **PASS, 12 scenarios** | [browser-results.json](evidence/browser-results.json), [browser-trace.zip](evidence/browser-trace.zip). Empty→cone→costmap→supplied plan changes→supplied local trajectory; moving/occluded/removed objects; single sensors/unmatched YOLO; bad calibration/clock/skew; map+epoch/reconnect late input; stale robot; inspect/toggles/pause/step; dark/light/narrow/HiDPI; exact C1 wire; load; destroy/remount; request audit. |
| Mandatory Python all | **PASS with 2 SKIP**, 3117 run in 99.292s | `python3 -m unittest discover -s tests -v`; [python-full.txt](evidence/python-full.txt). Skip: optional SVG plotting dependency absent (`test_overlay_artifacts_label_synthetic_and_not_operational`); optional rosbags backend absent (`test_real_humble_cdr_serialization_is_decoded_offline`). Neither skip is counted as PASS. |
| Mandatory relevant JS (all root JS unit files) | **PASS, 699** | Bundled Node 24 `node --test tests/*.mjs`; [javascript-full.txt](evidence/javascript-full.txt). Includes existing scene/Cockpit/pointcloud/observed-joints/Navigation Goal URDF suites. |
| Frontend syntax | **PASS, 116 modules** | `node scripts/check_frontend_syntax.mjs`; [javascript-syntax.txt](evidence/javascript-syntax.txt). |
| Python-discoverable C3 smoke | **PASS, 1 wrapper executing all 16 JS checks** | `python3 -m unittest tests.expansion_c3.test_module -v`; [c3-python.txt](evidence/c3-python.txt). |
| Staged whitespace / tracked-source credential scan / ownership | **PASS before source commit** | `git diff --cached --check`; `python3 scripts/check_repository_secrets.py`; final staged check repeated before evidence commit. No new raw maps/PCD/recordings/weights/env/build/install/log/secrets staged. |
| Full pre-existing Playwright product E2E | **NOT_RUN** | C3's actual browser runner above executed; no claim that every unrelated product E2E suite was run. Shared product entrypoints were unchanged. |
| D3 native replay, NATIVE_NAV2_SIM | **NOT_RUN / INPUT_REQUIRED** | No exact new D3 SHA/native packet input available. No simulated curve is counted as a Nav2 result. |
| REPLAY_REAL / LIVE / actual hardware | **NOT_RUN / DEVICE_NOT_RUN** | No robot SSH/HTTP/DDS/camera/sensors/services/config/TF/initialpose/goal/velocity/posture/deployment accessed. |
| Remote CI at document creation | **NOT_TRIGGERED (pre-push)** | Existing push workflow is tests/audits only; no hardware deployment job. The final response reports the one post-push observation for exact final HEAD. Local PASS does not assert remote CI PASS. |

The final 1200-packet browser run lasted **30,050.4ms = 39.93Hz**; it kept max pending **1**, retained packet **1**, history **1 ≤ 3**. An additional synchronous 1200-packet burst increased coalesced drops by **1199**. Post-GC heap changed from **3,230,700** to **3,481,664** bytes (+250,964 bytes); this bounded 30s sample is not a proof of indefinite leak freedom. Measured interaction latencies were **30,32,50,44,35,48ms**; max sampled rAF gap **36.1ms**; max overlay draw **2.2ms**. The VM measurement is not Jetson FPS or performance certification; no C3 Python/JS regression process overlapped its stress run. Unrelated parallel chats were not controlled.

The browser recorded **23 same-origin GET requests**, zero API/mutation/cross-origin/websocket requests and zero page errors. Its primary context also blocks such requests, so a regression would be visible in the request audit. The functional trace covers functional UI scenarios; stress has measured JSON evidence, not a 30s video/trace.

Visual evidence: [desktop dark + inspect](evidence/desktop-dark-inspect.png), [desktop light](evidence/desktop-light.png), [390px light](evidence/narrow-light.png), [390px dark / DPR2](evidence/narrow-dark-hidpi.png), [source mismatch](evidence/mismatch-dark.png), [C1 validated synthetic wire](evidence/c1-validated-synthetic.png). Screenshots were inspected at desktop and narrow sizes.

Development failures were corrected before this candidate: duplicate path generations in bounded history; a stale-input transition that could leave URDF visible until the 100ms refresh (now invalidates on the next frame); the existing renderer's default LIVE POSE label in a synthetic host (now explicitly SYNTHETIC). A browser test initially expected an epoch error while changing both map and epoch; it now separately checks map rejection and same-map old-stream rejection. Final pass results above do not conceal these earlier findings. Earlier failure trace remains local in `/tmp/c3-development-failure-trace.zip`, outside the submitted final evidence.

## Reproduction

Use an isolated Python venv for repository requirements, the bundled Node 24 or compatible Node runtime, and an isolated Playwright 1.62.1/Chromium installation. Run from this clone root. Actual environment setup used:

```sh
python3 -m venv /tmp/c3-scene-env-20261029
/tmp/c3-scene-env-20261029/bin/python -m pip install -r requirements.txt -r requirements-competition-offline.txt
PLAYWRIGHT_BROWSERS_PATH=/tmp/c3-scene-browsers \
  /home/desktop1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  /home/desktop1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/cli.js install chromium
python3 experiments/expansion_20261029/c3_scene_ui/serve.py --port 4183
```

In a second terminal (server remains on loopback, no robot access):

```sh
node tests/expansion_c3/test_consumer.mjs
PATH=/tmp/c3-scene-env-20261029/bin:$PATH python3 -m unittest discover -s tests -v
/home/desktop1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --test tests/*.mjs
/home/desktop1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node scripts/check_frontend_syntax.mjs
PATH=/tmp/c3-scene-env-20261029/bin:$PATH python3 -m unittest tests.expansion_c3.test_module -v
```

To reproduce the exact counterpart check, fetch **only** its pinned commit, export its contracts to a fresh private `/tmp` directory and make the export read-only. No branch merge or copy into C3 source:

```sh
git fetch --no-tags origin 2402c02c6f91ba54064894b21735e01b98610acd
mkdir -p /tmp/c3-c1-export-2402c02
git archive 2402c02c6f91ba54064894b21735e01b98610acd robot_dashboard/expansion_contracts | tar -x -C /tmp/c3-c1-export-2402c02
chmod -R a-w /tmp/c3-c1-export-2402c02
node --input-type=module -e "import{makePacket,makeContext}from'./experiments/expansion_20261029/c3_scene_ui/fixture.js';import{writeFileSync}from'node:fs';writeFileSync('/tmp/c3-compat-input.json',JSON.stringify(makePacket(1,'multi',makeContext({map_id:'111111111111111111111111',revision:'1'.repeat(64)}))));"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/c3-c1-export-2402c02 \
  /tmp/c3-scene-env-20261029/bin/python tests/expansion_c3/c1_compatibility.py /tmp/c3-compat-input.json /tmp/c3-c1-wire.json
node tests/expansion_c3/check_c1.mjs /tmp/c3-c1-wire.json
C3_C1_WIRE=/tmp/c3-c1-wire.json \
C3_PLAYWRIGHT=/home/desktop1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright \
PLAYWRIGHT_BROWSERS_PATH=/tmp/c3-scene-browsers \
  /home/desktop1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node tests/expansion_c3/browser.mjs
```

Use a fresh export directory or its already populated exact-SHA read-only export; do not try overwriting a read-only export. Test runner timeouts were 150s for mandatory Python, 180s for root JS, 60s syntax, 30s C3 wrapper; none timed out. `regression-results.json` records expanded commands and exit codes.

## Future product connection and one next action

[INTEGRATION_POINTS.md](INTEGRATION_POINTS.md) names the actual future shared functions and minimum ports: Cockpit `createCockpitSceneHost` activate/deactivate/renderState lifecycle, RobotScene3D projection/camera hook, official model/joint cache, saved map scene alternative and shared latest-only pointcloud transport. Current robot/goal slots must retain their separate owners. C1 stream validation and independently verified D3 geometry/hash/calibration/time pins remain prerequisites for any future live wiring. Default remains OFF because no product entrypoint imports C3. Recovery is explicit feature destroy/unmount; no runtime configuration or robot state changed.

**Next one action:** after a new D3 exact SHA/native replay is published, run one read-only exported map-bound packet replay through this C1 adapter and UI. Do not start product/main integration or equipment validation until the user separately authorizes that phase after the existing three tasks finish.

Evidence boundary: main changed **NO**; robot/camera connection **NO**; equipment deployment/service/motion **NO**; public original PCD/private captures/weights/rosbags/env/secrets committed **NO**. No unexecuted check is reported as successful, and no deployment/driving completion is claimed.
