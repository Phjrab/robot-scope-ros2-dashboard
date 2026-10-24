# C1 approved snapshot integration — 2026-10-24

Branch: `review/20261024-c1-integration-r2`.
Base: `7ef47dc249e4dba83865e78dc283f40013ea92de` (latest remote main at start and pre-submission check).
Verified source candidate: `c5de97b14c3bc132bf881d132378641cf69f825a`. The final publication after this source commit only records CI evidence in this review document.
Scope: hardware-free software integration. `SYNTHETIC_ONLY`; production native motion remains disabled.

## Adopted revisions and preservation

| Role | Approved and adopted HEAD |
|---|---|
| C1 | `2034cc72842ebda1e73f39d12021fb898e75e0b8` |
| D0 | `6403aab3afef96efa778b5265afd7ce5b351265c` |
| C2 | `efc2df6bfaad8f0032fee758b12e250435ffc71c` |
| C4 | `e2e9c5087767f3953d715c61e76388e4769d34b4` |
| C3 | `d0231311c41c9dcb81df35d7138cf11207be49c9` |

An independent clone was used. The source commits were applied with `git cherry-pick --no-commit`, in C1 → D0 → C2 → C4 → C3 order, then recorded as an integration candidate. No conflict resolution or history rewriting was necessary. Applied commit sequences:

- C1: `a49a89b`, `2034cc7`.
- D0: `5983bdc`, `5b3dd23`, `318f7db`, `6403aab`.
- C2: `9864f4d`, `efc2df6`.
- C4: `3611867`, `e2e9c50`.
- C3: `dfeabb3`, `5c144fc`, `d023131`.

The latest main's LiDAR/observation UI and server-backed map anchor presets are retained. `AGENTS.md` is unchanged; the user's explicit review-branch authorization overrides its default main-only publication rule. Only this integration branch is a push target. No PR, main merge, deployment, robot connection, camera acquisition, ARM or physical goal/velocity/posture command was performed.

At the pre-submission remote check, C1/D0/C2/C4 still matched their approved HEADs. C3 had advanced to `6d9b111b10ab4163cede32bf73ea151b1432b27c` (four commits, 11 files, +510/-22). Its diff and `FOLLOWUP.md` were read. They add native hosted execution, a separate workflow, Humble activation/diagnostic fixes and audit changes. Those later commits are **not adopted** here. C3's `.github/workflows/competition-nav2-review.yml` is not duplicated; the integration job runs the approved snapshot's offline tests only.

## Shared changes

The latest main added read-only anchor-preset requests. The full browser run exposed four UI consistency failures caused by a missing fixture response. The exact map-specific empty preset GET response is added to that fixture; assertions and product behavior remain unchanged. Competition E2E output is ignored by Git and retained by the existing failure-artifact workflow.

### Evidence revision selection

`competition_assets.vm_evidence()` explicitly selects `D0-20261024`. The new code-reviewed registry pins D0's original `D0_SOURCE_EVIDENCE.json`, all seven source/validation entries from that manifest, and actual traffic unit-test, integration test/trace and arena summary logs. The unchanged avoidance source and validation are included. Missing files, a modified source, a changed manifest/log, a missing validation report or an unknown revision fail closed. Symlinks, escaped paths and oversized files are rejected.

`vm_evidence('publication-7f2a707')` verifies the original source snapshots and original validation/log hashes. Original publication checksum files are not edited. The response says whether it is historical and exposes the verified hashes; both revisions remain synthetic diagnostics with `native_connected=false`. This does not register an executor or qualify a map.

### One executable software path

`offline Frame → TrafficWorker → C4 TrafficPipeline (D0 color/temporal functions) → CompetitionIngress → C2 NativeActionAdapter → CoordinatorNavigationPort → existing MissionCoordinator → SessionGate/CommandBoundary`.

The entry point is explicit, in-process `MissionRoutes.create_software_native_session(...)`. It is not called by startup, status, an HTTP endpoint or capability discovery. It requires enabled **synthetic** activation and complete declared software ports. Live activation is rejected. The session is limited to one compiled traffic approach/exit pair. Goal poses and visit IDs must match that pair; normal coordinator map/context/preflight checks still execute. Tests replace the external navigation/planner/map/detector/clock boundaries and call the actual service, coordinator, C2/C4 and D0 types.

