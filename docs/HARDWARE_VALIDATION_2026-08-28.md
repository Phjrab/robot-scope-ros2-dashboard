# Hardware validation — 2026-08-28

## Scope and safety boundary

This session exercised the deployed Jetson dashboard, Go2 observation path,
XT16 preview path, and the fixed Control Bridge service lifecycle. The robot
remained DISARMED with no control lease, released deadman, and zero linear and
angular commands. No motion action, navigation goal, initial pose, mapping
launch, map mutation, map deletion, or dataset capture was performed.

The final XT16 validation below used repository and Jetson commit
`2d785c31e27f85faf5cf0223a47fb490687c0fb1`. Runtime acceptance reports remain
private and Git-ignored on the Jetson.

## Control Bridge lifecycle result

- The root-owned sudoers rule was installed from the repository example and
  validated with `visudo`. It permits only fixed `systemctl --no-block start`
  and `stop` commands for `robot-scope-control-bridge.service`.
- The independent `ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_ENABLED=1` opt-in was
  added to the private deployment environment after preserving a private
  rollback copy.
- The dashboard reported the Bridge service as configured and startable while
  the unit remained disabled and inactive by default.
- A same-origin request mismatch was rejected with HTTP 403 before dispatch,
  confirming the mutation origin guard.
- Dashboard-mediated start reached `ACTIVE/RUNNING`, and the signed bridge
  reported authenticated, connected, ready, and idle.
- The observed graph cardinality was one sport subscriber, one owned sport
  publisher, zero foreign named sport publishers, nine expected bare Unitree
  publishers, ten total sport publishers, and one LowState publisher.
- The Controls UI showed `AVAILABLE`, `DISARMED`, `BRIDGE IDLE`, released
  deadman, and zero commands. The STOP button remained disabled until the local
  safety acknowledgement was checked.
- Dashboard-mediated stop reached `INACTIVE/DEAD` and completed successfully.
  The Bridge was left stopped at the end of the session.

## Acceptance results

An initial run after enabling the lifecycle produced:

```text
PASS=48 FAIL=2 BLOCKED=4 NOT_RUN=12
```

The signed bridge was healthy, but the public API omitted the internal total
publisher count. Commit `1cce222` now projects the validated internal
`sport_publishers` value to the public `total_sport_publishers` field without
exposing the internal field. After deployment, the next run produced:

```text
PASS=49 FAIL=1 BLOCKED=4 NOT_RUN=12
```

The `control.signed_bridge` row changed to PASS. The remaining FAIL was
`lidar.xt16_converted`. The four BLOCKED rows were the raw LiDAR dashboard
observation, idle FAST-LIO odometry, idle navigation timestamp/TF validation,
and idle localization health. These were not converted into false passes.

## XT16 performance finding

The Hesai driver continued producing complete 64,000-point raw frames at its
expected cadence, but the Python conversion bridge intermittently rejected
clouds when callback delay exceeded the fixed 250 ms clock residual boundary.
The observed converted topic fell below 4 Hz and became stale during those
windows. The bridge correctly rejected stale input instead of rebasing the
clock or publishing an unsafe timestamp.

The session also identified unrelated host contention: a separate
`cluster-discovery` process targeting an LLM benchmark worker repeatedly
created a temporary Python virtual environment and ran `ensurepip`. During
these probes it consumed a large share of one CPU core while the dashboard,
XT16 bridge, and Control Bridge were already active. Converted-cloud backlog
and rejection bursts increased during this contention. Robot Scope timing and
freshness thresholds were not weakened to hide the failure.

### Quiet-host rerun and rejected tuning

The unrelated discovery load was stopped and its temporary Python processes
were confirmed absent before a second session. With the Control Bridge stopped,
the converted cloud recovered to 6.49–7.37 Hz, 0.031–0.050 s age, and
68–126 ms jitter. This confirmed that the external probe materially worsened
the first run, but did not prove it was the only cause.

With the signed Control Bridge active, no lease, released deadman, and zero
commands, the acceptance result remained:

```text
PASS=49 FAIL=1 BLOCKED=4 NOT_RUN=12
```

