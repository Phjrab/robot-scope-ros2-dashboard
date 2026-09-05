# Track C4C Go2 locomotion acceptance isolation

Date: 2026-09-05

Status: `STOCK-1 PASS — MP-030 BLOCKED PRE-COMMAND BY ODOMETRY CLOCK GUARD`

This is a stationary-baseline checkpoint report, not a motion acceptance
report. The C4C release was activated through the fixed service lifecycle,
the S0/S1 read-only observations passed and one human-operated STOCK-1 motion
was observed. MP-030 was authorized and invoked once, but its fixed supervisor
failed closed before lease acquisition because no fresh odometry pose was
available. No Bridge micro-probe motion, Nav2 goal, Robot Scope lease, ARM,
deadman or Robot Scope non-zero command has been executed. Items that require
Bridge movement evidence remain `NOT_RUN` or `BLOCKED`; no locomotion
root-cause class has been selected.

## 1. Repository and deployment identity

| Item | Audited value |
| --- | --- |
| Repository baseline HEAD | `fa717cf32d4495692d9c57a9fb5f294c6a31ac8a` |
| `origin/main` at C4C audit | `fa717cf32d4495692d9c57a9fb5f294c6a31ac8a` |
| Worktree before C4C | clean, `main...origin/main` |
| Published C4C implementation | `e69718ad8e084a219fb171d6aa442f5877543e5f` |
| Deployed observer compatibility fix | `103ed69e43e263020af426c06e6d7bb7d12b4e99` |
| Startup-zero correction | present at repository baseline HEAD |
| Latest CI for deployed commit | run `33933164283`: Ubuntu 22.04/Python 3.10 and Ubuntu 24.04/Python 3.12 both passed, including hardware-free browser E2E |
| Last fully green predecessor | `f83f3fff08f0280954839f4e5b87110f314c6271` |

Deployment was checked independently of Git metadata:

| Host | Audited production state |
| --- | --- |
| external Orin `192.168.50.10` | `robot-scope.service` active/enabled; process cwd `/home/jetson_orin_nano/releases/robot-scope/103ed69e43e263020af426c06e6d7bb7d12b4e99` |
| robot-side Orin `192.168.50.30` | release symlink `/home/unitree/releases/robot-scope/103ed69e43e263020af426c06e6d7bb7d12b4e99`; `robot-scope-control-bridge.service` intentionally inactive/enabled after S1 cleanup; XT16 relay active/enabled |
| both hosts | exact full-SHA release identity matched while both services were active; restart count `0` after activation |

The external development checkout was old and dirty at `72e39c3`. It was not
used as release evidence and was not modified. The external dashboard process
also carried a stale `ROBOT_SCOPE_GIT_COMMIT` environment value while its
actual cwd was the `f83f3ff` release. Process cwd and immutable release
fingerprints are therefore authoritative; that stale environment value is not.

The first exact Git archive for
`e69718ad8e084a219fb171d6aa442f5877543e5f` had SHA-256
`77aab8026fbed0d8bbd5d78a69d653ac6465ff9dbbeae0722dbcf3184a3b5a4b`.
The S0 compatibility follow-up archive for
`103ed69e43e263020af426c06e6d7bb7d12b4e99` had SHA-256
`91f4758e5670b222dc002ec78ae06beaa58884492cf4d338d12ada4b28f5cc29`.
Each hash was independently verified after transfer to both hosts. The
archives were extracted into previously absent full-40-character release
directories; neither dirty development checkout was pulled, reset or used as
a release.

Activation used the required Bridge-first order. The old Bridge emitted its
StopMove cleanup and reached inactive before the robot-side stable symlink was
atomically switched. The fixed dashboard lifecycle then started the new
Bridge, whose process cwd and release identity were verified before the
external dashboard symlink was atomically switched and its service restarted.
Rollback symlinks for the current release preserve `e69718ad`; that release's
rollback links in turn preserve `f83f3fff`.