- The worker has one inference thread and one latest pending frame. Ingress never runs YOLO or opens a camera. Dropped sequences reach C4's stability checks; close discards late results. Existing CameraHub owners can transfer already acquired `Frame` data through the same boundary, but their live clock/source binding is not installed by this change.
- C4 provides signal fields only. Feet, physical stop, pose, path, navigation, safety and departure come from independently stamped trusted ingress. Owner/run/step/config/goal/generation, bound producer epoch, signal/crossing and C4 association/config are checked centrally and again by C2's canonical normalizer.
- A component may retain its original same-host `received_s`. Inference or polling cannot replace this first receipt. Duplicate components retain the original receipt and payload; old epochs/sequences are rejected. The 2 s dwell must be supported by both receipt progression and each foot/motion source timestamp's progression. Deltas are compared within each source clock, never between hosts.
- The existing service's durable request ledger records start, observation/tick, stop and cleanup intent before effects. Same-key payload conflicts and uncertain receipts cannot replay effects. The session serializes event application; coordinator start/continuation/goal calls retain the existing operation/admission lock and actual goal ownership. It does not acquire that same non-reentrant admission lock around a nested coordinator call.
- Successful arrival pauses at `native_barrier`, with no operator confirmation token. Resume/skip/retry cannot bypass the native owner. Canceled approach continuation validates the exact terminal goal, visits, owner token, new generation HOLD ACK and still-fresh C2 postconditions under the coordinator operation lock. Both paths use the existing dispatch/preflight/monitor machinery.
- Operator/safety pause is distinguished from the adapter-owned approach cancellation by the process-local owner token. An external pause permanently blocks native continuation for that run. A regression first reproduced an unwanted second goal before this distinction and now asserts the explicit continuation rejection.
- STOP immediately retires the software command gate and fences the coordinator before awaiting durable IO, admission or planning. Tests reproduced and fixed an exit-preflight race and cover first-goal admission waiting. Native completion releases coordinator ownership only after exit success and departure evidence.
- `native_required` is durably retained, while owner tokens, GREEN/dwell and command authority are not restored. A restarted process cannot restart/resume the old run. The software gate rejects stale RELEASE, foreign goals, old generations, duplicate command sequences and expired inputs; E-stop/collision take priority.

The single runtime action-decision owner is C2. D0 `TrafficLifecycle` is exercised as a regression reference, not as a second goal/HOLD/RELEASE producer. `CommandBoundary` returns a software result; it is not connected to a physical publisher.

## Contract comparison

| Concern | D0 reference | C2/C4 integration |
|---|---|---|
| Approach | No traffic self-HOLD before terminal/cancel ACK | Same; fresh tracking may pass the one gate |
| Terminal vs stop | Explicit action terminal, then distinct HOLD ACK | Exact actual navigation ID; separate HOLD ACK and independently observed body stop |
| Minimum stop | Source-supported continuous 2 s | Both feet INSIDE + STOPPED, receipt and per-source 2 s progression |
| Signal | Associated fresh GREEN before departure | Actual C4 fragment, bound signal/crossing/config; no invented physical evidence |
| Exit | New goal generation; ACK is not departure | New-generation HOLD before dispatch; fresh exit sample permits release; MOVING + departure proof latches departure |
| RED | Revokes before departure; alone does not cancel committed crossing | Same, with safety/path/pose/goal freshness still enforced |
| Restart/uncertainty | New session required | Durable native marker, retired gate and new run required; no automatic nonzero restore |

## Verification

Local environment: Python 3.12.3, Node 20.20.2, existing Chromium. Network installation of optional Python libraries was unavailable. Local cached/system copies supplied NumPy 1.26.4, SciPy 1.11.4, OpenCV 4.10.0, jsonschema 4.10.3 and Pillow 10.2.0; `pip check` passes. CI installs the explicit offline dependency file, including Pillow 12.3.0. No private weights, raw user video or robot input is required.