The converted-cloud rate and jitter could remain within bounds while a single
freshness gap exceeded the fixed 0.5 s limit. One quiet-host run observed
5.69 Hz, 226 ms jitter, and 0.824 s age. A bounded 100 Hz and then 50 Hz
`/imu/body` experiment reduced IMU callback work but did not remove the gap;
the 50 Hz run observed 5.77 Hz, 296 ms jitter, and 2.617 s age. Those tuning
commits were therefore reverted by `305e324` rather than leaving an unverified
FAST-LIO behavior change in the product.

Jetson telemetry showed all six CPU cores online in MAXN mode, approximately
43°C temperature, no swap use, and no thermal or memory pressure. The remaining
evidence points to the Python large-PointCloud2 conversion/DDS boundary under
the combined dashboard and signed-bridge workload, not a safe reason to widen
the timestamp or freshness limits.

## Repository verification

- Targeted API and acceptance tests: 16 passed.
- JavaScript unit tests: 238 passed.
- Python suite: 672 total; 671 passed. The one error is the known macOS baseline
  where `/etc/os-release` is absent in
  `test_apply_os_release_override_must_match_running_host`.
- The deployed Control Bridge publisher-total fix was verified against the
  live API and acceptance recorder.

## XT16 C++ bridge and receive-buffer resolution

The repository Python converter was retained as the executable contract
reference, while the deployed high-rate conversion path was replaced with the
repository-owned C++ ROS 2 node in commit `2e56d8a`. On the Jetson this reduced
the conversion process from approximately 104% CPU to approximately 30% CPU
without changing the point layout, decimation, timestamps, QoS contract, or
freshness rejection boundary.

Per-socket inspection then isolated the remaining intermittent gap to the C++
node's CycloneDDS unicast socket: with the host's 212,992-byte receive-buffer
ceiling it accumulated 2,908 kernel UDP drops in 20 seconds. Commit `72e18a3`
added a fixed 8 MiB CycloneDDS receive-buffer request and a fail-closed doctor
check. The deployed sysctl file raises only `net.core.rmem_max` to 8,388,608;
it does not change the default buffer for unrelated sockets.

After applying the fixed sysctl file and restarting only the dashboard, a
20-second control-idle measurement reported zero drop growth on all four C++
bridge UDP sockets. A dashboard-mediated Control Bridge start was then tested
with no lease, released deadman, and zero commands. Across a 60-second combined
load window, all 241 observations of `/velodyne_points` stayed within the fixed
bounds:

```text
minimum rate:       9.980 Hz
maximum age:        0.117 s
maximum jitter:     7.480 ms
out-of-bound rows:  0
API read errors:    0
```

The same-window logs contained zero input rejection lines and zero five-second
summaries with nonzero rejections. Every UDP socket owned by the converter
still had a zero cumulative kernel-drop count after the combined-load run.
Read-only `go2-nav` acceptance produced:

```text
PASS=53 FAIL=0 BLOCKED=4 NOT_RUN=12
```

`lidar.xt16_converted` and `control.signed_bridge` both passed. The raw Hesai
dashboard row remained blocked because that raw topic is intentionally not a
dashboard observation source, and FAST-LIO/navigation/localization remained
blocked because those runtimes were idle. No blocked row was converted into a
false pass. The Control Bridge was stopped through the dashboard immediately
after acceptance and was verified inactive; the dashboard remained active.

## FAST-LIO odometry validation

The Jetson and repository were aligned to commit `4d43ed2` for this step. The
dashboard started only its owned FAST-LIO localization pipeline while Nav2,
initial-pose publication and navigation goals remained idle. No map was saved,
converted, renamed or deleted. The robot remained stationary and DISARMED.

The fixed FAST-LIO readiness gate passed with three consecutive fresh
`/Odometry` samples and one fresh `/Laser_map` sample. The final observed header
and arrival ages were 0.043/0.028 seconds for odometry and 0.070/0.001 seconds
for the registered cloud. A direct read-only odometry sample retained the
expected `camera_init -> body` frame contract and zero linear/angular twist.

During a 60-second FAST-LIO-only run, `/Odometry` stayed at or above 13.85 Hz,
its maximum observed age was 0.111 seconds and its maximum jitter was 39.98 ms.
The FAST-LIO process's four UDP sockets accumulated no kernel drops. The
converted cloud remained at or above 9.97 Hz with maximum age 0.137 seconds,
and its bridge sockets also retained zero drops.

