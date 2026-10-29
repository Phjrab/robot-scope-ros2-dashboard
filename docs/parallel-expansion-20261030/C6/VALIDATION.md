# C6 validation receipt

The candidate uses only C6-owned paths. Source/fixture fingerprints are recorded
in evidence/validation.json. Final commit HEAD and its CI are reported after push;
no previous branch's green check is presented as this candidate's CI result.

| Check | Result and scope |
|---|---|
| Actual existing goal producer + sink + C6 parser | PASS; generated arrival, yaw error, canceled cases; original ns/goal/pose intact |
| Actual C1 producer/validator + C3 JSON parser/adapter/consumer | PASS at pinned latest SHA; 0.2 strings beyond 2^53, expired source, source reset, map reset |
| C6 focused Python | 12 PASS; includes 2 explicit peer checks when C6_DEPS is set |
| Mock adapter/clock unit | 4 JS PASS, separately identified; no real HTTP/native claim |
| Actual C3 mount + existing renderer in Chromium | PASS; local file input, A/B, pause, step, seek-back, expiry/map-clear, XSS and native original path pixels |
| Accessible private real sink | 2 CANCELED runs, 128 source records; original goal/near-result/after-stop pose and source ns EXACT_MATCH; input SHA256 unchanged |
| D3 actual hosted artifact replay | All 5 existing cases parsed; real recorded native result/trace/path retained; **no local native/ROS execution** |
| Browser external requests / control mutations | 0 / 0; 12 GETs to fixed local static routes only |
| Complete Python discovery | **3144 run, 0 failures/errors, 3 existing optional skips**, 138.602 s; C2_CROSS_REQUIRED=1, C6_DEPS set |
| Existing JS suite | **700 PASS** |
| Frontend syntax | **114 dashboard modules PASS**, plus C6 host/probes checked |
| Whole-source Ruff / mypy / tracked-source secret scan / whitespace | PASS (see validation.json) |

C6 imports have no ROS/control client and the parser regression rejects any socket
construction. Browser host CSP has connect-src none; no private bundle is served
or uploaded. Scene ports only alter local renderer state. These zero-mutation
results are offline software evidence, not device instrumentation.

## Actual field result preservation

The public allowlisted summaries are [run A](evidence/goal-0.json),
[run B](evidence/goal-1.json), and [reference comparison](evidence/field-comparison.json).
Original private paths/context/config/process data were not copied into Git.

| Recorded result | Near result XY / yaw | First measured stop XY / yaw |
|---|---|---|
| A CANCELED | 0.21693780336552657 m / -0.5416224128502644 rad | 0.23887938189009666 m / -0.6366998576569042 rad |
| B CANCELED | 1.0580929703881354 m / 1.7882436152828185 rad | 1.0558109958069524 m / 1.862413546261037 rad |

These match the existing field-check report; goals differ, so this is not an
algorithm A/B improvement measurement. Result timestamps are receipt times, not
Nav2 success timestamps. Accepted rows lack an independent event timestamp;
associated pose stamps are separately labelled. ACK/contact remain UNOBSERVED.
The first measured-stop sample does not imply continuous stillness afterwards.

## Native artifact boundaries

D3's [existing hosted run](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840774827)
ran source `fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d`. This task only downloaded and
read its exact artifact; ZIP and member SHA256 checks pass. [Verification counts](evidence/artifact-verification.json)
retain succeeded/canceled/failed distinctions. Simulation contact count zero is
not a physical contact observation. Neither raw clearance zero nor ZERO commands
are promoted to contact or measured stop. Native original float-second timestamps
are never advertised as ns measurement precision. No C7 result is needed.

The C1 producer and C3 mount in this check are actual modules, but their data is
either explicitly SYNTHETIC or archived native SIMULATION. It is not a live C1
service or a real-robot observation chain. The static loopback host is actual HTTP;
mock transport tests are separate. Native costmap geometry, real joint/calibration,
real canonical C1 archive and independent bridge/contact evidence are not claimed.

## Preserved environment failures

First full discovery: 3143 run, 127 errors/2 failures/3 skips. Most errors were
existing strict filesystem tests rejecting macOS `/var` symlink ancestors; the
initial temporary environment also caused an offline child/benchmark failure.
Second unfiltered run with resolved `/private/tmp`: 3143 run, 2 errors/7 failures/
3 skips, all remaining failures were existing calibration fixture GID checks
because the new directory inherited wheel while the process group was staff.
Only the C6-owned temporary directory's group was aligned to the process group;
22 affected Hesai tests passed, then the **complete unfiltered** suite passed as
reported above. No product tests, thresholds, safety checks or shared sources were
changed or excluded. Full logs remain private; their hashes are retained in the
validation receipt. The final extra strict-input validation was followed by the
12 focused tests and static checks.

External/device socket connections were blocked throughout full-suite runs by a
temporary audit guard; only loopback was permitted. No robot DDS/camera/service,
deployment, TF/goal/cmd_vel publication, main merge, PR or other branch mutation.
