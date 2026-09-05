# C4C Motion Observation Source Contract

- Status: software validated; deployment, stationary qualification, dynamic
  qualification and motion use are not approved
- Scope: the fixed C4C Go2 locomotion micro-probes only
- Selected source: `unitree_go.sport_mode_state.position`
- Automatic fallback: forbidden

## 1. Why this contract exists

The C4C supervisor previously used `/api/v1/pose` while requiring Navigation,
Localization and Mapping to remain idle. The endpoint is populated by the
general `RosAgent` odometry selection. In the deployed production profile the
intended source was strict wireless `/utlidar/robot_odom`, but the sender
rejected every observed sample as `source_stale`. The supervisor therefore
blocked before lease, ARM, deadman or Move. This is a verified direct block.

The following is a design explanation, not an additional observed fact:

```text
micro-probe needs bounded travel evidence
  -> general /api/v1/pose needs a selected Odometry producer
  -> strict wireless producer sends zero packets when source stamps fail its clock fence
  -> /api/v1/pose remains waiting
  -> pre-command gate blocks
```

The general pose endpoint is unchanged. C4C now consumes a separate, explicit
relative-position evidence field from the existing signed Bridge status.

## 2. Function-level paths

### Previous micro-probe pose path

```text
LoopbackDashboardAdapter.snapshots
  -> GET /api/v1/pose
  -> telemetry.robot_pose
  -> RosAgent.pose_snapshot
  -> TelemetryHub.pose_snapshot_locked
  -> RosAgent._summary_callback / _update_pose
  -> selected `odometry` topic from _pick_default_sources_locked
  -> producer selected from config/go2.json preferences and the live graph
```

`TelemetryHub` increments its own pose sequence on a decoded
`nav_msgs/msg/Odometry` callback. This sequence is not the original producer
sequence. The endpoint hides stale pose values and remains a general dashboard
world-pose view.

### Existing and selected SportModeState path

```text
Go2 /sportmodestate (or the one configured allowlisted alias)
  -> Go2ControlBridge._sport_mode_state_callback
  -> SportModeStateObservation.observe
  -> raw diagnostic snapshot plus C4C motion_snapshot
  -> signed /robot_scope/control/status or fixed authenticated UDP status
  -> ControlTransport.status_motion_observation
  -> ControlTransport.raw_snapshot receiver-age projection
  -> GET /api/v1/control
  -> C4C supervisor explicit source validation
```

The Bridge already owned this one subscriber. No new DDS endpoint, ROS owner,
planner, controller, Mission or Nav2 process is added. Position was previously
used only by the independent observation script; the Bridge callback read
mode, gait, velocity and error but did not retain position. The new projection
retains position, source stamp and a callback-derived sequence. The Bridge
status heartbeat and the underlying sample sequence are separate.

The installed `unitree_go/msg/SportModeState` definition on the robot contains
`TimeSpec stamp`, `float32[3] position` and `float32[3] velocity`. It contains no
separate source sequence. The contract therefore increments `source_sequence`
only after a strictly increasing source stamp and a valid fixed-size position
are observed. Repacking the same status cannot advance it.

## 3. Strict wireless time-fence correction

The immutable deployed `103ed69e43e263020af426c06e6d7bb7d12b4e99`
protocol has these values:

| Check | Constant | Actual limit | Direction |
| --- | --- | ---: | --- |
| receiver age of sender realtime | `MAX_SOURCE_AGE_NS` | 500 ms | past |
| sender comparison of source stamp to sender realtime | `MAX_STAMP_SENDER_DELTA_NS` | 500 ms | past |
| sender/receiver future skew | `MAX_FUTURE_SKEW_NS` | 100 ms | future |

Robot-side immutable hashes:

- sender: `3ca6f69e4c12c697e7e2735044b4ed15b8ec3dabd8ac6ddb0f178faf1cbd2ec1`
- protocol: `4a5e4dc0df2867dc2bc782154c391c5837855088ef81e3645d810f623a109229`

External immutable hashes:

