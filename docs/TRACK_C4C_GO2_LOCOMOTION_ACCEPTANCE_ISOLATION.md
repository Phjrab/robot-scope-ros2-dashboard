# Track C4C Go2 locomotion acceptance isolation

Date: 2026-09-05

Status: `HARDWARE-FREE GATE COMPLETE — STOCK-1 NOT AUTHORIZED`

This is a checkpoint report, not a motion acceptance report. No C4C stock
motion, Bridge micro-probe, Nav2 goal, lease, ARM, deadman or non-zero command
has been executed. Items that require physical evidence remain `NOT_RUN` or
`BLOCKED`; no locomotion root-cause class has been selected.

## 1. Repository and deployment identity

| Item | Audited value |
| --- | --- |
| Repository baseline HEAD | `fa717cf32d4495692d9c57a9fb5f294c6a31ac8a` |
| `origin/main` at C4C audit | `fa717cf32d4495692d9c57a9fb5f294c6a31ac8a` |
| Worktree before C4C | clean, `main...origin/main` |
| C4C change set before publication | focused C4C-only implementation, tests and documentation |
| Startup-zero correction | present at repository baseline HEAD |
| Latest CI at audit | run `33862858679`: Ubuntu 22 functional job passed; overall failed in the Ubuntu 24 packaging-audit job when the remote npm audit endpoint rejected the dependency tree |
| Last fully green predecessor | `f83f3fff08f0280954839f4e5b87110f314c6271` |

Deployment was checked independently of Git metadata:

| Host | Audited production state |
| --- | --- |
| external Orin `192.168.50.10` | `robot-scope.service` active/enabled; process cwd `/home/jetson_orin_nano/releases/robot-scope/f83f3ff`; dashboard release resolves to `f83f3fff08f0280954839f4e5b87110f314c6271` |
| robot-side Orin `192.168.50.30` | `robot-scope-control-bridge.service` active/enabled; process cwd `/home/unitree/releases/robot-scope/f83f3ff`; XT16 relay active/enabled |
| both hosts | wireless IMU/odometry sender/receiver inactive/disabled at audit |

The external development checkout was old and dirty at `72e39c3`. It was not
used as release evidence and was not modified. The external dashboard process
also carried a stale `ROBOT_SCOPE_GIT_COMMIT` environment value while its
actual cwd was the `f83f3ff` release. Process cwd and immutable release
fingerprints are therefore authoritative; that stale environment value is not.

Both production hosts still run `f83f3ff`. The startup-zero correction at
`fa717cf` and all C4C diagnostics/supervisor work are **not deployed**. The old
release is not eligible for a C4C live probe because it cannot provide the new
authoritative accepted-command evidence.

Any future C4C candidate must be installed in an immutable release directory
whose basename is the complete 40-character lowercase commit SHA, and each
service process cwd must resolve to that same directory. The existing
seven-character `f83f3ff` directory convention cannot satisfy the live probe's
release-identity gate and must not be reused for that deployment.

After the robot was powered back on, a final read-only audit at
`2026-09-04T23:35:35Z` reconfirmed the same immutable release on both hosts.
The external dashboard and robot-side Bridge were active, but no deployment,
service transition or control mutation was performed.

## 2. Previous C4B evidence

| Evidence | Recalculated result |
| --- | --- |
| Goal submissions | exactly 1 |
| Signed Move requests | `+59`, all 59 non-zero |
| Maximum signed x/y/yaw | `0.0291743403 / 0 / 0.00428817545` |
| Motion-run duration | approximately 3.0 s |
| Bridge motion run | ID 1, final inactive |
| Final signed request | API 1003 StopMove |
| SportModeState | fresh `mode=0`, `gait_type=0`, `error_code=100` |
| FAST-LIO pose | millimetre-scale fluctuation only; no sustained forward displacement |
| Goal feedback | startup `0.000`, then `0.275`, then `0.225` m remaining |
| First health fault | `GOAL_PROGRESS_TOO_LOW` at 3.038 s; sensor, TF and cardinality remained healthy |
| Physical observation | no forward movement; stop confirmed by the operator |

The current repository fixes the provisional startup `0.000` accounting bug.
That correction explains a false progress baseline and early abort; it does
not explain why the Go2 did not walk after the signed Move requests.

## 3. Official Unitree contract

The installed robot-side `unitree_ros2` source was inspected at
`3ff13ea08ec619496c2651fd21b172f7958dd5a5`. Confirmed and unconfirmed facts
are kept separate:

| Contract item | Result |
| --- | --- |
| Move API | confirmed API ID `1008`, JSON fields `x`, `y`, `z` |
| StopMove API | confirmed API ID `1003` |
| SportModeState fields | confirmed mode, gait type, position, velocity, yaw, foot state and error fields |
| documented enum references | mode 0 idle/default stand, mode 3 locomotion, gait 0 idle, gait 1 trot |
| Move reply semantics | confirmed fire-and-forget in the inspected official path; `/api/sport/response` is not a per-Move execution acknowledgement |
| automatic posture/mode call prerequisite | no official evidence that C4C should automatically call StandUp, BalanceStand, FreeWalk or SwitchJoystick; those calls remain prohibited |
| `/sportmodestate` versus `/lf/sportmodestate` firmware-specific authority | `UNKNOWN`; installed Robot Scope profile selects `/sportmodestate`. Before a supervised observation, a separate graph check must establish which allowlisted alias is authoritative; the observer itself only enforces a stable publisher count of 1–4 on the selected topic |
| SDK2 lease meaning for this deployed firmware/path | `UNKNOWN` as a Go2 body-acceptance explanation; C4C does not introduce an SDK2 client |
| firmware v1.1.15 gait-entry/deadband threshold | `UNKNOWN` |
| firmware/app/remote ownership arbitration | `UNKNOWN` |
| `error_code=100` meaning | `UNKNOWN`; no interpretation is inferred |
| whether the body accepted the previous 59 Move requests | `UNKNOWN`; publication and dashboard-to-Bridge acknowledgement do not prove execution |

The user-provided platform identity is Go2 EDU hardware v2.0, robot firmware
v1.1.15 and Unitree Go app v2.0.0-8031e. No response-topic observer,
request-topic observer, direct ROS publisher, SDK2 client or official motion
example was added.

## 4. Stock baseline

`NOT_RUN`.

STOCK-1 requires the Bridge to complete StopMove cleanup and become inactive,
Nav2 and every Robot Scope lease to remain inactive, the robot to be standing
in a clear corridor of at least 0.40 m, a physical remote/E-stop and safety
operator to be ready, and only the read-only SportModeState observer to run.
After those facts are shown, a new confirmation is required for one
human-operated 0.10–0.20 m forward attempt. Codex will not generate the stock
motion command.

## 5. Bridge probe results

| Probe | Physical x target | Fixed window | Conservative maximum predicted travel | Result |
| --- | ---: | ---: | ---: | --- |
| MP-030 | 0.03 m/s | 0.70 s | 0.0285 m | `NOT_RUN` |
| MP-050 | 0.05 m/s | 0.70 s | 0.0475 m | `NOT_RUN` |
| MP-080 | 0.08 m/s | 0.70 s | 0.0760 m | `NOT_RUN` |
| MP-100 | 0.10 m/s | 0.70 s | 0.0950 m | `NOT_RUN` |

Each live probe remains individually gated by STOCK-1 PASS and a fresh
confirmation. No probe may retry or advance automatically, and the ladder
must stop after the first physical success.

## 6. Mode, gait and error changes

The only live values currently available are from the preceding C4B run:
`mode=0`, `gait_type=0`, `error_code=100`, with no recorded transition during
the command window. C4C S0, S1 and STOCK-1 observations are `NOT_RUN`, so
SportModeState authority and time-to-gait are not yet established.

The new read-only observer has three fixed modes: S0 for 10 seconds, S1 for
10 seconds and STOCK-1 for 20 seconds. It prints `OBSERVER_READY` only after
publisher discovery is stable and one valid first sample has been retained;
the fixed observation clock starts at that point. Live evidence is `PASS`
only when:

- the fixed observation duration completes;
- no invalid sample is rejected;
- sample count is at least 10 and rate is at least 5 Hz;
- initial sample age, maximum inter-sample gap and final sample age are each
  at most 0.5 s;
- publisher count remains stable, non-zero and within the fixed range 1–4.

It records the first mode-or-gait transition, first separate mode and gait
transition times, and the first body-velocity sample above the 0.01 m/s
candidate threshold online. The threshold remains explicitly provisional
until S0 noise is measured. Raw samples and transitions are bounded; the
result is written as a new private `0600` JSON file under an owned `0700`
directory. Evidence-quality failures sampled after `OBSERVER_READY` are
preserved with `status=FAIL`, and the observer returns a non-zero exit status.
Discovery, publisher-count changes or an invalid first sample before READY
abort before evidence-file creation and must be retained by the supervising
terminal/session log.

## 7. Actual movement evidence

C4C physical movement: `NOT_RUN`.

The preceding C4B operator observation was no movement, and its FAST-LIO
variation was below the 5 mm significance boundary. That evidence does not
replace the required C4C stock baseline or a fixed Bridge micro-probe. A future
movement decision must combine the safety operator's observation with
SportModeState/position or validated localization displacement.

