# Hardware acceptance and fault-injection procedure

This document is the Phase 11 acceptance contract for Robot Scope. It separates
hardware-free CI evidence from observations that require the deployed Ubuntu ROS
host, Go2, XT16, control bridge, and an operator in the test area. The acceptance
recorder does not modify a service, publish a ROS message, start mapping or
navigation, clear an E-stop, write a map or dataset, or send a robot command.

At the time this procedure was added, the robot was not available. The tooling
and hardware-free regression tests are complete; actual Go2/XT16 rows must remain
`BLOCKED` or `NOT_RUN` until a later, explicitly requested supervised session.
Do not convert missing hardware into a passing result.

## Result model

Every row uses exactly one status:

| Status | Meaning |
|---|---|
| `PASS` | The fixed expected condition was observed during this run. |
| `FAIL` | A check ran and observed an unsafe or incompatible condition. |
| `BLOCKED` | A prerequisite or live source was unavailable, so the condition could not be established. |
| `NOT_RUN` | The check was deliberately not attempted in this run. |

Each JSON result includes the check ID and timestamp, fixed expected condition,
bounded observed result, non-secret evidence, whether a manual action occurred,
and its safety impact. Reports include the exact Git commit and distinguish
`read_only` from `supervised_record` scope. They never contain the bridge key,
control or navigation lease tokens, authorization data, full environment dumps,
raw child output, arbitrary command lines, or absolute operational paths.

Reports are written as paired files:

```text
runtime/reports/acceptance-<UTC timestamp>.json
runtime/reports/acceptance-<UTC timestamp>.md
```

The directory is forced to mode `0700` and each report to `0600`. `runtime/` is
Git-ignored. Review and redact a copied report before sharing it outside the
deployment team; never commit the runtime copy.

## Read-only run

Run on the deployed Ubuntu ROS host from the repository root:

```bash
python3 scripts/robot_scope_acceptance.py --mode go2-nav
```

The exit status is `0` when no check is failed or blocked, `1` when at least one
check is `FAIL`, `3` when there is no failure but at least one check is
`BLOCKED`, and `2` for invalid recorder configuration. `NOT_RUN` alone does not
make the command fail.

The only configurable network value is a numeric loopback dashboard port:

```bash
python3 scripts/robot_scope_acceptance.py --mode go2-nav --dashboard-port 8088
```

The host is fixed to `127.0.0.1`. The recorder permits only bounded `GET`
requests to its fixed endpoint allowlist. It runs the existing read-only doctor,
reads the current Git commit, and uses fixed `systemctl show` argument vectors
for only `robot-scope.service` and
`robot-scope-control-bridge.service`. It does not accept a URL, unit name,
executable, shell fragment, ROS topic, runtime artifact path, or arbitrary
evidence string from the operator. `--project-dir` and `--env-file` retain the
existing doctor's installation-root inputs; the project root must identify a
Robot Scope checkout and reports still use its fixed `runtime/reports` child.

### Fixed read-only coverage

| Area | Acceptance evidence |
|---|---|
| Platform | Ubuntu 22.04, supported architecture, Python environment, ROS 2 Humble, RMW/domain, fixed config and executable presence through `robot_scope_doctor.py` |
| Go2 network | Dedicated interface/address and Cyclone DDS setup from the doctor; live agent/interface/pinned-target/reachability from `/api/v1/health` |
| Control graph | `/lowstate` one-publisher rate/freshness; signed bridge authentication and age; exact sport/LowState graph cardinality |
| XT16 | Hesai packet-path continuity represented by the driver's `/lidar_points`, plus `/velodyne_points` one-publisher rate, jitter, and freshness bounds |
| Localization | `/Odometry` one-publisher rate/jitter/freshness and, when navigation is running, runtime scan/odometry/TF readiness |
| Nav2 | Fixed Humble executables and parameter file through the doctor; runtime state from the navigation API |
| Maps | Opaque managed-map catalog is readable and contains a supported 2D map before Nav use |
| Storage | Dataset free space exceeds its configured reserve plus one bounded manifest; configured dataset, map, mapping-log, ROS-log, and report directories are real, non-writable by group/others, and private where required |
| Services | Both fixed systemd units are observed with load, enablement, active/sub-state, result, and restart count; no enable/start/stop occurs |

The Localization row is paired with the Phase 14
`navigation.localization_health` check. That row records the explicit state
and reason plus bounded cloud/odometry rates and ages, TF age and advancing
fresh-sequence count from `GET /api/v1/navigation`. `READY` is accepted only
after distinct fresh cloud and odometry sequences; cached status cannot pass.
Before the supervised initial-pose step, `INITIAL_POSE_REQUIRED` remains
`BLOCKED`, not a false pass. See
[ARCHITECTURE_PHASE14.md](ARCHITECTURE_PHASE14.md).

Topic-rate thresholds are acceptance criteria, not runtime timeout changes:

| Topic | Minimum rate | Maximum observed age | Maximum jitter |
|---|---:|---:|---:|
| `/lowstate` | 10 Hz | 0.75 s | 100 ms |
| `/lidar_points` | 4 Hz | 1.0 s | 300 ms |
| `/velodyne_points` | 4 Hz | 0.5 s | 300 ms |
| `/Odometry` | 5 Hz | 1.5 s | 200 ms |

Arrival metrics alone do not prove a timestamp domain. Therefore the timestamp
and TF row passes only while the navigation runtime is running and its existing
strict scan, odometry, and TF readiness gates are true. If navigation is idle,
that row is `BLOCKED`, not inferred from cached topic data. The recorder does not
widen the bridge, control, FAST-LIO, or navigation freshness limits.