- receiver: `930dca47ad7dc99c7255c7b4df85602848f093bd4d75c76552f696faca3c6795`
- protocol: `4a5e4dc0df2867dc2bc782154c391c5837855088ef81e3645d810f623a109229`

The sender imports `wireless_odom_protocol.py` from the script directory. The
installed systemd sender and receiver units currently name mutable
`project/robot-scope` working directories, while both units are inactive. The
robot project files match the immutable hashes. The external project protocol
has a different file hash, although the three limits above are identical. This
is a deployment-identity risk and is why a future deployment must use an exact
release and verify process cwd/import fingerprints rather than starting the
existing unit blindly.

The approximately 3.788-second-old `/utlidar/robot_odom` sample exceeds the
500 ms past-direction source-stamp limit. It was correctly blocked. It does
not exceed a “100 ms past guard”; 100 ms is only the future-skew limit.

Current evidence cannot distinguish among producer clock offset,
transport/queue/processing delay, and sender-host clock error. Root cause is
`UNKNOWN`. No stamp was rebased, no host clock was changed, and all strict
limits remain unchanged.

## 4. Candidate comparison

| Property | A: strict wireless odometry | B: SportModeState relative position | C: FAST-LIO observation-only |
| --- | --- | --- | --- |
| Source identity | `/utlidar/robot_odom` | `unitree_go.sport_mode_state.position` | `/Odometry` through a new explicit owner |
| Current implementation | implemented, inactive | existing Bridge subscriber; new bounded projection | C2 implementation exists but is Nav runtime-owned |
| Actual evidence | 3.788 s old stamps, sent 0 | stationary low noise; STOCK-1 position/velocity changed with physical motion | C2 stationary `/Odometry` history |
| Coordinates/origin | `odom` -> `base_link` | vendor local position; origin semantics unverified | FAST-LIO `camera_init`/`body` transformed by existing C2 contract |
| Timestamp | original odometry stamp | Unitree `TimeSpec`; clock domain unverified | original FAST-LIO stamp |
| Progression | original stamp plus signed packet sequence | strict source-stamp increase plus callback sequence | C2 gate sequence/stamp |
| Reset detection | boot/sequence/stamp guards | Bridge generation, stamp regression and jump latch | C2 generation/reset/jump gates |
| Delivery | authenticated odom datagram | existing authenticated Bridge status | would require sensor/FAST-LIO owner |
| Position evidence | unavailable now | present | present when pipeline runs |
| Extra processes | sender and receiver | none | XT16, IMU, FAST-LIO and observation owner |
| Control/Nav2 interference | none when healthy | none; read-only Bridge subscriber | must prove narrow owner and no planner/controller |
| Required change | resolve unknown clock/delay cause | signed bounded projection and supervisor adapter | new observation-only lifecycle boundary |
| Unverified | root cause and live supply | clock domain, origin/reset semantics, live end-to-end dynamic accuracy | isolated lifecycle/resource impact |
| Decision | preserved but blocked | selected for software implementation; live qualification pending | excluded for now because B needs fewer owners |

There is no runtime fallback among these sources.

## 5. Schema and semantics

`robot-scope.motion-observation`, version 1, is not odometry and is not a map
pose. It is limited relative-travel evidence for C4C.

It contains the fixed source ID, Bridge process generation, exact path-derived
release, source stamp, callback-derived source sequence, callback age measured
on the robot process monotonic clock, status receive age measured on the
dashboard process monotonic clock, explicit unverified source clock domain,
vendor-local coordinate identity, unverified origin, finite XYZ position,
quality, invalid reason, reset latch and bounded accept/reject counts.

`source_age_ms` is deliberately `null`: the Unitree clock relation has not
been qualified. Callback age is not called acquisition age. Cross-host
monotonic values are never subtracted. Orientation and ROS frame are also
`null`; neither is fabricated. A source stamp is used for progression only.
Across consecutive samples, a source-time advance more than 250 ms ahead of
the same-process callback elapsed time is an invalid future-progression event.
This relative progression check is not the strict odometry protocol's 100 ms
absolute future-skew check. A callback gap over the 500 ms observation stale
limit also invalidates that Bridge generation. Last and maximum callback gaps
are carried in the signed observation for stationary qualification.