| Suite | Result |
|---|---|
| Node 20 browser collection | 195 tests / 27 files; no ESM collection error |
| D0 traffic subtree | 136 PASS |
| D0 avoidance subtree | 30 PASS |
| D0 integration subtree | 44 PASS |
| D0 arena regression | 13 PASS |
| D0 independent review | 11 PASS |
| C2 standalone subtree | 66 PASS in final discovery (including first-goal STOP race) |
| C3 offline subtree | 38 PASS; native 144-run plan not executed |
| C4 standalone subtree | 53 PASS, no optional-dependency SKIP |
| Combined actual-package integration | 21 path scenarios + 2 worker scenarios PASS |
| D0 revision evidence | 2 tests PASS, including four mutation/missing-file cases and historical lookup |
| Full Python, final candidate | 2,842 run: 2,840 PASS, 2 SKIP; 85.921 s |
| Full JS | 662 PASS |
| Full browser E2E | Initial 191 PASS / 4 FAIL (new main anchor-preset GET missing from UI fixture); targeted rerun 4/4 PASS; final remote full suite 195/195 PASS on both OS/Python jobs |
| Real FastAPI competition E2E | 5 PASS |
| Static checks | Ruff PASS; mypy 4 source files PASS; JS syntax 105 modules PASS; tracked-source secret scan PASS; pip check PASS; npm audit 0 vulnerabilities |

The two full-suite skips are the existing optional SVG plotting and rosbags CDR backends; C4 and combined integration did not skip locally.

The combined tests cover approach tracking, actual success and canceled-approach continuation, missing HOLD ACK, moving body despite HOLD ACK, insufficient source time, duplicate callbacks/polling, fresh GREEN exit, ACK/departure separation, predeparture RED/UNKNOWN/stale, postdeparture RED, E-stop/collision, old epochs/foreign goals, durable payload conflicts, restart/cancel uncertainty, normal completion STOP during exit preflight and operator pause after internal cancel ACK. Worker tests verify bounded queueing, event-loop responsiveness, sequence-gap invalidation and late-result disposal.

CI adds `competition-offline-integration`, with explicit imports and separate interpreter discovery for D0/C3 and the C2/C4/combined packages. Thus optional imports cannot silently skip the combined path in that job. The two existing OS/Python jobs retain full Python/JS/browser coverage and C1's real-API E2E/failure artifacts. No full native matrix runs on ordinary pushes.

## Remaining bindings and minimum next inputs

| Item | Minimum missing input / owner | Current behavior |
|---|---|---|
| Live camera transfer | C4 + camera owner: verified frame epoch/sequence, source clock relationship, source age and association/config revision | Offline diagnostics work; no camera opened or source timing invented |
| Physical feet/stop/departure | C2 + sensor owner: independent producer clocks/epochs, measured cadence and qualified feet/body/pose evidence | Synthetic evidence only; live native motion disabled |
| Final physical command consumer | C1 + control owner: reviewed integration into existing final arbiter, ACK, TTL, E-stop/collision and cleanup contract | Single software boundary only; no cmd_vel/actuator output |
| Production native route admission | C1 + C2: approved compiled competition run/preflight binding and durable event admission/rate policy | In-process synthetic injection only; public competition native capability remains unavailable |
| Real model accuracy | C4: approved weights and representative GREEN/RED/UNKNOWN data with provenance | Detector is stubbed in CI; real recognition/qualification not claimed |
| Native Nav2 benchmark | C3: separately approved follow-up SHA and genuine isolated native evidence | Approved snapshot offline tests only; zero native runs claimed here |
| Whole-course gait/parking | C2/D0 + physical validation owner: validated posture, footprint, terrain and body-containment ports | Session intentionally limited to traffic approach/exit; other capabilities retain their existing unavailable status |

The session retains the existing bounded 256-request ledger and rejects further non-safety effects when full. A production high-rate ingress needs a separately reviewed durable event/rate policy. Safety cleanup still applies when storage/receipt persistence fails. A hung detector can finish its current worker call after close, but has no mission/command callback and its result is discarded.

