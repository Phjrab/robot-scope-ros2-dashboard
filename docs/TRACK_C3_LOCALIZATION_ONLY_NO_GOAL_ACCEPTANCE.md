# Track C3 lease-free localization-only no-goal acceptance

Status date: 2026-09-02

```text
SOFTWARE_PASS
DEPLOYMENT_STAGING_PASS
C2_RECHECK_PASS
INITIAL_POSE_ONCE_PASS
LOCALIZED_NG1_PASS
GOAL_NOT_RUN
LEASE_NOT_ACQUIRED
MOTION_NOT_RUN
CLEANUP_PASS
```

## Scope and immutable safety boundary

This record covers only the explicit
`go2-xt16-wireless-competition-fastlio` localization-only session. It fixes
the earlier C3 contradiction by giving exact-map Nav2 localization a distinct
owner that cannot acquire a navigation or manual-control lease and cannot own
a goal, Mission, ARM, deadman, control binding or accepted motion output.

The ordinary `/api/v1/navigation/start` contract is unchanged. Track A/B,
the strict wireless `/utlidar/robot_odom` transport and its 500 ms source-age
and 100 ms future-skew guards, `competition-pdf-direct`, and the C2 profile
remain intact. A `PASS` row means the exact check ran. `BLOCKED` identifies a
missing prerequisite. `NOT_RUN` is deliberate and is never promoted by
software-only evidence.

## Baseline and external deployment inventory

| Item | Evidence |
|---|---|
| Repository baseline | `382a86585797d8735486f2e0990a5335cd137490` on `main` before the C3 map-pin update |
| Baseline CI | GitHub Actions run `33606397403`, successful |
| External production checkout | `/home/jetson_orin_nano/project/robot-scope`, old/dirty at `72e39c3f9517e9ba445ee2b8ddbcf6779bfe699b` |
| Production symlink | `/home/jetson_orin_nano/robot-scope -> /home/jetson_orin_nano/releases/robot-scope/92117dd` |
| Production service | active from clean release `92117dd`; `ROBOT_SCOPE_DIR` and the reversible systemd release override point to that exact release |
| Private environment | `/home/jetson_orin_nano/.config/robot-scope/control.env`, mode `0600`; content is not recorded here |
| Clean production path | `/home/jetson_orin_nano/releases/robot-scope/92117dd` |
| Production commit | `92117dd03588817adf9bbce269029243f86761b2` |
| Map-pin CI | GitHub Actions run `33609783794`, successful |

The old deployment checkout is preserved in place. C3 must not pull, reset,
clean, overwrite or reuse it as a staging directory. The production service
was switched separately after explicit operator approval; its default profile
and port 8088 remain unchanged.

## Fixed bindings and pinned candidate

| Role | Binding |
|---|---|
| Profile | `go2-xt16-wireless-competition-fastlio` |
| Localization odometry | `/Odometry`, `camera_init -> body` |
| Controller odometry | `/robot_scope/nav/controller_odom_fastlio`, `odom -> base_link` |
| Scan | `/scan` |
| Initial pose | fixed `/initialpose`, frame `map`, exactly one message |
| Localization result | `/amcl_pose`, exactly one publisher required |
| Private command monitor | `/robot_scope/nav/cmd_vel_raw` |
| Sport monitor | `/api/sport/request` |
| Managed map | `map_20260902_161903_edited` |
| Map ID | `f292601e2c8b269eb635cb0f` |
| Map revision | `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93` |
| Map metadata | 297×156, 0.05 m/cell, origin (-8.97357559204, -2.05925989151, 0); 21,505 free, 24,827 occupied, 0 unknown cells |

## API and state contract

The same-origin mutation endpoints are:

- `POST /api/v1/navigation/localization/start`
- `POST /api/v1/navigation/localization/initial-pose`
- `POST /api/v1/navigation/localization/stop`
- `GET /api/v1/navigation`

The separate session states are `idle`, `starting`,
`waiting_initial_pose`, `localizing`, `localized`, `stopping` and `failed`.
Its public state pins map and parameter revisions, counts initial-pose and raw
command observations, and always reports `goal_allowed=false` and
`motion_allowed=false`.

Initial-pose publication requires an active waiting session, the same exact
map/revision, `confirmed=true`, fresh fixed sensor inputs, one fixed publisher,
a finite known-free pose with robot-radius clearance and a zero pose count.
The count is committed to one after the single publish. Recovery and status
callbacks never replay it. A duplicate attempt is rejected explicitly.

A nonzero private command, malformed sensor sample, publisher conflict or
other runtime fault closes the runtime session, notifies its application
owner and reverse-cleans the exact Nav2 and mapping owners without submitting
a control command.

## Operator-confirmed initial pose