Fixed arrays must be indexable with exact length. Strings, bytes, booleans,
iterator-only objects, non-finite values and over-bound values are rejected.
Unknown fields are rejected by the dashboard validator.

Quality behavior:

- `WAITING`: no qualified sample exists;
- `READY`: a valid source-stamp-advancing sample is within the robot callback
  freshness limit;
- `STALE`: the last valid sample is retained, but callback age is over limit;
- `INVALID`: malformed data, regressed/future-progressing stamp, evidence gap,
  reset or implausible adjacent jump was seen.

A duplicate source stamp increments a bounded diagnostic counter but is not
new evidence: it does not advance sequence or refresh callback age, so a
persistently repeated sample becomes `STALE`. Regressed stamps,
generation/source/origin changes, non-finite data and an adjacent jump over
1 m invalidate the generation. The component never automatically chooses a
new origin. A new probe requires a new qualified session.

## 6. Supervisor contract

The command path remains:

```text
supervisor -> dashboard control interface -> ControlManager
  -> signed transport -> Go2ControlBridge -> Go2 Sport request
```

The supervisor requires the literal source ID before preflight. It requires
the observation generation to equal the signed Bridge epoch and the release to
equal the dashboard release. Before any nonzero frame it requires both
LowState and the underlying observation sequence to advance.

The existing bounds remain:

- callback age: at most 0.50 s;
- pre-command planar drift: at most 0.005 m;
- planar displacement from the first qualified sample: at most 0.10 m.

Planar displacement is `sqrt((x-x0)^2 + (y-y0)^2)`, not accumulated path
length. The runtime cursor retains the maximum observed displacement so a later
return toward the origin does not erase prior evidence. Source selection is
fixed before the probe.

The four probe speeds, 0.70 s command window, 50 ms cadence, watchdog tail,
first-acceptance timeout, scheduler no-catch-up rule, HMAC, epoch/sequence,
200 ms watchdog, LowState/cardinality, lease, deadman, clamps, exact zero and
cleanup contracts are unchanged. Mode, gait and error remain raw diagnostics;
no mode 3 or gait 1 requirement exists.

`MOTION_USE_APPROVED` remains false. The public live CLI therefore refuses all
four probes even when old confirmation flags are supplied. Software tests may
exercise the pure supervisor with mock data, but no prior approval can open
the live gate.

## 7. Validation states

```text
SOFTWARE_VALIDATED=PASS
STATIONARY_OBSERVATION_VALIDATED=PASS
DYNAMIC_OBSERVATION_VALIDATED=NOT_RUN
MOTION_USE_APPROVED=NO
```

Software validation does not qualify the source clock, coordinate origin or
dynamic distance accuracy. Existing STOCK-1 files can support replay tests but
cannot replace a live end-to-end dynamic qualification of the new signed path.

The stationary result was collected on 2026-09-05 from the exact release
`a8b88b80a66d5173914c4a3b21754f1155b222e1`. It qualifies only continuity,
freshness and stationary noise of this signed path. It does not qualify the
vendor-local coordinate scale during motion and does not open the probe gate.

## 8. Deployment and stationary-validation execution

The operator approved this deployment and stationary-only observation. No
motion authority was obtained and no nonzero command was sent.

1. Build one archive from the eventual exact full SHA and record its SHA-256.
2. Stage clean immutable release directories on robot `192.168.50.30` and
   external `192.168.50.10`; do not pull/reset either dirty project checkout.
3. Verify producer/consumer schema compatibility and file fingerprints.
4. Confirm Navigation, Localization, Mission and Mapping idle; no lease,
   deadman or accepted nonzero command; record existing preview/sensor owners.
5. Stop neither service until the operator approves the exact transition.
6. Transition Bridge first with exact-zero verification, then dashboard. Never
   run two Bridges. No new DDS endpoint is added: the existing one
   `/sportmodestate` subscription and restricted request publisher remain.
7. Keep the live probe gate closed. Observe only the signed
   `motion_observation` for 5–10 minutes while stationary.