Post-activation evidence for the initial release at `2026-09-05T00:18Z`
reported Bridge
authenticated/connected/ready, accepted command exactly `(0,0,0)`, dashboard
command exactly `(0,0,0)`, no lease, deadman released, motion run inactive,
one request subscriber, one owned publisher, zero foreign named publishers and
the expected ten bare publishers. The new Bridge had published 279 StopMove,
zero Move and zero action requests. Navigation, localization and goal remained
idle. These are service and telemetry facts; physical standing/stopped state
was then confirmed by the operator before S0/S1.

The first S0 observer invocation rejected the real Foxy fixed-array velocity
field before `OBSERVER_READY`. It wrote no evidence file, created no command
endpoint and did not start S1. Commit `103ed69` narrowly changed only fixed
three-element numeric vector decoding, retaining rejection of strings,
arbitrary iterables, non-numeric, non-finite and out-of-range values. Its full
suite and CI passed before the corrected release was activated on both hosts.

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

## 4. Stationary body-state baseline

The operator confirmed the robot was standing, completely stopped, inside a
clear safety area with the physical remote/E-stop ready and a safety operator
present. Both fixed observations then completed without a command endpoint,
lease, ARM, deadman, non-zero command or Nav2 process.

| Evidence | S0: Bridge inactive | S1: Bridge active, idle |
| --- | ---: | ---: |
| Result | `PASS` | `PASS` |
| Actual duration | 10.000034 s | 10.000238 s |
| Samples / rejected | 2,964 / 0 | 2,947 / 0 |
| Observed rate | 296.398989 Hz | 294.692981 Hz |
| Maximum sample gap | 0.019234 s | 0.018501 s |
| Final sample age | 0.000135 s | 0.001806 s |
| Publisher count min/max | 1 / 1 | 1 / 1 |
| Mode/gait transitions | 0 | 0 |
| First mode/gait/error | `0 / 0 / 100` | `0 / 0 / 100` |
| Last mode/gait/error | `0 / 0 / 100` | `0 / 0 / 100` |
| Maximum vector speed | 0.000001 m/s | 0.000001 m/s |
| Position span x/y/z | 0.000313 / 0.000351 / 0.000005 m | 0.000315 / 0.000277 / 0.000006 m |
| First-to-last x/y/z | -0.000088 / 0.000180 / 0.000001 m | 0.000192 / -0.000143 / 0.000001 m |

Private evidence was retained with file mode `0600` under an owned `0700`
directory:

- `/home/unitree/.robot-scope/locomotion-observations/go2-locomotion-s0-20260905T003647.388421Z.json`
- `/home/unitree/.robot-scope/locomotion-observations/go2-locomotion-s1-20260905T003906.564311Z.json`

For S0, the Bridge completed StopMove cleanup and was inactive before capture.
The request graph remained at the expected ten bare publishers and one
subscriber, with no Robot Scope Bridge publisher. For S1, Bridge preflight
showed the exact release, authenticated/connected/ready state, exact-zero
accepted command, no lease/deadman/motion run, one request subscriber, one
owned publisher, zero foreign named publishers and the expected ten bare
publishers. The Bridge emitted no Move or action request during observation.

Over a separate fixed 10.014758-second S1 idle interval, StopMove count changed
from 213 to 232: 19 requests, or 1.8972 Hz. Move and action deltas remained
zero. The accepted command remained exactly zero and the lease, deadman and
motion run remained inactive. The Bridge was then stopped through the fixed
lifecycle and confirmed inactive, leaving the system ready for STOCK-1.

The measured stationary position variation is below the existing 5 mm
significance threshold. It establishes a low-noise stationary baseline but
does not by itself make SportModeState authoritative for physical movement.

## 5. Stock baseline

`PASS` for stock-controller locomotion, with an operator-distance procedure
deviation recorded separately.

Preflight established exact release `103ed69`, Bridge inactive, Nav2 idle, no
Robot Scope request publisher, ten expected bare request publishers, one
`/sportmodestate` publisher, robot standing, clear corridor, physical
remote/E-stop ready and safety operator present. Codex created no motion
command; the operator used the stock remote.

The first 20-second observer run completed with no remote input because the
operator could not act inside the window. It was retained as valid read-only
no-motion evidence but was not counted as the authorized motion attempt. A
fresh retry instruction then produced the following motion evidence:

