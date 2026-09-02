# Track C3 lease-free localization-only no-goal acceptance

Status date: 2026-09-02

```text
SOFTWARE_PASS
DEPLOYMENT_STAGING_NOT_RUN
C2_RECHECK_NOT_RUN
INITIAL_POSE_ONCE_NOT_RUN
LOCALIZED_NG1_NOT_RUN
GOAL_NOT_RUN
LEASE_NOT_ACQUIRED
MOTION_NOT_RUN
CLEANUP_NOT_RUN
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
| Repository baseline | `8406da8c174cda171d82f45c39724583e1ff0047` on `main` |
| Baseline CI | GitHub Actions run `33571349263`, successful |
| External production checkout | `/home/jetson_orin_nano/project/robot-scope`, old/dirty at `72e39c3f9517e9ba445ee2b8ddbcf6779bfe699b` |
| Production symlink | `/home/jetson_orin_nano/robot-scope -> /home/jetson_orin_nano/project/robot-scope` |
| Production service | active from the old checkout; not restarted or redirected by C3 staging |
| Private environment | `/home/jetson_orin_nano/.config/robot-scope/control.env`, mode `0600`; content is not recorded here |
| Clean staged path | `NOT_RUN` |
| Staged commit and hashes | `NOT_RUN` |

The old deployment checkout is preserved in place. C3 must not pull, reset,
clean, overwrite or reuse it as a staging directory. The production service,
default profile, symlink and port 8088 stay unchanged until a separate
explicit production-switch decision.

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
| Managed map | `map_20260813_125411` |
| Map ID | `97bae189b35182c688cecb3c` |
| Map revision | `60becc42ecb58aca30834c92ed4778e0a38d31562950524a5871808d225ae4ae` |
| Map metadata | 120×169, 0.05 m/cell; live revalidation still required |

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
| Exact live map/revision recheck | `NOT_RUN` |
| Resolution and image size | `NOT_RUN` |
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
| Clean exact-commit staging | `NOT_RUN` | pending staged release preparation |
| C2 stationary NG0 recheck | `NOT_RUN` | must precede candidate confirmation |
| Candidate pose validation and display | `NOT_RUN` | operator confirmation gate not reached |
| Initial pose exactly once | `NOT_RUN` | publish count remains zero |
| `map -> odom -> base_link` and `/amcl_pose` | `NOT_RUN` | requires confirmed initial pose |
| Lifecycle and both costmaps | `NOT_RUN` | requires localized NG1 |
| 60-second localized NG1 | `NOT_RUN` | requires confirmed initial pose |
| Goal and Mission | `NOT_RUN` | prohibited in C3 |
| Lease/ARM/deadman/motion | `NOT_RUN` | prohibited; live evidence pending |
| Reverse cleanup | `NOT_RUN` | live session not started |
| Complete Python/JavaScript/e2e tests | `NOT_RUN` | run after live acceptance |
| Commit and `origin main` push | `NOT_RUN` | only after acceptance evidence is complete |

## Live observation and cleanup

Topics, QoS, rates, TF, `/amcl_pose`, lifecycle, costmaps, raw command/Sport
monitoring, resource use and reverse-cleanup evidence are `NOT_RUN`. During a
live run, any nonzero raw command or Sport request is an immediate `FAIL` and
requires reverse cleanup. Missing or ambiguous evidence is `BLOCKED`, never
`PASS`.

## Changed files, tests, commit and push

The final changed-file inventory, complete command results, repository and
deployed commit, hashes, focused commit and push result will be recorded only
after the confirmation-gated hardware portion completes.
