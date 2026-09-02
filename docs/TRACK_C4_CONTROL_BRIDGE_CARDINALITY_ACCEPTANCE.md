# Track C4 prerequisite — Go2 v1.1.15 Control Bridge cardinality

Status date: 2026-09-02

```text
ROOT_CAUSE_PASS
STRICT_PROFILE_UPDATE_PASS
HARDWARE_FREE_TESTS_PASS
REPOSITORY_PUBLICATION_PASS
DEPLOYMENT_NOT_RUN
STATIONARY_LIFECYCLE_NOT_RUN
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
| Deploy same commit to external and robot-side endpoints | `NOT_RUN` | service deployment is separate from Git publication |
| Stationary authenticated-ready lifecycle | `NOT_RUN` | requires explicit service deployment/restart approval |
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