| Evidence | STOCK-1 result |
| --- | ---: |
| Observation quality | `PASS` |
| Actual duration | 20.000533 s |
| Samples / rejected | 5,954 / 0 |
| Observed rate | 297.692070 Hz |
| Maximum sample gap | 0.020466 s |
| Final sample age | 0.000122 s |
| Publisher count min/max | 1 / 1 |
| Physical observation | robot moved approximately 0.30–0.40 m and then fully stopped |
| Maximum vector speed | 1.033427 m/s |
| Position span x/y/z | 0.276652 / 0.350337 / 0.013701 m |
| First-to-last x/y/z | -0.272898 / -0.343941 / 0.002611 m |
| First-to-last vector magnitude | approximately 0.439 m |
| Mode/gait/error | remained `0 / 0 / 100`; zero transitions |

Private evidence:

- no-input run: `/home/unitree/.robot-scope/locomotion-observations/go2-locomotion-stock-1-20260905T005420.281355Z.json`
- motion run: `/home/unitree/.robot-scope/locomotion-observations/go2-locomotion-stock-1-20260905T005625.741811Z.json`
- post-motion S0: `/home/unitree/.robot-scope/locomotion-observations/go2-locomotion-s0-20260905T005926.805755Z.json`

The approved target was 0.10–0.20 m. The operator reported intentionally
holding the stock input longer and estimated 0.30–0.40 m of physical travel;
the larger displacement is therefore an operator procedure deviation, not
evidence of autonomous overshoot. The stock-controller locomotion question is
nevertheless answered: the Go2 body can walk through its stock control path.

The post-motion 10-second S0 observation passed with 2,980 samples at
297.988914 Hz, no rejected samples, no mode/gait transition, 0.014212-second
maximum gap and 0.002086-second final age. Position span was
0.000816 / 0.000461 / 0.001155 m and first-to-last displacement was
0.000691 / -0.000249 / 0.000102 m, below the existing 5 mm movement
significance boundary. The operator confirmed the robot was fully stopped.
Bridge remained inactive and the observer left no process or command endpoint.

## 6. Bridge probe results

| Probe | Physical x target | Fixed window | Conservative maximum predicted travel | Result |
| --- | ---: | ---: | ---: | --- |
| MP-030 | 0.03 m/s | 0.70 s | 0.0285 m | `BLOCKED PRE-COMMAND` |
| MP-050 | 0.05 m/s | 0.70 s | 0.0475 m | `NOT_RUN` |
| MP-080 | 0.08 m/s | 0.70 s | 0.0760 m | `NOT_RUN` |
| MP-100 | 0.10 m/s | 0.70 s | 0.0950 m | `NOT_RUN` |

The operator supplied the exact MP-030 safety approval. The Bridge was started
through the fixed dashboard lifecycle and preflight established exact release
`103ed69`, authenticated/connected/ready state, fresh LowState, exact-zero
accepted command, no lease, deadman released, motion run inactive, one owned
request publisher, zero foreign named request publishers, the expected ten
bare publishers, and idle Navigation/Mission/mapping state. The fixed local
dry-run passed.

The single live supervisor invocation returned exit status 2 and wrote this
private evidence before it could acquire a lease:

- `/tmp/robot-scope-c4c-1000/c4c-1788570525883782343-1463456.json`
- `status=BLOCKED`
- `error="fresh odometry pose is unavailable"`
- `locomotion_acceptance=NOT_EVALUATED`
- `physical_motion=NOT_EVALUATED`
- fixed predicted maximum travel `0.0285 m`

The dashboard pose endpoint remained `waiting`, with no topic and sequence
zero. Consequently the supervisor could not enforce its unchanged 0.5-second
pose-age, 5 mm pre-command drift and 0.10 m observed-travel gates and correctly
refused to continue. Bridge-owned request evidence after the invocation showed
zero Move, zero action and zero motion-run count; no lease, ARM, deadman or
non-zero command occurred.

