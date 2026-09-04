# Track C4B non-intrusive Sport request evidence

Date: 2026-09-03

Status: `STATIONARY HARDWARE + C2 NG0 ACCEPTED — C3/C4B NOT AUTHORIZED`

## Purpose

The first supervised C4B attempt correctly failed closed because an external
read-only ROS 2 subscriber changed `/api/sport/request` cardinality from one to
two. This change provides evidence from the existing Go2 Control Bridge instead
of adding a second DDS endpoint. It does not authorize a navigation session,
initial pose, goal, ARM, deadman, non-zero command or robot motion.

## Architecture

The existing Bridge remains the only Robot Scope publisher on
`/api/sport/request`. Immediately after that publisher returns successfully, a
pure in-process recorder classifies the published API request. The snapshot is
included in the existing signed Bridge status envelope and is strictly
validated by the external dashboard before a bounded allowlist is exposed at
`GET /api/v1/control`.

The recorder creates no ROS publisher, ROS subscriber, timer, process, network
socket, control manager, lease or motion authority. It does not choose, modify,
delay or retry requests. A failed publisher call is not recorded as a
successful publish. Existing Sport and LowState cardinality gates remain
unchanged.

## Signed contract

The exact schema is `robot-scope.sport-request-evidence.v1`, scoped to one
Bridge process lifetime. It exposes bounded cumulative counts for published,
StopMove, Move, zero Move, non-zero Move, malformed Move, allowlisted action
and unknown requests; last API ID and age; and cumulative maximum absolute
`x`, `y` and `z` Move axes.

It also exposes a monotonically increasing process-local motion-run ID. A run
begins on the first successfully published bounded non-zero Move after an
inactive period and ends on StopMove or another API class. Per-run non-zero
Move count and maximum absolute axes let a supervised C4B run be separated
from earlier process activity without resetting or mutating the recorder.

The dashboard rejects unknown fields, inconsistent counts, invalid types,
non-finite values, values outside the unchanged Bridge hard limits, and
inconsistent motion-run state. Authenticated evidence containing a malformed
Move or unknown API makes Bridge readiness false. Absence remains compatible
only for rolling deployment; C4B itself must treat absent evidence as a hard
block.

## Preserved safety boundaries

- Go2 Bridge limits remain 0.30 m/s linear X, 0.20 m/s linear Y and 0.50 rad/s
  angular Z.
- The 200 ms command watchdog, LowState freshness, signed transport, epoch,
  replay protection, exclusive lease, deadman and exact-zero behavior are
  unchanged.
- Sport publisher/subscriber and LowState publisher cardinality are unchanged.
- Strict wireless `/utlidar/robot_odom` 500 ms source-age and 100 ms
  future-skew guards are unchanged.
- C4 readiness and stable-READY requirements are unchanged.

## Hardware-free acceptance

The focused tests must prove:

1. evidence is recorded only after the existing Sport publisher call;
2. the recorder has no ROS/control authority dependencies;
3. StopMove, zero Move, bounded non-zero Move, allowlisted action, malformed
   Move and unknown API classifications are exact and bounded;
4. signed evidence is strictly validated, projected through the public API and
   malformed/unknown evidence fails readiness closed;
5. status without the optional field remains readable during rolling
   deployment, while the C4B runbook explicitly blocks on absence.

## Remaining hardware gates

Do not restart either Jetson service under this software-only change. Before a
new goal attempt:

1. create an immutable clean release and deploy it to the external and robot
   Jetsons using the existing reversible release procedure;
2. restart only the separately approved services, beginning with the local
   Bridge while the robot is stationary and ending with the dashboard;
3. prove authenticated READY, fresh LowState and unchanged `1/0/10/11` Sport
   publisher classification with exactly one Sport subscriber;
4. prove the control API exposes a valid evidence snapshot, malformed and
   unknown counts are zero, the last request is StopMove, and no non-zero run
   is active;
5. rerun C2 NG0, lease-free C3 and stable C4 pre-goal gates;
6. display the exact map, revisions, start, route and clearance, then stop for
   a new one-shot initial-pose confirmation and a separate new C4B goal
   approval.

The external DDS observer used in the blocked attempt must not be started
again. The earlier approval is consumed and cannot be reused.

## Stationary deployment result

The exact commit
`47b9151baaae3e919bdd806ad34a7a8f01fae044` was deployed on 2026-09-03.
The Git archive SHA-256 was
`98c4fcb5fdab91cb8388a743a909f5715ec48fe9a83ae3bd5077236604f99bf9`.
Both Jetsons independently verified that hash before extraction, and the four
changed runtime Python files matched the local commit byte-for-byte.

| Host | Active release | Preserved rollback |
| --- | --- | --- |
| external Jetson | `/home/jetson_orin_nano/releases/robot-scope/47b9151` | release `1164553`, symlink and private environment backup |
| robot Jetson | `/home/unitree/releases/robot-scope/47b9151` | release `140db78` and rollback symlink |

Neither old/dirty development checkout was pulled, reset, cleaned or modified.
The robot-side service resolves directly through the new release symlink. The
external private `ROBOT_SCOPE_DIR` and live process working directory resolve
to the new release. Its root-owned systemd drop-in still names the old
`1164553` launcher path; the old and new supervisor and runner hashes are
identical, and the runner executes the new Python package and profile selected
by the private release pointer. Therefore `1164553` must not be removed until
that drop-in is updated in a separately authorized root-maintenance window.

The robot-side Bridge was stopped, its release pointer changed atomically and
then started. The external dashboard was restarted only after Bridge recovery.
No mapping, localization, navigation, goal, lease, ARM, deadman or non-zero
command was started during deployment.