## Reproduction and local log identity

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
npm run test:e2e:ci
npx playwright test --config playwright.competition.config.mjs --reporter=line --output=competition-test-results
python -m ruff check robot_dashboard scripts
python -m mypy --config-file mypy.ini
node scripts/check_frontend_syntax.mjs
python scripts/check_repository_secrets.py
```

D0/C2/C3/C4 discovery commands and the explicit optional dependency environment are in `.github/workflows/ci.yml`, job `competition-offline-integration`. Full raw local logs are retained outside the repository in the independent C1 workspace. These digests identify the runs; they are not physical evidence.

| Local log | SHA-256 |
|---|---|
| `r2-python-final.log` | `ef083d842ee0fcc0e45795f7f33e209a5de901b924d57343d45737c7d6fc0ef8` |
| `r2-js-full.log` | `b65fad33b8988d3b27a2ab1b3a8bcf88a94642e9ae4e88cda578dc912371e93a` |
| `r2-competition-e2e.log` | `621c9cff11b57b5afe4a5e3dbddae1a2173a0c5a108223e1e0815d2bea2cbb3b` |
| `r2-d0-traffic-final.log` | `c8f02812e942ba305036c0f08954d992578be39e6c1964a28a8d20ccce683f5f` |
| `r2-d0-avoidance-final.log` | `5fe0849725a4d360f9f720c310047718f9cc4924129028c62d002ddb71f36b15` |
| `r2-d0-integration.log` | `d2887b8c0bc62c12eeb558015d32acf83250d7474de0fbee2a19eff13f5f10be` |
| `r2-d0-arena.log` | `ad0858374dd17e263d12cd9e3f4a56789fdf2ea853777e9cc546c70def1721c0` |
| `r2-d0-independent.log` | `b753e5fcca70ed1889762fe0a4b870e94c965d1a43289166e08b2172bcad2ccc` |
| `r2-c3-offline.log` | `6c93152710661ba40838a4806a27b6d09c05d3d60073e58ae8a6f82dd28eb4fb` |
| `r2-c4-offline.log` | `2f1e394d676662ba73e95dbada4f8c5086199bb2c357c6f3cf2052cf34998273` |
| `r2-integration-final.log` | `305611f9bd962ae7e725b22f94b66994e8bc51b30e489a1599868d5828b4fa55` |
| `r2-browser-full.log` | `18d72a3b048efe7d0bc42fb60de37d2bbd5fcfc6131cad8c2ed9a89a52ca5cba` |
| `r2-consistency-final.log` | `201f4d2165a19f7f2653d7ff0805a4d50f326d4c6fa8b07db6068a48c9fbc8d2` |
| `r2-python-submission.log` | `b578ee822cb22b03521056ba5bfbdbf87d4ca022e4224eca6d34b99628249e2b` |
| `r2-operator-pause-before.log` | `b1535255a9099fafea066cb43904a5f45a66a8ca9c334319303c3e68b6a7219d` |
| `r2-operator-pause-final.log` | `d16b9209237f116d3e503c84607d073509c3fe35cd9876fcbf4c62ad5f087be0` |

## Final remote CI evidence

[CI run 40099488046](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40099488046) completed **SUCCESS** for source `c5de97b14c3bc132bf881d132378641cf69f825a`.

| Job | Result | Completed UTC |
|---|---|---|
| hardware-free-tests (ubuntu-24.04, 3.12) | SUCCESS | 2026-10-24T14:01:34Z |
| competition-offline-integration | SUCCESS | 2026-10-24T13:45:46Z |
| hardware-free-tests (ubuntu-22.04, 3.10) | SUCCESS | 2026-10-24T14:00:55Z |

The dedicated offline job executed 416 tests: C2 66, C4 53, combined integration 23, revision evidence 2, D0 136 + 30 + 44 + 13 + 11, and C3 38. None were skipped. The two matrix jobs passed static checks, dependency audits, Python coverage tests, JavaScript tests, all 195 browser tests and all 5 real-API mission E2E tests. Each matrix root suite ran 2,770 tests with 6 optional-dependency skips: the existing SVG/rosbags checks plus four C4/combined modules in the base environment. The dedicated job installs their dependencies and runs all C4/combined tests with no skips. Raw GitHub job logs were checked; this is not an inference from a queued workflow.

The earlier `cddec817f32694a99665f3fa1088c6ff28c148a1` candidate was superseded by the operator-pause fix and is not the final verification source. The final source and this report retain the same approved role snapshots. Later C3 follow-up code remains excluded.

| Downloaded final job log | SHA-256 |
|---|---|
| `r2-ci-final-offline.log` | `e7fb3f040cf5e98320690962d45b7c0a7d1c96b60d804a59b50503b2e7321313` |
| `r2-ci-final-ubuntu22.log` | `6b806297bec02a50343c6055d747cef2df7de416987f2f9a45839e83d820cbde` |
| `r2-ci-final-ubuntu24.log` | `6c81a70d8b7e3358b670c2dbcde643d837f63ed580a3b82f99370239b2bc8e54` |