A temporary exact-release diagnostic start of the existing strict wireless
odometry sender and receiver found the immediate blocker without weakening it.
The sender received `/utlidar/robot_odom` but sent zero packets because the
source stamps were consistently about `3788 ms` old; all samples were rejected
as `source_stale`. The receiver therefore received and published zero packets.
This exceeds the preserved 500 ms past-direction source-stamp guard. The
separate 100 ms limit applies only to future skew. Both temporary processes
were stopped in reverse order, UDP port 46030 was released, and the Bridge was
stopped through the fixed lifecycle. Final state was Bridge `inactive/dead`,
Navigation idle, no lease and no temporary process residue.

MP-030 was therefore consumed only as a supervisor invocation, not as a motion
attempt. It must not be retried automatically. Each remaining live probe and
any MP-030 retry require a new, separate approval. No probe may advance
automatically, and the ladder must stop after the first physical success.

## 7. Mode, gait and error changes

The preceding C4B run, both initial C4C stationary observations, the successful
STOCK-1 movement and the post-motion stationary observation all reported
`mode=0`, `gait_type=0`, `error_code=100`, with zero mode/gait transitions.
During STOCK-1, however, the same message stream reported 1.033427 m/s maximum
vector speed and approximately 0.439 m first-to-last position displacement,
while the operator observed approximately 0.30–0.40 m physical movement.

Therefore `/sportmodestate` is a live body-state evidence source for velocity
and position on this deployed firmware, but its mode/gait fields are not an
authoritative locomotion-state indicator. No time-to-gait or gait-entry enum
transition can be derived from this evidence. `error_code=100` remains opaque
and unchanged; no meaning is inferred.

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

## 8. Actual movement evidence

C4C stock-controller physical movement: `PASS`.

The operator observed approximately 0.30–0.40 m of intentional stock-remote
movement and confirmed the robot fully stopped. SportModeState independently
reported approximately 0.439 m first-to-last displacement and a 1.033427 m/s
maximum vector speed. The post-motion S0 position span returned below 1.2 mm,
inside the existing 5 mm significance boundary.

This proves the body and stock controller can produce locomotion. It does not
prove that the Robot Scope Bridge request path is accepted. The preceding C4B
operator observation remains no movement despite 59 signed Move requests. The
authorized MP-030 supervisor stopped before a Move request because its bounded
odometry safety input was unavailable, so a successfully armed fixed Bridge
micro-probe is still required to isolate that boundary.

## 9. Threshold interval

No Bridge gait-entry threshold interval has been established.

- prior highest observed non-moving signed x: `0.0291743403 m/s` in the Nav2
  C4B chain;
- stock-controller movement: confirmed, but its command magnitude is neither
  exposed nor comparable to the Bridge's physical x request;
- highest confirmed non-moving fixed Bridge probe: `UNKNOWN` (MP-030 emitted no
  Move and did not evaluate physical motion);
- lowest confirmed moving Bridge probe: `UNKNOWN`;
- uncertainty interval: `UNKNOWN`;
- time-to-gait and time-to-motion: `UNKNOWN`.

The C4B value is not treated as a firmware threshold because it included Nav2
command shaping and no stock/manual Bridge comparison exists yet.

## 10. Root-cause class

No specific root-cause class is selected. The Section 17 checkpoint value is:

```text
ROOT_CAUSE=UNRESOLVED
```

STOCK-1 passed. MP-030 was safely blocked before command because strict
wireless odometry rejected source stamps approximately 3.788 seconds old. The
next minimum work is to provide a separately qualified C4C motion-observation
source without relaxing the 500 ms past or 100 ms future strict-odometry
guards, then obtain a new, separate MP-030 approval. No Nav2
parameter or safety threshold is changed without fixed Bridge-probe evidence.

## 11. Changed code

The focused changes are committed, pushed, CI-green and deployed as the exact
full-SHA release identified in Section 1:

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
- the observer accepts ROS fixed three-element numeric arrays while retaining
  fail-closed rejection for strings, arbitrary iterables, booleans,
  non-numeric, non-finite and out-of-range values.
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

## 12. Tests

Current, directly rechecked evidence against this worktree:

| Check | Exact result |
| --- | --- |
| C4C observer focused suite after fixed-array correction | 17 tests, all passed |
| C4C micro-probe and signed-transport focused suite | 60 tests, all passed |
| complete Python suite with coverage | 1,107 tests, all passed; total branch coverage report 69% |
| JavaScript unit suite | 270 tests, all passed |
| Cockpit JavaScript suite | 86 tests, all passed |
| Playwright hardware-free browser suite | 32 tests, all passed |
| Ruff on configured `robot_dashboard scripts` scope | passed |
| configured mypy | passed, four files checked |
| Python compilation and shell syntax | passed |
| tracked-source secret scan | passed |
| frontend syntax scan | 53 modules passed |
| CI for deployed `103ed69` | run `33933164283`, both supported Ubuntu/Python jobs passed including browser E2E |
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
rechecked. It ran 1,103 tests and ended with one import error because the host
Python 3.13 environment lacks `fastapi`; the repository virtual environment
passes the corresponding suite. This remains a host baseline dependency issue,
not a C4C regression.

## 13. Service, process, lease and final safety state

The post-MP-030 cleanup audit found:

- external dashboard active on the full-SHA `103ed69e43e263020af426c06e6d7bb7d12b4e99` release;
- robot-side stable release link on the same full-SHA release, with the Control
  Bridge intentionally inactive/enabled after its fixed lifecycle cleanup;
- Navigation pipeline, localization-only session and goal idle;
- no Navigation or manual lease;
- immediately before shutdown, dashboard and Bridge accepted commands were
  exact zero, deadman released, motion run inactive and the latest signed
  request was StopMove;
- S1 showed authenticated Bridge, fresh LowState/SportModeState, one request
  subscriber, one owned publisher, zero foreign named publishers and the
  expected ten bare publishers;
- S0 and final inactive graph checks showed the expected ten bare request
  publishers, one subscriber and no Robot Scope publisher;
- S0/S1 and STOCK-1 private evidence exists at the exact paths in Sections 4
  and 5; the MP-030 pre-command block evidence exists at the path in Section 6;
  the observer and supervisor left no command endpoint or process residue;
- both S0 and S1 showed mode/gait `0/0`, error code `100`, no transition and
  sub-millimetre stationary variation, without inferring firmware semantics.

The release activation, S1 and MP-030 preflight intentionally stopped and
started the Bridge. The dashboard was restarted only during release activation.
None acquired a lease, armed, engaged deadman, sent a non-zero command, started
Navigation or sent a goal. No physical movement was commanded or observed
during S0/S1 or the blocked MP-030 invocation. STOCK-1 used only the
human-operated stock remote while the Bridge remained inactive. Post-motion S0
and the operator both confirmed final stop. After MP-030 blocked, the temporary
exact-release odometry sender and receiver were stopped in reverse order, port
46030 had no listener, and the Bridge lifecycle reached `inactive/dead`.

## 14. Next prompt

No C4E prompt has been created. The hardware-free supervisor tests, S0/S1
stationary baselines and STOCK-1 locomotion baseline are green, and the exact
release is deployed. The authorized MP-030 invocation was blocked before
motion by unavailable fresh odometry. The next engineering gate is a qualified
C4C-only relative-position observation path. Strict odometry source-clock
remediation remains a separate blocked track and is not assumed to be the only
solution. Only after software, stationary and dynamic observation
qualification may MP-030 be considered again, with a new fresh approval. Every
higher probe also requires a separate approval, and
the ladder stops after the first successful Bridge-driven movement.

`docs/TRACK_C4E_SUPERVISED_NAV2_RETRY_PROMPT.md` may be written only after C4C
has evidence for a root-cause class and a characterized effective command.
This C4C work does not send a Nav2 goal.

## 15. Rollback

Repository rollback should use a normal revert of the focused C4C commit,
whose published SHA is recorded in the Git/CI completion report. The baseline
before this change is `fa717cf32d4495692d9c57a9fb5f294c6a31ac8a`.
Deployment rollback must first verify exact zero, deadman released and no
lease, restore the external dashboard symlink to its preserved `e69718ad`
release and restart it, then stop the Bridge through the fixed lifecycle,
restore the robot-side rollback symlink to `e69718ad` and start it again only
when operationally required. Process cwd, latest signed StopMove, exact zero
and no lease must then be reverified. The dirty
external development checkout must never be reset or used as a deployment or
rollback target. Rollback is not currently required because the dashboard is
healthy and the Bridge completed exact-zero cleanup before becoming inactive.