## 8. Threshold interval

No gait-entry threshold interval has been established.

- prior highest observed non-moving signed x: `0.0291743403 m/s` in the Nav2
  C4B chain;
- highest confirmed non-moving fixed Bridge probe: `UNKNOWN`;
- lowest confirmed moving Bridge probe: `UNKNOWN`;
- uncertainty interval: `UNKNOWN`;
- time-to-gait and time-to-motion: `UNKNOWN`.

The C4B value is not treated as a firmware threshold because it included Nav2
command shaping and no stock/manual Bridge comparison exists yet.

## 9. Root-cause class

No specific root-cause class is selected. The Section 16 checkpoint value is:

```text
ROOT_CAUSE=UNRESOLVED
```

The next minimum discriminating evidence is STOCK-1. If it passes, MP-030 may
be proposed under a separate approval. No Nav2 parameter or safety threshold
is changed without that evidence.

## 10. Changed code

All changes remain local and undeployed at this checkpoint:

- ControlManager now reports its actual last emitted command instead of an API
  layer fabricating zero when no authoritative command was available.
- Go2ControlBridge exposes bounded accepted-command state and a bounded
  command acknowledgement. Raw source identity and epoch remain private; the
  external API projects only sequence, type, age and a server-computed
  `source_matches_dashboard` boolean.
- the Bridge signs a path-derived exact 40-character release identity. The
  dashboard validates and projects it, and a live probe requires it to equal
  the dashboard process release. Environment metadata is never accepted as
  release authority.
- a readiness loss now clears an accepted drive and force-stops immediately,
  including the pre-first-Move interval while an idle Stop is throttled. The
  200 ms watchdog and 500 ms idle Stop cadence are unchanged.
- while an accepted dashboard command is arriving, the Bridge publishes its
  signed acknowledgement on the next existing 50 ms tick; idle signed status
  retains its 250 ms cadence and command/watchdog timing is unchanged.
- `scripts/observe_go2_locomotion_state.py` provides fixed, read-only S0/S1/
  STOCK-1 observation with the evidence-quality gates described above.
- `scripts/run_go2_locomotion_micro_probe.py` is default-dry-run and exposes
  only MP-030/050/080/100. It has no free velocity, duration, host, port, topic
  or output path and can use only the existing signed dashboard control path.
  It rechecks every exclusion and exact zero after ARM but before motion, sends
  only one first frame while waiting at most 150 ms for signed acceptance,
  never catches up missed frames, enforces 5 mm pre-command drift and 0.10 m
  observed-travel bounds, immediately aborts if the opaque baseline error code
  changes, and rechecks full Bridge readiness plus all Navigation, Mission,
  mapping, competition-mode and lease exclusions during cleanup. Mode and gait
  transitions remain recorded evidence rather than inferred acceptance.

No `/api/sport/request` publisher/subscriber, direct Sport publisher, SDK2
motion path, Nav2 goal path, automatic posture call or global minimum velocity
floor was added. HMAC, epoch, sequence, 200 ms watchdog, LowState/cardinality,
lease, deadman, clamps, exact-zero cleanup, the 3 s stall guard, 0.01 m/s
progress guard and 5 mm significance guard were not weakened.

## 11. Tests

Current, directly rechecked evidence against this worktree:

| Check | Exact result |
| --- | --- |
| C4C observer and supervisor focused suite | 47 tests, all passed |
| control/Bridge/transport/API plus C4C focused suite | 138 tests, all passed |
| complete Python suite with coverage | 1,106 tests, all passed; total branch coverage report 69% |
| JavaScript unit suite | 270 tests, all passed |
| Cockpit JavaScript suite | 86 tests, all passed |
| Playwright hardware-free browser suite | 32 tests, all passed |
| Ruff on configured `robot_dashboard scripts` scope | passed |
| configured mypy | passed, four files checked |
| Python compilation and shell syntax | passed |
| tracked-source secret scan | passed |
| frontend syntax scan | 53 modules passed |
| `git diff --check` | passed |

The focused supervisor matrix covers active prior motion, lease/source
exclusion, stale or mismatched drive acknowledgement, non-advancing sequence,
output overshoot, scheduler lateness, invalid ARM response, explicit-zero and
release failure, disarm/software-STOP fallback, error-code change, cleanup
status or final-exclusion loss, final evidence retention, exactly one run and
no retry. An old idle Stop acknowledgement may exceed 750 ms
because the Bridge-owned 500 ms StopMove heartbeat is not an incoming command;
runtime drive acknowledgement still has the unchanged 750 ms freshness gate.