8. Record source rate and source-stamp progression, callback/status ages,
   the signed last/maximum callback gap, XY/Z span, rejected/reset counts,
   Bridge readiness, endpoint
   cardinality, CPU/RAM/network and Control/Nav2 state.
9. Stop only processes started by this validation, or retain production state
   only if that exact final state was approved.

The immutable release archive SHA-256 was
`bf27af806edcab008ca1e458bb99c047bbc3f6eda3020f35e7950b9175d84b0f`.
Both staged copies matched it. The Bridge was transitioned first, followed by
the dashboard. Process cwd on each host resolved to the same full-SHA release,
and both services reported zero restarts during the observation.

The signed API observation ran for 300.024055 seconds and sampled the control
view 1,201 times plus the Navigation, Mapping and Mission views 301 times.
Every motion observation was `READY`; HTTP failures, validation errors,
rejected samples and reset detections were all zero. Source sequence advanced
from 79,194 to 168,729, an observed rate of 298.426071 Hz. There were 54
duplicate source stamps; none advanced sequence or refreshed freshness. The
maximum callback receive age was 18 ms, maximum signed callback gap 41 ms and
maximum dashboard receiver-status age 282 ms. Maximum planar displacement
from the first stationary sample was 0.000076 m. XYZ spans were 0.000092 m,
0.000092 m and 0.000021 m.

The dashboard service memory snapshot changed from 199,262,208 to 210,276,352
bytes and its cumulative CPU counter increased by 257.542 seconds over the
measurement bracket. External interface counters changed by approximately
1.180 GB received and 6.51 MB transmitted. The robot Bridge end snapshot was
42,344,448 bytes, 26 tasks and 107% process CPU; robot interface counters
changed by approximately 0.75 MB received and 1.164 GB transmitted. These
network and CPU figures include the already-running XT16 preview and therefore
must not be attributed solely to the small status-field addition.

The private evidence JSON is stored on the external host as
`/home/jetson_orin_nano/.robot-scope/c4c-observations/c4c-stationary-a8b88b8-20260905.json`
with SHA-256
`b1418349f8ca3e3664eee264c1bbbb9aab56d4fc29f92b4c3ee51f7f882afb88`.
It contains no command or secret material.

Before cleanup, the manager and accepted commands were exact zero, lease and
motion run were inactive, and Move/nonzero-Move/action counts were all zero.
Navigation, localization and goals remained idle; Mapping pipeline and save
operation remained idle; Mission remained inactive. The pre-existing XT16
preview remained running. The Bridge was then stopped through the fixed
dashboard lifecycle API and reached `inactive/dead`; the dashboard and preview
were left active. The strict odometry sender and receiver remained inactive.

An intermediate deployment exposed two fail-closed integration issues before
the successful observation. Commit `d425a67bafc3752408b3cddb2bf8af9fa371d599`
added the signed observation to the intentionally bounded public control
projection. Commit `a8b88b80a66d5173914c4a3b21754f1155b222e1`
then corrected duplicate source-stamp handling: a duplicate is no progress and
does not refresh age, while a persistent repeat becomes stale. Regressions,
future progression, reset, evidence gap and implausible jump remain invalid.

The immediate pre-`a8b88b8` rollback links preserve
`d425a67bafc3752408b3cddb2bf8af9fa371d599`; the earlier
`103ed69e43e263020af426c06e6d7bb7d12b4e99` release also remains available.
Any rollback must select an exact immutable release explicitly, transition in
reverse order, verify process cwd/fingerprints and exact zero, and leave the
Bridge inactive unless a new operational approval says otherwise. Git
publication is not deployment approval.

## 9. Remaining qualification

Stationary validation has passed. A separately approved human-operated dynamic
comparison is still required. Dynamic validation must establish that this
vendor-local stream detects bounded real movement promptly and consistently
without source/origin reset. Only then may a focused change set
`MOTION_USE_APPROVED=true`, followed
by a new exact-release deployment and a fresh MP-030 approval. MP-030,
MP-050/080/100 and Nav2 goals remain not run by this work.