A second run added the authenticated Control Bridge without acquiring a lease,
holding deadman or publishing a motion command. Both XT16 and FAST-LIO socket
drop deltas remained zero. The dashboard rate window initially included the
intentional gap between the stopped first session and the fresh second
publisher, so it briefly reported a conservative 1.41 Hz minimum and 8.761 s
jitter while current sample age stayed below 0.102 seconds. The metric recovered
without weakening any bound. The subsequent read-only acceptance observation
for `/Odometry` was 19.9 Hz, 0.036 seconds age and 40.94 ms jitter.

The combined-load read-only acceptance result was:

```text
PASS=54 FAIL=0 BLOCKED=3 NOT_RUN=12
```

`control.signed_bridge`, `lidar.xt16_converted` and
`localization.fast_lio_odom` passed. `navigation.tf_and_timestamp` and
`navigation.localization_health` correctly remained blocked because Nav2 was
idle, and the unmeasured raw Hesai dashboard-rate row remained blocked. The
FAST-LIO pipeline and Control Bridge were then stopped through their dashboard
APIs and verified inactive. The persistent XT16 preview and dashboard remained
active.

## CWP live verification follow-up

The repository and Jetson were aligned to commit `3642d75` for this follow-up.
Nav2 was explicitly deferred. The Control Bridge, FAST-LIO and mapping remained
stopped, and no initial pose, navigation goal, mission mutation, map mutation,
dataset capture or robot motion was requested.

### Camera ownership and live sources

- The Go2 front camera was live at 1280x720 and approximately 14.3 FPS through
  the existing UDP multicast H.264 relay.
- Opening and compacting only the Go2 panel changed its catalog viewer count
  exactly from 0 to 1 and back to 0. Restoring the panel returned it to 1 while
  the RealSense source kept its independent viewer. No second camera owner was
  introduced.
- The Jetson could reach the RealSense relay at `192.168.123.18`, and its HTTP
  endpoint returned 200. The source did not produce a frame. The relay health
  response reported `state=error`, zero frames, `process_running=false`, and
  `RealSense GStreamer exited with status 1`. This is a live-source FAIL rather
  than a Cockpit demand or network failure. Relay host credentials were not
  available, so its service logs were not inspected and it was not restarted.

### Live XT16 rendering and host load

- LOW 10K, MEDIUM 30K and HIGH 60K modes all rendered through the shared
  `/velodyne_points` transport. Observed short-window UI rates were about
  23-32, 23-34 and 21-38 FPS respectively.
- AUTO with a HIGH ceiling stepped HIGH to MEDIUM to LOW under load and then
  remained bounded at LOW, confirming the adaptive hysteresis path.
- With HIGH and both camera demands active, a ten-second Jetson sample measured
  40.113 Mbit/s receive traffic on `eno1`. The dashboard used about 122.08% CPU
  and 99.28 MiB RSS; the XT16 bridge used 31.37% CPU and 18.28 MiB RSS; the
  Hesai driver used 35.96% CPU and 118.73 MiB RSS; and the Go2 GStreamer relay
  used 37.26% CPU and 55.61 MiB RSS.
- These are bounded short-window observations, not a substitute for the
  required 60-minute renderer/socket/listener/heap soak.

### Revision-pinned map correction

The Navigation map selector and SavedMapCatalog metadata exposed a valid map
ID and revision, while the Cockpit map panel incorrectly showed
`MAP_REVISION_MISMATCH`. The live API confirmed that catalog metadata uses
`id`, but the bounded map-data response uses `map_id`. Commit `3642d75` accepts
those two fixed product fields while retaining exact opaque ID and revision
matching. It does not relax the conflict, geometry, annotation or navigation
revision gates.

After deployment and dashboard-only restart, the read-only map panel reported
`READY` for `map_20260813_125411`, map ID prefix `97bae189` and revision prefix
`504ee7d326`. Localization correctly remained `UNINITIALIZED / UNAVAILABLE`
and navigation stayed `IDLE` because Nav2 was deferred.

### Verification and final safe state