| Field | Value |
|---|---|
| Exact live map/revision recheck | `PASS` — read from the production saved-map catalog on 2026-09-02 |
| Resolution and image size | `PASS` — 0.05 m/cell, 297×156 |
| Candidate x/y/yaw | `PASS` — `(0.0, 0.0, 0.0)` |
| Cell value | `PASS` — cell `(179, 41)` is free |
| Robot-radius clearance | `PASS` — all 61 cells inside the configured 0.22 m radius are free |
| Map preview | `PASS` — the managed-map geometry and exact candidate were shown before mutation |
| Robot actual direction | `PASS` — operator confirmed the robot was at the mapping start and faced the same direction |
| Exact request body shown | `PASS` — map ID/revision and nested x/y/yaw payload were shown before mutation |
| Operator confirmation | `PASS` — exact confirmation `C3 초기 위치 x=0 y=0 yaw=0 발행 승인` received |
| `/initialpose` publish count | `PASS` — runtime and application session both reported exactly `1` |

No earlier general approval, C2 approval or automatically calculated pose is
authorization to publish `/initialpose`.

The map origin candidate `(x=0.0, y=0.0)` was evaluated before starting the
confirmation-gated session. Cell `(179, 41)` is free, and all 61 cells inside
the configured 0.22 m robot radius are free. The operator then independently
confirmed the robot's physical location and heading before the one-shot
request was sent.

## Acceptance table

| Check | Result | Evidence |
|---|---|---|
| Repository implementation | `PASS` | distinct coordinator/gateway/API owner with no lease or output path |
| Hardware-free focused tests | `PASS` | exact-map, one-shot, interlock, command isolation, cleanup and C2 checker coverage |
| External dirty checkout preserved | `PASS` | read-only inventory; no in-place update or service switch |
| Clean exact-commit staging | `PASS` | detached exact commit, source hashes checked; production checkout/service target unchanged |
| C2 stationary NG0 recheck | `PASS` | staged checker returned `WAITING_FOR_INITIAL_POSE`, private raw command `quiet` |
| Candidate pose validation and display | `PASS` | exact map/revision, `(0, 0, 0)`, free cell `(179, 41)` and 61/61 clearance cells shown before confirmation |
| Initial pose exactly once | `PASS` | accepted once; session count `1`; no retry or replay |
| `map -> odom -> base_link` and `/amcl_pose` | `PASS` | localized checker passed before and after the bounded observation |
| Lifecycle and both costmaps | `PASS` | required lifecycle nodes active; global/local costmap publishers each exactly one during localized NG1 |
| 60-second localized NG1 | `PASS` | 60/60 one-second API samples retained localization/readiness and exact-zero control; the external Nav DDS graph received no C3-owned Sport sample |
| Goal and Mission | `NOT_RUN` | prohibited in C3 |
| Lease/ARM/deadman/motion | `PASS` | lease remained inactive, deadman false, dashboard command exact zero, `goal_allowed=false`, `motion_allowed=false`, nonzero raw-command count zero |
| Reverse cleanup | `PASS` | localization session stopped, C3 Nav2/FAST-LIO/runtime owners exited, then production profile was restored to `go2-xt16-wireless` |
| Complete Python/JavaScript/e2e tests | `PASS` | focused Python 29, venv Python 980, JavaScript 270, Playwright 32, Ruff and mypy PASS |
| Commit and `origin main` push | `PASS` | this acceptance record and the unexecuted C4 prompt are committed together; exact SHA is retained in Git history and the final handoff |

## Live observation and cleanup

The pre-confirmation C2 run observed one publisher for the fixed scan,
FAST-LIO and canonical controller-odometry inputs. Cloud and odometry were
approximately 10 Hz, IMU was approximately 500 Hz, frames were
`camera_init -> body` and `odom -> base_link`, accepted points were about
14,884–14,896, and clock offsets were about 22–31 ms. The exact checker
verified no lease, deadman false, exact-zero dashboard command, quiet private
raw command, no Sport request and `WAITING_FOR_INITIAL_POSE`.

The first staged attempt failed closed before Nav2 because the clean source
checkout did not contain the Git-ignored C++ dependency workspace. Relay,
Hesai and IMU were healthy; `wireless_cloud_bridge.log` reported the missing
binary. The already validated binary was then referenced temporarily with
SHA-256 `99a56c3ff62c9f9ece51b4da80f85e5590b41a663eddd52fd8fec1d86dd332ec`.
That dependency link was removed after the accepted C2 run, restoring a clean
staged Git status.

The accepted pre-confirmation session was explicitly stopped. External
publishers for `/lidar_points`, `/imu/body`, `/velodyne_points`, `/Odometry`,
canonical odometry, `/scan`, `/map` and the private command all returned zero;
the fixed UDP ports had no listener. Mounted relay, IMU, odometry and Control
Bridge services were inactive. The foreground candidate dashboard was then
stopped and the production service returned active from its original old
checkout. A later, separately approved deployment replaced that production
target with clean release `92117dd`; its post-deployment state was lease
inactive, deadman false, exact-zero command, navigation `idle`, localization
session `idle` and goal `idle`.

