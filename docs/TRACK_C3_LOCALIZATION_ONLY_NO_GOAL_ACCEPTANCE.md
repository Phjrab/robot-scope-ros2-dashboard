# Track C3 lease-free localization-only no-goal acceptance

Status date: 2026-09-02

```text
SOFTWARE_PASS
DEPLOYMENT_STAGING_PASS
C2_RECHECK_PASS
INITIAL_POSE_ONCE_NOT_RUN
LOCALIZED_NG1_NOT_RUN
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
| Production symlink | `/home/jetson_orin_nano/robot-scope -> /home/jetson_orin_nano/releases/robot-scope/382a865` |
| Production service | active from clean release `382a865`; `ROBOT_SCOPE_DIR` and the reversible systemd release override point to that exact release |
| Private environment | `/home/jetson_orin_nano/.config/robot-scope/control.env`, mode `0600`; content is not recorded here |
| Clean production path | `/home/jetson_orin_nano/releases/robot-scope/382a865` |
| Production commit | `382a86585797d8735486f2e0990a5335cd137490` |

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
| Candidate x/y/yaw | `NOT_RUN` |
| Cell value | `NOT_RUN` |
| Robot-radius clearance | `NOT_RUN` |
| Map preview | `NOT_RUN` |
| Robot actual direction | `NOT_RUN` |
| Exact request body shown | `NOT_RUN` |
| Operator confirmation | `NOT_RUN` |
| `/initialpose` publish count | `0` |

No earlier general approval, C2 approval or automatically calculated pose is
authorization to publish `/initialpose`.

## Acceptance table

| Check | Result | Evidence |
|---|---|---|
| Repository implementation | `PASS` | distinct coordinator/gateway/API owner with no lease or output path |
| Hardware-free focused tests | `PASS` | exact-map, one-shot, interlock, command isolation, cleanup and C2 checker coverage |
| External dirty checkout preserved | `PASS` | read-only inventory; no in-place update or service switch |
| Clean exact-commit staging | `PASS` | detached exact commit, source hashes checked; production checkout/service target unchanged |
| C2 stationary NG0 recheck | `PASS` | staged checker returned `WAITING_FOR_INITIAL_POSE`, private raw command `quiet` |
| Candidate pose validation and display | `NOT_RUN` | operator confirmation gate not reached |
| Initial pose exactly once | `NOT_RUN` | publish count remains zero |
| `map -> odom -> base_link` and `/amcl_pose` | `NOT_RUN` | requires confirmed initial pose |
| Lifecycle and both costmaps | `NOT_RUN` | requires localized NG1 |
| 60-second localized NG1 | `NOT_RUN` | requires confirmed initial pose |
| Goal and Mission | `NOT_RUN` | prohibited in C3 |
| Lease/ARM/deadman/motion | `NOT_RUN` | prohibited; live evidence pending |
| Reverse cleanup | `PASS` | pre-confirmation session stopped; external publishers/ports and mounted services returned inactive/zero |
| Complete Python/JavaScript/e2e tests | `PASS` | Python 963, Playwright 32, Cockpit 86, Ruff, mypy and JS syntax PASS |
| Commit and `origin main` push | `NOT_RUN` | only after acceptance evidence is complete |

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
checkout.

`/amcl_pose`, localized TF/costmaps and NG1 remain `NOT_RUN`. During the later
confirmation-gated run, any nonzero raw command or Sport request is an
immediate `FAIL` and requires reverse cleanup. Missing or ambiguous evidence
is `BLOCKED`, never `PASS`.

## Changed files, tests, commit and push

The final changed-file inventory, complete command results, repository and
deployed commit, hashes, focused commit and push result will be recorded only
after the confirmation-gated hardware portion completes.