- Map-state targeted JavaScript: 8/8 passed.
- Frontend syntax: 48 modules passed.
- Full JavaScript unit: 239/239 passed.
- Cockpit Playwright: 13/13 passed. One full-run mission draft timing failure
  passed when isolated and the complete suite then passed on rerun; no
  assertion was weakened.
- Full Python: 672 total, 671 passed, with the known macOS-only
  `/etc/os-release` baseline error unchanged.

At the end of verification, both camera sources had zero viewers and were
stopped, the Cockpit had zero floating panels, LiDAR was restored to LOW 10K
with AUTO disabled, and the Safety HUD showed DISARMED, released deadman, no
lease and zero velocity commands. Control Bridge, FAST-LIO, mapping and Nav2
processes were absent; only the dashboard and persistent XT16 preview remained
active.

## RealSense color interface resolution — 2026-08-30

The relay failure was traced to device identity, not network reachability or
the JPEG encoder. The D435i depth and color USB interfaces both claimed the
same by-id `video-index0` name. On this host the resulting symlink pointed to
depth node `/dev/video0`, which rejected the fixed 640x480 YUY2 color profile
with `not-negotiated`. A two-frame read-only probe showed the same failure on
`/dev/video2`, while the actual color node `/dev/video4` accepted the profile.

Commit `d56fbd7` replaced the ambiguous by-id selection with a fail-closed
sysfs identity check. The relay now accepts exactly one by-path character
device matching Intel vendor `8086`, D435i product `0b3a`, USB color interface
`03`, and V4L index `0`. It still rejects zero or multiple matches and retains
the fixed network allowlist, 640x480@15 profile, software JPEG preference,
bounded viewers and root-owned hardened service.

The exact deployed script checksum was
`b2280729e85472758965bf1f59649cc752371d27176ed309544e843d3a4adce1`.
After the RealSense service restart:

- the allowed dashboard host received 2,478,096 MJPEG bytes in five seconds,
  including a complete 17,152-byte JPEG frame;
- the standalone Cockpit panel reached LIVE at 15.0 FPS with zero frame age;
- the short dual-panel check reported Go2 14.29 FPS and RealSense 15.0 FPS in
  the dashboard API, with exactly one viewer on each source;
- the relay reported 14.99 FPS, zero invalid frames, one viewer and no error;
- closing both panels returned dashboard viewers to zero and the relay to idle
  with no warning-or-higher journal entries after the deployed restart.

The dashboard had been inactive after the Jetson reboot and was started only
for this read-only CWP check. Control Bridge, FAST-LIO, mapping and Nav2 stayed
stopped. The final Cockpit state had zero panels, LOW 10K LiDAR, DISARMED,
released deadman, no lease and zero velocity commands. The actual Xbox
Controller check and 60-minute soak remain explicitly deferred.

### RealSense relay restart recovery

With the RealSense panel already LIVE, the operator restarted only
`robot-scope-realsense-camera.service`. The panel entered `WAITING` while the
relay restarted and then returned automatically to LIVE at 15.0 FPS without a
page reload or panel reopen. After recovery, the dashboard catalog and relay
health each reported exactly one viewer; the relay reported one running
producer process, one running producer thread, 14.99 FPS, zero invalid frames
and no last error. Closing the panel returned both viewer counts to zero and
the on-demand producer process/thread to stopped while the manually managed
relay service remained active and idle.

This validates supervised service-restart recovery only. Physical RealSense
cable removal remains deferred to a separately supervised fault-injection
scenario. No control lease, motion command, mapping, localization, Nav2 or map
mutation was used during this check.

### RealSense JPEG resolution metadata

Commit `37abe45` added a bounded JPEG SOF metadata scan to the dashboard's
existing single RealSense reader. It does not decode the image or add another
camera owner. The scan follows JPEG segment lengths within a 128 KiB header
limit and rejects malformed markers, dimensions above 8192, or images above
32 MiPixels. Width and height are projected through the fixed camera catalog
and the existing WebSocket frame metadata.

After the commit was fast-forwarded to the dashboard host and only
`robot-scope.service` was restarted, the live API reported width 640, height
480 and 15.0 FPS. The Cockpit panel displayed `RES 640×480` while LIVE. Closing
the panel returned dashboard and relay viewers to zero, and the relay's
on-demand producer process and thread both stopped. The relay service remained
manually managed, active and idle.