The repository virtual environment is the authoritative test environment.
The exact workflow command `python3 -m unittest discover -s tests -v` was also
rechecked. It ran 1,102 tests and ended with one import error because the host
Python 3.13 environment lacks `fastapi`; the repository virtual environment
passes the corresponding suite. This remains a host baseline dependency issue,
not a C4C regression.

## 12. Service, process, lease and final safety state

The latest read-only deployment audit, repeated after the robot was powered
back on, found:

- external dashboard active on the immutable `f83f3ff` release;
- robot-side Control Bridge active on the immutable `f83f3ff` release;
- Navigation pipeline, localization-only session and goal idle;
- no Navigation or manual lease;
- dashboard command exact zero, deadman released and Bridge motion run inactive;
- latest signed request StopMove;
- authenticated Bridge, LowState and SportModeState fresh at audit;
- request cardinality one subscriber, one owned publisher, zero foreign named
  publishers and the expected ten bare publishers;
- Bridge process-lifetime evidence at the final audit showed 322 StopMove,
  zero Move and zero action requests; `mode=0`, `gait_type=0` and
  `error_code=100` remained observational values with no inferred meaning.

The deployed release cannot expose the new Bridge accepted-command field, so
an authoritative deployed `accepted_command=[0,0,0]` has **not** been claimed.
The last C4B operator report confirmed no motion and stop, but C4C has not yet
obtained a fresh physical-state confirmation. No C4C service, process, lease,
command or robot state was mutated, so there is no C4C live session residue to
clean up. No Nav2 goal was sent.

The user later powered the Go2 back on. Only the read-only final audit above
was performed after that update. No deployment activation, service restart,
stationary observer capture, lease, ARM, deadman, non-zero command or motion
test was attempted. A fresh physical stopped/standing confirmation was not
provided, so no physical state is inferred from telemetry.

## 13. Next prompt

No C4E prompt has been created. The hardware-free supervisor tests are green.
The next preparation step is a clean exact-release deployment and stationary
S0/S1 capture; the next permitted motion gate is then the exact STOCK-1
procedure and a fresh user confirmation. MP-030 can be
proposed only after STOCK-1 PASS; every higher probe requires its own approval.

`docs/TRACK_C4E_SUPERVISED_NAV2_RETRY_PROMPT.md` may be written only after C4C
has evidence for a root-cause class and a characterized effective command.
This C4C work does not send a Nav2 goal.

## 14. Rollback

Repository rollback should use a normal revert of the focused C4C commit,
whose published SHA is recorded in the Git/CI completion report. The baseline
before this change is `fa717cf32d4495692d9c57a9fb5f294c6a31ac8a`.
Deployment rollback, if a future clean C4C release is activated, must
atomically restore the prior
immutable release on each affected host and then verify process cwd, latest
signed StopMove, exact zero, deadman released and no lease. The dirty external
development checkout must never be reset or used as a deployment or rollback
target.

At this checkpoint no C4C deployment or service mutation occurred, so the
production rollback action is `NOT_REQUIRED`.

## 15. Acceptance status

| Gate | Status |
| --- | --- |
| REPOSITORY_AUDIT | PASS |
| DEPLOYMENT_AUDIT | PASS |
| STARTUP_ZERO_FIX | PASS |
| OBSERVER_SOFTWARE | PASS |
| STATIONARY_BODY_BASELINE | NOT_RUN |
| STOCK_CONTROLLER_BASELINE | NOT_RUN |
| MP_030 | NOT_RUN |
| MP_050 | NOT_RUN |
| MP_080 | NOT_RUN |
| MP_100 | NOT_RUN |
| GAIT_ENTRY_THRESHOLD | BLOCKED |
| SPORT_MODE_AUTHORITATIVE | BLOCKED |
| GO2_REQUEST_ACCEPTANCE | BLOCKED |
| NAV2_SCALING_ROOT_CAUSE | BLOCKED |
| SOFTWARE_CORRECTION | NOT_RUN |
| STATIONARY_SOAK | NOT_RUN |
| NAV2_GOAL | NOT_RUN |
| ROBOT_MOTION | NOT_RUN |
| CLEANUP | PASS |

`STARTUP_ZERO_FIX=PASS` is repository-level only; deployment remains on the
pre-fix `f83f3ff` release. `CLEANUP=PASS` is scoped to the fact that C4C has
performed no live mutation and left no session, lease or command residue.

## 16. Final decision

```text
ROOT_CAUSE=UNRESOLVED
```

This value records insufficient evidence, not a diagnosis. The next minimum
motion probe is STOCK-1 after clean deployment and stationary S0/S1 evidence.
No C4E prompt, software correction, Nav2 retry or motion escalation is
authorized by this checkpoint.