The recorder does not open a raw UDP packet sniffer. Fresh `/lidar_points` from
the fixed Hesai driver is the product-boundary evidence that the packet path is
producing complete clouds. Packet-level investigation below that boundary uses
the existing private host tooling only when a failed or blocked row requires it;
it is not silently substituted with a passing cloud result.

## Hardware-free CI versus hardware acceptance

CI proves parser bounds, report durability and redaction, GET-only behavior,
fixed command/endpoint allowlists, strict supervised opt-in, and fail-closed
status classification. It cannot prove link carrier, DDS discovery, real sensor
rates, physical stopping distance, watchdog behavior, process shutdown on the
Jetson, or map/dataset writes on the deployment filesystem.

Before signing off hardware, require all of the following to refer to the same
run and commit:

1. The full Python and JavaScript suites are green for that commit.
2. The read-only acceptance report has no unexplained `FAIL` or `BLOCKED` row.
3. The operator records each required supervised scenario separately.
4. No safety timeout, speed limit, graph-cardinality rule, map revision fence,
   or filesystem reserve was changed to make acceptance pass.

## Supervised scenario recording

List the fixed scenario IDs without creating a report:

```bash
python3 scripts/robot_scope_acceptance.py --list-supervised-scenarios
```

The recorder never performs the action. The operator uses the existing dashboard
and approved lab procedure, then records exactly one result per invocation. A
single-scenario run ensures a failure cannot automatically advance to another
motion or fault test.

Every supervised record requires all five explicit flags:

- `--allow-supervised-motion`
- `--confirm-estop-ready`
- `--confirm-clear-area`
- `--confirm-low-speed-limits`
- `--confirm-operator-present`

Example after the operator has safely completed the named procedure:

```bash
python3 scripts/robot_scope_acceptance.py --mode go2-nav \
  --allow-supervised-motion \
  --confirm-estop-ready \
  --confirm-clear-area \
  --confirm-low-speed-limits \
  --confirm-operator-present \
  --supervised-scenario supervised.manual_short_stop \
  --supervised-result PASS
```

Literal `PASS`, `FAIL`, `BLOCKED`, and `NOT_RUN` are the only result values.
There is no free-form evidence argument, preventing secrets or raw diagnostics
from being copied into the report.

### Fixed scenario catalog

| ID | Operator procedure and expected fail-stop behavior |
|---|---|
| `supervised.manual_short_stop` | ARM at the existing low limit, make one short deadman-held move, release, verify stop, then DISARM. |
| `supervised.browser_disconnect_watchdog` | During minimal controlled motion, close the controlling page and verify bounded stop and lease release. |
| `supervised.dashboard_process_stop` | While stationary and DISARMED, use the approved lifecycle control and confirm final stop occurs before transport teardown. |
| `supervised.control_bridge_stop` | While stationary and DISARMED, stop through the dashboard and confirm signed readiness disappears and no motion continues. |
| `supervised.stale_lowstate` | Using the approved isolated fault setup, interrupt LowState and confirm readiness/lease fail closed. |
| `supervised.foreign_sport_publisher` | Introduce only the fixed lab test publisher and confirm exact graph cardinality blocks readiness. |
| `supervised.navigation_start_stop` | Start with a verified map but send no goal; confirm readiness and STOP cleanup/lease release. |
| `supervised.mapping_warmup_cancel` | Start Nav from idle localization, cancel during warmup, and confirm exact Nav-owned mapping cleanup. |
| `supervised.nav2_child_crash` | With no goal active, apply the approved child-failure procedure and confirm navigation deactivation and exact cleanup. |
| `supervised.xt16_interruption` | With no goal active, interrupt XT16 and confirm freshness loss blocks Nav without replaying stale clouds. |
| `supervised.dataset_shutdown_blocker` | Start a short capture and confirm lifecycle change is blocked until capture is finalized. |
| `supervised.low_disk_rejection` | Use only a bounded approved test volume and confirm map/dataset writes reject before crossing reserve. |

The physical remote must remain in hand during every motion-capable scenario.
Dashboard SOFTWARE STOP is a software latch, not a substitute for the physical
E-stop. The recorder never clears either stop.

## Immediate stop and failure rules

Stop the current scenario and do not continue to the next one when any of these
occurs:

- physical motion differs from the bounded operator command;
- deadman release, browser disconnect, stale LowState, bridge loss, or sensor
  loss does not stop motion within the existing safety contract;
- a foreign publisher is accepted instead of blocking readiness;
- navigation reports a lease after STOP, rollback, or child failure;
- a stale cloud, odometry sample, invalid timestamp domain, or missing TF is
  treated as ready;
- a lifecycle operation bypasses an active dataset, mapping, navigation, lease,
  or action blocker;
- a map/dataset write crosses the configured disk reserve or publishes a
  partial artifact;
- any service enters a restart loop or emits an unhandled traceback.

First use the physical remote/E-stop as required by the lab procedure. Then mark
the current scenario `FAIL`, preserve the non-secret report and relevant private
host logs, return the system to stationary/DISARMED state, and investigate. Do
not clear the E-stop automatically, increase timeouts, loosen cardinality, reduce
disk reserve, bypass exact job/revision fencing, or repeat motion until the cause
is understood.

## Phase 11 completion boundary

The repository-side recorder, documentation, and hardware-free tests complete
the implementable portion of Phase 11. Because the robot is currently
unavailable, the following remain intentionally pending:

- real Jetson Ubuntu/ROS/systemd identity report;
- live Go2, signed bridge, LowState, sport graph, XT16, FAST-LIO, TF and Nav2
  measurements, including the Phase 14 localization-health and calibration
  assistant observations;
- every physical and fault-injection scenario in the fixed catalog.

Those rows must be completed only after the user explicitly requests the later
robot-connected validation. Phase 12 work must not be inferred from this
procedure.
