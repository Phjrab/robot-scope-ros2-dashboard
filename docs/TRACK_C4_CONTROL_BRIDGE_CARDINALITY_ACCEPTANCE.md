# Track C4 prerequisite — Go2 v1.1.15 Control Bridge cardinality

Status date: 2026-09-02

```text
ROOT_CAUSE_PASS
STRICT_PROFILE_UPDATE_PASS
HARDWARE_FREE_TESTS_PASS
REPOSITORY_PUBLICATION_PASS
DEPLOYMENT_PASS
STATIONARY_LIFECYCLE_PASS
MOTION_NOT_RUN
```

## Scope

This prerequisite resolves only the Control Bridge graph baseline that blocks
Track C4. It does not start navigation, acquire a lease, ARM, hold deadman,
submit a goal or authorize robot motion. Server velocity clamps, the 200 ms
Bridge watchdog, exact graph equality, foreign named publisher rejection,
fresh LowState and signed transport remain unchanged.

## Evidence and decision

The operator-confirmed Go2 body firmware is v1.1.15. A stationary robot-side
Foxy audit observed the following stable `/api/sport/request` graph:

| Endpoint class | Observed |
|---|---:|
| Robot Scope named publisher | 1 |
| Foreign named publisher | 0 |
| Anonymous Unitree publisher | 10 |
| Total publisher count | 11 |

Five consecutive graph samples retained the same anonymous endpoint GID set.
The repository's previous value of nine predated the firmware update. It made
the Bridge fail closed and publish only periodic API 1003 `StopMove`; the
robot-side observation found no API 1008 `Move` or action.

The active `go2` profile now requires exactly ten anonymous Unitree
publishers. It does not accept a range and does not learn the graph at runtime.
Any value other than ten, any named foreign publisher, a missing own publisher
or an inconsistent total remains not ready.

## Acceptance

| Check | Result | Evidence |
|---|---|---|
| Root cause identified without motion | `PASS` | stable v1.1.15 robot-side graph and fail-closed Bridge status |
| Safety invariants preserved | `PASS` | configuration-only exact baseline change; safety core unchanged |
| Exact-ten regression | `PASS` | focused Bridge/profile tests and complete suites passed |
| Nine/eleven rejection regression | `PASS` | strict mismatch and named-foreign cases remain not ready |
| Focused commit and push | `PASS` | the focused commit containing this record is published on `origin/main` |
| Deploy same commit to external and robot-side endpoints | `PASS` | both active release links resolve to clean `140db78`; both services restarted from that release after explicit approval |
| Stationary authenticated-ready lifecycle | `PASS` | five consecutive samples retained authenticated READY, 1/0/10/11 graph counts, fresh LowState, no lease, released deadman and exact zero |
| C4 short low-speed goal | `NOT_RUN` | requires all C4 gates and separate supervised-motion approval |

## Deployment gate

Do not mark this prerequisite hardware-complete merely because tests pass.
Both endpoints must run the same focused commit. With the robot stationary,
the lifecycle check must show authenticated status, fresh LowState, one Robot
Scope publisher, zero foreign named publishers, ten anonymous Unitree
publishers, eleven total publishers, no lease, released deadman and an exact
zero command. Any mismatch remains `BLOCKED` and no motion may follow.

## Repository verification

- Focused Go2 Bridge tests: 18/18 passed.
- Focused application-configuration tests: 8/8 passed.
- Project virtual-environment Python suite: 981/981 passed.
- JavaScript unit suite: 270/270 passed.
- Frontend syntax: 53/53 modules passed.
- Required host-Python command: 977 tests ran; 976 passed and the existing
  macOS baseline import error remained because the host interpreter lacks the
  declared `fastapi` dependency. The dependency-complete project virtual
  environment passed the same coverage.

## Stationary deployment evidence

After the explicit `APPROVE_C4_CARDINALITY_DEPLOY` approval, the exact
`140db7821d29bcb4e4327989156242732695f094` Git archive was transferred to
both Jetsons. Its SHA-256 was
`73433a653e090045b87a86515f1dc441cd2cf9e966140a3aa72eb0a1a85bfbb0`.
The existing dirty checkouts and prior clean releases were not modified.

The external dashboard and robot-side Bridge now resolve respectively to:

- `/home/jetson_orin_nano/releases/robot-scope/140db78`
- `/home/unitree/releases/robot-scope/140db78`

The first external restart correctly remained fail-closed because its private
`ROBOT_SCOPE_DIR` still pinned the previous release even though systemd ran
the new supervisor. That single private path was updated atomically after an
exact old-value check, its mode remained `0600`, and the dashboard was
restarted. No other private value was displayed or changed.

Five consecutive one-second API samples then reported:

| Field | Value in all five samples |
|---|---:|
| Bridge ready/authenticated | `true` / `true` |
| own / foreign named / anonymous / total publishers | `1 / 0 / 10 / 11` |
| lease active / deadman | `false` / `false` |
| command x / y / yaw | `0.0 / 0.0 / 0.0` |

The same snapshot reported fresh LowState, `navigation=idle`, `goal=idle` and
no localization-only session. Robot-side Foxy graph inspection independently
reported eleven publishers and one subscriber. The Bridge process command
used the new release profile and its startup log required exactly ten
anonymous Unitree publishers. No ARM, deadman, lease, navigation goal or
motion command was issued during deployment or validation.

## Rollback inventory

- External previous release: `92117dd`; its former systemd override is stored
  at `/var/tmp/robot-scope.service.release.conf.pre-140db78`.
- External private environment backup:
  `/home/jetson_orin_nano/.config/robot-scope/control.env.pre-140db78`, mode
  `0600`.
- Robot-side previous release: `c107d87`; its former override is stored at
  `/var/tmp/robot-scope-control-bridge.release.conf.pre-140db78`.

Rollback must restore each host's matching release pointer and configuration
as one reviewed operation; mixing old and new expected counts must remain
fail-closed.