The confirmation-gated run used the clean production release `92117dd` and
the exact pinned map/revision above. The prelocalization checker first passed
with `WAITING_FOR_INITIAL_POSE` and a quiet private raw-command topic. After
the exact operator confirmation, the dashboard API published `(0, 0, 0)`
once. The session moved through `localizing` to `localized`; its observed pose
was approximately `(-0.0010, 0.0014, 0.00046)`. Both the immediate and final
localized checker passed with connected `map -> odom -> base_link`, fresh
`/amcl_pose`, active required lifecycle nodes, one publisher for each costmap
and a quiet raw-command topic.

The bounded observation collected 60/60 valid one-second API samples. Every
sample kept the exact map/revision, localized state, initial-pose count one,
goal `idle`, motion disabled, lease inactive, deadman false, dashboard command
exact zero, nonzero raw-command count zero and all required readiness fields
true. A simultaneous typed `unitree_api/msg/Request` subscription observed no
`/api/sport/request` message in the external Nav DDS graph for 60 seconds and
exited only on the expected timeout. No goal, Mission, ARM or robot motion was
requested by C3.

A later robot-side Foxy audit found that this external subscription was not a
whole-robot Sport-topic monitor: the narrow wireless architecture does not
carry the robot-side Go2 DDS graph to the external Nav graph. On the robot
side, the pre-existing safety Bridge was publishing only API 1003 `StopMove`
while its exact-cardinality check remained fail-closed at ten observed versus
nine expected anonymous Unitree publishers. No API 1008 `Move` or action was
observed. This does not invalidate the lease-free C3 localization result or
authorize motion, but it narrows the claim to C3-owned command isolation and
records that future motion acceptance must monitor the robot-side graph
directly. The v1.1.15 baseline correction is a separate C4 prerequisite.

The localization health summary was `READY` immediately after convergence.
The final API sample reported `DEGRADED` while all readiness and checker
conditions remained valid; the adjacent cleanup snapshot showed odometry at
9.985 Hz against a strict 10.0 Hz health threshold, with fresh age, low jitter,
no jump/reset and connected TF. This is retained as a threshold-margin review
item and was not hidden or used to relax any guard.

The point-in-time resource snapshot reported about 156 MiB RSS for FAST-LIO,
54 MiB for the navigation runtime and 21–29 MiB for each Nav2 child. The seven
navigation runtime/child processes totalled about 197 MiB RSS. Dashboard CPU
was 84.7%, FAST-LIO 30.3% and the navigation group about 49.3% at that instant;
these are single multi-core samples, not averages, and require a later soak for
capacity conclusions.

Reverse cleanup set the localization session and shared pipeline to `idle`.
All C3 Nav2, navigation-runtime, FAST-LIO and bridge processes were absent on
the external host before operational restore. The temporary profile was
restored from `go2-xt16-wireless-competition-fastlio` to
`go2-xt16-wireless`, and the production service restarted from clean release
`92117dd`. Its post-restore navigation session and goal are `idle`, lease is
inactive, deadman false and command exact zero. The established dashboard
startup policy then independently reacquired the XT16 preview path, so the
Hesai UDP receiver and mounted XT16 relay are active under preview ownership;
Nav2, FAST-LIO, wireless IMU sender and wireless odometry sender remain
inactive. This preview reacquisition is not C3 residue.

## Changed files, tests, commit and push

The preparatory map-pin update changed this acceptance record,
`TRACK_C3_STATIONARY_INITIAL_POSE_NO_GOAL_PROMPT.md`, the exact constants in
`scripts/check_competition_no_goal_ready.py`, and its C3 regression fixtures.
Commit `92117dd` was pushed to `origin/main`, passed CI run `33609783794` and
was deployed as a clean release. Documentation follow-up `6cdb9cb` passed CI
run `33610758672` on both supported Python/Ubuntu jobs.

For this confirmation-gated acceptance update, focused C2/C3 Python tests
passed 29/29, JavaScript unit tests passed 270/270 and Playwright passed 32/32.
The exact repository-workflow command using the host `python3` ran 976 tests:
975 passed and `test_competition_state` could not import because that host
interpreter lacks the declared `fastapi` dependency. The project virtual
environment, which contains the declared dependencies, passed all 980 Python
tests. Ruff reported all checks passed and mypy reported no issues in four
source files. The first Playwright attempt was blocked before test collection
by the sandbox's local-port restriction; the permitted rerun passed all 32.

This confirmation-gated C3 update also adds the deliberately unexecuted C4
short-low-speed-goal prompt. The repository now contains a strict Go2 v1.1.15
baseline correction for the observed ten anonymous publishers, but C4 remains
blocked until that focused commit is deployed to both control endpoints,
stationary readiness is revalidated and a separate supervised-motion approval
is received.