### Dataset Capture storage and recovery — 2026-08-30

Three 1 Hz server-side sessions were captured without requesting robot motion.
All three finalized as `completed` and remain under the private
`runtime/datasets/sessions` root for post-run inspection:

| Source selection | Session suffix | Samples | Bytes | Drops |
| --- | --- | ---: | ---: | ---: |
| Go2 front | `7a00c285070c456fa24a4f1ff2fe4f55` | 14 | 1,873,299 | 1 initial invalid JPEG |
| RealSense color | `8ee7902369e04f518d23ff1192cf00f3` | 6 | 294,176 | 0 |
| Go2 + RealSense | `db3954c7d25e4e3f8d634a8ebb2ddf55` | 6 pairs | 1,095,415 | 1 initial invalid JPEG |

Every published sample contained its selected JPEG files and `metadata.json`;
manifests and sample artifacts were mode `0600` below mode `0700` managed
directories. RealSense metadata reported 640x480, the dual sample contained
both 1280x720 Go2 and 640x480 RealSense frames, and the inspected pair skew was
637 microseconds against the fixed 250 ms maximum. The manifest correctly
states that pairing is not hardware synchronisation.

The deployed status API reported a 20 GiB per-session quota, a 5 GiB minimum
free-space reserve and approximately 55.6 GB free. Filling the production disk
to either boundary was intentionally avoided. Commits `03af9a3`, `ecc295c` and
`359dd67` instead added and stabilised isolated fail-closed coverage. On the
Jetson's Linux filesystem, all 18 DatasetCapture tests passed, including:

- quota accounting before a sample is published and exact camera-token release;
- reserve failure before camera open, and reserve loss during writing with no
  partial sample published;
- an isolated capture process that writes a real atomic sample and exits
  without normal cleanup, followed by recovery as `interrupted` with the
  committed sample preserved and abandoned temporary directories removed.

The production DatasetCapture manager was idle after verification, all live
session files were retained, and no dataset path was added to Git. A live
dashboard SIGKILL during production capture was not required because the same
manager and filesystem recovery path passed in an isolated child process.

### Control Bridge robot-off preflight — 2026-08-30

After the robot battery was exhausted, no live bridge transition was attempted.
The Jetson ran all 18 Control Bridge lifecycle, preflight and HTTP contract
tests successfully. The deployed unit remained `disabled`, `inactive` and
`dead`, with no main PID or matching bridge process. The read-only lifecycle API
reported a loaded fixed service, no operation and stop unavailable because the
unit was already inactive.

The control projection remained fail-closed: no active or bound lease, deadman
false, linear X/Y and angular Z all exactly zero, bridge waiting/not connected,
and control unavailable. This is sufficient software and inactive-state
evidence only. The current-commit `start -> DISARMED/zero -> stop` hardware row
remains blocked until the robot is charged and connected; no start request,
lease, ARM request, action or motion command was sent during this preflight.

## Remaining risks and next safe step

1. Stop or reschedule the unrelated cluster-discovery/temporary-venv probe and
   keep it disabled during later Robot Scope acceptance sessions.
2. The C++ conversion, DDS receive buffer and FAST-LIO odometry now pass both
   standalone and Control Bridge combined-load checks. Nav2 validation remains
   explicitly deferred. When resumed, start with Nav2 without a goal, then
   initial pose, runtime TF and localization health under the operator,
   physical remote and E-stop procedure in `HARDWARE_ACCEPTANCE.md`.
3. Preserve the existing local modifications in the external Hesai workspace;
   the full installer remains intentionally blocked until their ownership and
   purpose are reconciled.
4. Navigation/localization and supervised motion scenarios remain incomplete.
   Motion validation requires the physical E-stop ready, a clear test area,
   low-speed limits, an operator present, and the physical remote in hand.
5. RealSense now resolves the exact D435i color interface and passes short
   standalone and simultaneous LIVE checks. Revalidate the sysfs identity if
   the camera model, USB topology or relay host is replaced.
6. Complete the 60-minute CWP soak and actual Xbox Controller validation; the
   short rendering observation and synthetic controller tests do not satisfy
   those hardware acceptance rows.