Five consecutive one-second dashboard samples produced the same safety state:

| Field | Result |
| --- | --- |
| Control / Bridge | available, authenticated and READY |
| Sport cardinality | one subscriber; one Robot Scope publisher; zero foreign named; ten trusted anonymous Unitree; eleven total |
| LowState | exactly one publisher; observed age 1 ms |
| Lease / deadman / command | no lease; released; exact `(0.0, 0.0, 0.0)` |
| Evidence schema | `robot-scope.sport-request-evidence.v1`, `bridge_process` |
| Evidence counts | published/StopMove advanced `252/252` through `260/260`; every Move/action/malformed/unknown count remained zero |
| Last request | API 1003 StopMove; observed age 199-399 ms |
| Motion run | ID 0, inactive, zero non-zero Move count and zero maxima |
| Navigation | session, pipeline and goal idle; localization-only session inactive |

Robot-side ROS graph inspection, which did not subscribe to the Sport topic,
independently reported eleven publishers and one subscriber. The active Bridge
process used the new release profile and retained the expected ten anonymous
Unitree-publisher baseline.

## C2 NG0 stationary revalidation

The operator separately approved the next C2 stationary no-goal gate on
2026-09-03. The external dashboard was switched reversibly to
`go2-xt16-wireless-competition-fastlio` using a mode-0600 private-environment
backup. The clean `47b9151` release remained active on both Jetsons. The exact
inputs were managed map `map_20260902_161903_edited`, map ID
`f292601e2c8b269eb635cb0f`, map revision
`7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93`,
and the competition profile's active parameter revision
`4327ec7817bbb226bf4a16ca4f64e0d73eeee3dc150c8947c206fc56172388ad`.
An initial request using the pre-restart `go2-safe` revision failed closed with
HTTP 409 before creating an owner; the active revision was then read back and
pinned without changing any parameters.

The lease-free localization-only owner reached `waiting_initial_pose` with
`initial_pose_count=0`, `goal_allowed=false`, `motion_allowed=false`, goal
`idle`, and zero non-zero raw-command observations. To preserve the original
C2 command-isolation contract and avoid creating the extra Sport subscriber
that blocked the earlier C4B attempt, the robot-side Control Bridge was stopped
for the checker interval. Its process and Sport path were absent before the
first checker invocation. No navigation command bridge was launched.

The exact prelocalization checker passed 12/12 sequential samples, with five
seconds between samples. Every sample reported
`localization=WAITING_FOR_INITIAL_POSE` and `raw_command=quiet`, with the fixed
Nav2 children, lifecycle state, one scan publisher, one FAST-LIO odometry
publisher, one canonical controller-odometry publisher, fresh samples and
`odom -> base_link` present. The final stationary health snapshot recorded:

| Metric | Result |
| --- | --- |
| Controller odometry | 10.004759 Hz raw; mean period 0.099952 s |
| Period distribution | median 0.100087 s; p95 0.110012 s; max gap 0.124399 s |
| PointCloud | 9.998 Hz; age 0.0522 s |
| Odometry / TF age | 0.0437 s / 0.0417 s |
| FAST-LIO points | 16,000 input; 14,304 accepted |
| Control state | no lease; deadman false; exact `(0.0, 0.0, 0.0)` |
| Localization / goal | initial pose zero; goal idle; no motion authority |

Localization-only stop then reverse-cleaned its Nav2 and mapping owners. The
session, pipeline and goal returned idle; `/Odometry`, `/scan` and the private
raw command each had zero publishers, and the competition controller-odometry
topic and map topic were absent. The established preview policy reacquired only
the XT16 preview path. The private environment was restored to
`go2-xt16-wireless`, the dashboard restarted from `47b9151`, and the navigation
parameter view returned the `go2-safe` revision
`194c9c18648f9201df464802884022184095422d1b0b91e6d9a75917c9519d77`.

That dashboard restart automatically started the robot-side Control Bridge,
confirming the requested lifecycle behavior despite the unit itself remaining
systemd-disabled. The final signed snapshot was authenticated-ready with fresh
LowState, unchanged `1/0/10/11` Sport cardinality, 21/21 StopMove evidence,
zero Move/action/malformed/unknown evidence, no active motion run, no lease,
deadman false and exact-zero command. The XT16 preview relay was active; the
wireless IMU and odometry senders were inactive.

The post-run documentation verification passed the dependency-complete Python
suite 1007/1007, the JavaScript suite 270/270 and `git diff --check`. The host
Python 3.13 command ran 1003 tests but had one environment-only import error
because that interpreter does not have the declared FastAPI dependency; the
same test and complete suite passed in the repository virtual environment.

## Gate status after deployment

| Gate | Status |
| --- | --- |
| Exact clean source archive and hashes | `PASS` |
| Reversible release install on both Jetsons | `PASS` |
| Stationary Bridge restart and recovery | `PASS` |
| Signed evidence public projection | `PASS` |
| Unchanged Sport/LowState cardinality | `PASS` |
| No lease, deadman, non-zero command or navigation owner | `PASS` |
| C2 NG0 rerun | `PASS` — 12/12 stationary prelocalization checks; initial pose, goal, lease and motion absent |
| Lease-free C3 initial pose | `PASS` — fresh exact confirmation, one publication, 60/60 READY localized samples, reverse cleanup |
| Normal C4 pre-goal session | `NOT RUN` |
| C4B goal or robot motion | `NOT RUN — requires a new exact route and motion approval` |