## 16. Acceptance status

| Gate | Status |
| --- | --- |
| REPOSITORY_AUDIT | PASS |
| DEPLOYMENT_AUDIT | PASS |
| STARTUP_ZERO_FIX | PASS |
| OBSERVER_SOFTWARE | PASS |
| STATIONARY_BODY_BASELINE | PASS |
| STOCK_CONTROLLER_BASELINE | PASS |
| MP_030 | BLOCKED |
| MP_050 | NOT_RUN |
| MP_080 | NOT_RUN |
| MP_100 | NOT_RUN |
| GAIT_ENTRY_THRESHOLD | BLOCKED |
| SPORT_MODE_AUTHORITATIVE | FAIL |
| GO2_REQUEST_ACCEPTANCE | BLOCKED |
| NAV2_SCALING_ROOT_CAUSE | BLOCKED |
| SOFTWARE_CORRECTION | NOT_RUN |
| STATIONARY_SOAK | NOT_RUN |
| C4C_MOTION_OBSERVATION_STATIONARY | PASS |
| C4C_MOTION_OBSERVATION_DYNAMIC_SOURCE | PASS |
| C4C_SIGNED_DYNAMIC_END_TO_END | NOT_RUN |
| C4C_SIGNED_OBSERVATION_ONLY_SOFTWARE | PASS |
| C4C_SIGNED_OBSERVATION_ONLY_DEPLOYMENT | PASS — stationary manual-process path on exact release `a09264c` |
| NAV2_GOAL | NOT_RUN |
| ROBOT_MOTION | PASS |
| CLEANUP | PASS |

`STARTUP_ZERO_FIX=PASS` now covers the deployed full-SHA release.
`SPORT_MODE_AUTHORITATIVE=FAIL` is limited to the mode/gait fields as a
locomotion-state indicator: the position and velocity fields did reflect the
operator-observed movement. `CLEANUP=PASS` means release activation, S0/S1,
STOCK-1 and the blocked MP-030 invocation left no Robot Scope session, lease,
deadman, non-zero command, motion-run, observer, supervisor or temporary
odometry process residue.

## 17. Final decision

```text
ROOT_CAUSE=UNRESOLVED
```

This value records insufficient Bridge-acceptance evidence, not a diagnosis.
Stock locomotion is confirmed; MP-030 did not reach its motion phase because
the strict 500 ms past-direction source-stamp guard rejected approximately
3.788-second-old odometry; the 100 ms constant is the future-skew guard. The
cause remains unknown among publisher clock offset, queue/processing delay and
sender-host clock error. A separately qualified C4C observation source may
remove the probe dependency without changing strict odometry. No C4E prompt,
Nav2 retry or higher
Bridge motion probe is authorized by this checkpoint.

## 18. Follow-up: C4C motion-observation dependency

The follow-up design and software result are recorded in
`docs/C4C_MOTION_OBSERVATION_SOURCE_CONTRACT.md`. It preserves this blocked
MP-030 record, leaves `/api/v1/pose` unchanged, and selects the existing
Bridge-owned SportModeState position only as explicit C4C relative-travel
evidence. The exact release
`a8b88b80a66d5173914c4a3b21754f1155b222e1` was subsequently deployed to
both hosts and passed a five-minute stationary observation with all 1,201
samples `READY`, zero rejected samples or resets, a 41 ms maximum signed
callback gap and 0.076 mm maximum planar displacement. This changes only the
stationary qualification state. A later approved stock-remote observation
measured 0.118920 m planar movement from 5,920 valid samples and the operator
confirmed final stop; a following S0 capture measured only 0.187 mm
first-to-last planar drift. This qualifies the vendor source's dynamic
response but not live signed Bridge-to-dashboard delivery during movement
because the Bridge remained inactive to avoid request-publisher interference.
Overall dynamic qualification is therefore `PARTIAL_SOURCE_ONLY`, and the live
probe gate remains closed. MP-030 and all higher probes remain unexecuted by
the follow-up.
