# Multi-SLAM software delivery — 2026-10-15

Status: standalone MS software implementation, local verification and exact-SHA
remote CI complete within the limits below. Combined MR validation remains with
the MR owner. No live deployment or hardware claim. MAP-02 full retained-landmark access remains BLOCKED.
All changes preserve the original 1b0ae5b hardware follow-up and existing lab.

| Requirement | Implementation | Software evidence | Live / operational |
|---|---|---|---|
| R01 selection | slam_sessions, slam_wiring, existing dashboard SLAM panel | catalog/mode/ownership tests | installed readback BLOCKED |
| R02 actual start/stop/save | FAST-LIO coordinator, IsaacStereoAdapter, private broker, fixed launch, SLAM API | real call paths with fake ROS/native responses; lifecycle/failure tests | hardware mapping/native save BLOCKED |
| R03 native management | slam_packages, catalog UI/API, original-preserving scratch localize | atomic/hash/archive/compatibility/offline preview tests | actual native round-trip and successful fresh-pose localize BLOCKED |
| R04 actual camera observations | real left rectified IR subscriptions, timestamped optical transform, slam_features projection | known synthetic projection, invalid/stale/lost/calibration tests; bounded WS | live pixel alignment/source clock qualification BLOCKED |
| R05 global features / trajectory | replace-only global snapshots, spatial LOD, map scene, calibrated optical frustum | global extent/epoch/trajectory/camera view fixtures | global extent software implemented; full retained map MAP-02 BLOCKED by unverified capped export |
| R06 preservation | common pipeline ownership, MR read-only context, ARM/service/camera/dataset/legacy guards | existing regression suites and focused fault/security tests | equipment cleanup/load/performance not executed |

Source provenance: historical installed Isaac ROS3.2.6 and reference source
e31f4cc are different evidence. LL_OBSERVATIONS2048 and LL_MAP32768 visualization
caps do not establish full engine totals or installed semantics. Engine total
stays null. Corrected pose uses vis/slam_odometry, never VO renamed as map pose.
No native2D all-track exporter or complete retained-landmark exporter is claimed.

Review corrections include delayed status generation fencing, save-and-stop tail
confirmation, uncertain camera reservation recovery, nonblocking broker cleanup,
failed-save scratch release, finite hints, native localize stream quarantine,
source-time epoch fences and actual calibrated optical camera view. Frustum1m
rays are a display convention, not measured range. Saved preview consistency is
approximate; camera pixels excluded. Native load is not localization success.

## Verification environment and results

Local runtime: existing .venv Python3.13. Quality tools isolated in
/private/tmp/robot-scope-ms-quality; runtime environment and experiment image were
not reinstalled. System Python lacks runtime dependencies, so dependency-complete
.venv is used. Local socket/browser fixture tests require reviewed localhost
permission; no real ROS/camera/broker service was started. All browser backend
streams/maps are synthetic fixtures, not hardware screenshots.

Standalone MS candidate local results (before subsequent MR/shared-hook changes):

- Python unittest under coverage: 1,855 tests PASS, 2 skips (optional rosbags;
  Linux /proc process test on macOS), 100.262s. Coverage73%.
- JavaScript:370/370 PASS. Full Chromium E2E:80/80 PASS (2.2min).
- Focused runtime26, sessions34, features37, camera12, broker22, packages17,
  API14, wiring17; SLAM UI10 and E2E7 included in the full runs.
- Python3.10 grammar validation:172 source/script files PASS.

First full run failed2 stale API inventory/guard assertions; these were fixed by
adding explicit SLAM endpoints and existing direct origin guards. Subsequent full
runs passed. Exact stream pathname is now compared against the real server route;
the fixture no longer masks a URL mismatch. Final tests include post-localize
fresh-pose confirmation and persistent outcome/retry UI. No success is inferred
from native callback alone.
Ruff, configured mypy (4 existing files), frontend syntax (80 modules), pip check,
Python dependency audit and npm high-severity audit PASS at pre-publication check.
No workflow rules, Nav2 policy, timeout threshold or coverage gate weakened.

## Integration / remaining gates

MS applied MR-MS-001/002 router/configuration and default-false planner CLI
hooks in the shared checkout after MR source was copied. Focused shared tests51
and competition8 PASS; those hooks and MR source remain uncommitted and are not
part of the standalone CI candidate below. MR owns the coherent combined-source
full tests and local Git window; MS uses an explicitly returned five-document
publication window only. Actual map id/revision/frame, operational source/
generation/readiness and unverified alignment are read-only, revision-fenced
inputs; selected observation engine grants no pose or movement authority.
Effective planner-policy evidence remains BLOCKED. See HANDOFF for current windows.

Stage16 requires exact candidate CI/live release, current camera/resource owner,
approved service changes, backups/rollback and operator window. Stage17 operational
pose/initial pose/goal/movement remains NOT_RUN under its separate conditions.

Published and verified standalone source: `d866a3be78b34cbd16c68f3c8cf27e768c491216`.
[Exact source CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38691471690) **PASS** on
Ubuntu22.04/Python3.10 and Ubuntu24.04/Python3.12. Each matrix passed Python1855
(1 optional rosbags skip), coverage73%, JS370 and Chromium80, plus the configured
static, secret and dependency checks. Core implementation provenance remains
`72641da309bf041826a70469d6cc32f60a16fe03`.

The initial remote run38689015528 failed only because22 broker fixtures assumed
macOS /private/tmp. The test now uses canonical short /tmp on Linux/macOS.
Focused broker22 and full local Python1855 passed after correction; no product
source or CI policy changed. The exact follow-up SHA now passes the full remote
workflow. The existing experiment image, installed dependencies and user data
were preserved. User explicitly approved follow-up publication before the push.
