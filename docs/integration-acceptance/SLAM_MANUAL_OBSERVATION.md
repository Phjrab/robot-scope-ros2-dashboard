# Stereo manual observation — 2026-10-17

One approved bounded observation is complete on deployed implementation
`91f9006de6162d9e48f635f5f79a76e014950fd8`. The operator used the existing physical
remote; Codex sent no movement commands. Actual image, camera pose, tracking and
a growing global map were observed in the dashboard. Delay remains measurable;
duplicated-wall geometry and calibrated accuracy are not qualified. Exact identity,
aggregate measurements and private-evidence hashes are in
[SLAM_MANUAL_OBSERVATION.json](SLAM_MANUAL_OBSERVATION.json).

## Scope and exact execution

The user confirmed a stationary start, safe manual operating space and immediate
physical stop/independent recovery. The approved scope was one Stereo session,
stop request by age 300 seconds, cleanup target 360 seconds, and manual motion
capped at 90 seconds. The bridge remained inactive/disabled throughout; its
SOFTWARE STOP/watchdog was unavailable. No operational TF, initialpose, Nav2 goal,
mission, autonomous command, bridge restoration or deployment was performed.

Browser access was initially disabled. No camera session began during that blocker.
After access recovered, the in-app dashboard's Stereo mapping button started
session `77fdc2a25ec548c789ac0dddd55ab01e`, generation 2, map epoch
`db3ab27761a545f4885aea8bcdcc4f4a`, at 17:41:48 KST. Mapping used the preserved
Isaac image and domain 71/localhost/FastDDS broker as UID 1000. Dashboard domain
0/CycloneDDS remained unchanged. Camera reference is `vslam_lab_camera_link`,
not measured Go2 body pose. IMU fusion and operational pose application were off.

The first requested rotation included operator-reported round-trip translation.
That evidence is retained as a mixed-motion segment. After the operator confirmed
a full stop, a new stationary baseline was recorded in the **same session**.
The operator then reported completion of rotation only, return to the earlier
heading and full stop. Phase boundaries mark assistant cues/operator reports,
not independently measured motion onset. The physical motion duration and exact
return pose were not independently measured.

The dashboard Stop/discard flow was used at approximately 17:46:37 KST, before
the 300-second guard threshold. The guard did not send another stop; it observed
cleanup at age 312.562 seconds, within the 360-second target. Final API readback:
IDLE, unsaved=false, cleanup_required=false, camera reservation clear. The live
host camera-owner probe independently reported free. Bridge remains
inactive/disabled, dashboard and **user** broker services remain active.
The initial system-unit lookup for the broker was the wrong namespace; the
subsequent `systemctl --user` lookup confirmed the unchanged running instance.

Only this new temporary session was discarded. No native package was saved or
removed. Diagnostic snapshots remain private. The robot checkout remained clean,
and all four Stereo configuration hashes matched the pre-observation values.
This is not a new binary audit of every pre-existing map/bag. No calibration,
emitter, pairing, freshness or timeout threshold was changed.

## Real data receipt and larger-map behavior

The independent Mac receiver observed 320.016 seconds, including startup/cleanup:
364 JSON messages, 353 active-context messages, one connection and one context.
No invalid JSON/geometry or connection error was recorded. All 353 active messages
had image, camera pose, TRACKING, current observations and trajectory available.
Global map was available in 257; the initial 96 had no map layer. Overlay was
available in 325. These are receiver/channel counts, not camera or browser FPS.

| Delivered map size | Samples / within-bin gaps | Receipt gap median / p95 |
| --- | ---: | ---: |
| Below 1,000 points | 41 / 40 | 0.403 / 0.524 s |
| 1,000–4,999 | 141 / 139 | 0.562 / 1.327 s |
| 5,000–9,999 | 21 / 19 | 0.827 / 1.305 s |
| 10,000–14,999 | 53 / 51 | 1.872 / 2.516 s |

A gap belongs to a bin only when both consecutive active endpoints share that
bin, connection and context. Peak delivered count was 17,027, observed once;
no sustained 15K+ cadence is established. The last active main-receiver map was
13,555 points; the later browser stop view showed 13,264. They are different
snapshots, not a completeness discrepancy. Native retained-map completeness
and maximum-capacity/very large-map performance remain unverified.

Active gaps excluding lifecycle transitions had median 0.522 s, p95 2.093 s and
maximum 4.586 s. Map delivery used 48 full layers and 209 references; trajectory
changed in all 353 messages. Full-message median was 546,329 uncompressed JSON
bytes versus 139,391 for map references. Bytes saved did **not** establish that
latency was fixed. Motion, map changes, server work, extra subscriptions, resource
polling and observer processing are confounded; this is not a controlled A/B test.

## Actual displayed-image age

Read-only DOM samples read the image stamp written immediately after canvas
`drawImage`. Each call was bracketed by Mac wall time. Two live persistent-SSH
clock probes bound robot-minus-Mac time near -17 to -10 ms. The table uses regular
approximately 500 ms sampling, stamped labels, and DOM brackets at most 50 ms
inside those clock-probe times. The initial single sample and a 20-read burst are
not pooled into these results. Four final labels had no stamp; one final read took
2.279 seconds and is excluded from the narrow-bracket table, but retained raw.

| Display period | Accepted samples | Median image age | Maximum image age |
| --- | ---: | ---: | ---: |
| Stationary baseline, 3,598-point map | 30 | 0.972–0.987 s | 1.646–1.661 s |
| Rotation retry | 30 | 1.237–1.252 s | 2.648–2.664 s |
| Stationary return, about 13.5K points | 20 | 1.457–1.472 s | 2.269–2.292 s |

These conditional intervals describe the age of the timestamped image held on
screen. They assume continuous host clocks and offsets remaining within the
measured envelope. The RealSense driver uses approximate hardware-to-host time
mapping; its bias, physical exposure, compositor/monitor presentation and exact
decode/paint duration were not calibrated. Therefore **physical glass-to-glass
latency remains unmeasured**. The samples nevertheless show old displayed inputs
during actual operation, rather than inferring display speed from WS cadence.

## Rotation, matching and FIT findings

Comparing the two operator-declared stationary means around the rotation-only
retry gives camera-pose change **0.13917 m and 6.7682 degrees**. Position RMS radius
around each phase mean increased from 1.396 mm to 10.123 mm; the final phase also
contains drift over time, so this is not pure high-frequency noise. These results
combine SLAM self-consistency, camera motion about the physical rotation axis,
possible real translation and unmeasured return-pose error. They are **not absolute
accuracy**, calibrated drift or Go2 body-pose validation. No independent distance,
angle, reference trajectory or camera-to-body extrinsic measurement was available.

During the retry, image/pose/tracking were available in all 46 received frames;
overlay was available in 29. Across the entire active run, the 28 withheld overlays
had `NO_VALID_TIME_ALIGNMENT`, with source spreads 33.294–166.473 ms beyond the
existing 20 ms overlay guard. Stereo input pairing is separate: the eleven saved
full snapshots all had an actual timestamp-matched pair with zero source skew.
The additional two-second mid-rotation snapshot received no frame, so continuous
rotation-time stereo pairing is not proven. A final snapshot shows the bounded
cache selecting an older valid quartet instead of forcing the newest mismatched
image/observations together. No tolerance was relaxed.

The 13,555-point saved full snapshot spans approximately **114 × 125 × 80 m**;
95% of points are within 5.72 m of the coordinate-median center, but 78 are more
than 20 m away and 25 more than 50 m away. The current scene FIT uses all accepted
extrema. Its source formula gives a default camera distance around 248 m for this
snapshot, explaining the visibly tiny central map after FIT. This is a calculation
from source and saved points, not a direct read of the browser camera transform.
No points were deleted or filtered in production. Distant points are not declared
physically invalid without ground truth. This finding does not establish the cause
of the user's duplicated walls or prove a calibration fault. Projector-like dots
in the IR image remain a hypothesis; no current emitter parameter readback/change
was performed in this window.

## Incomplete diagnostics and next minimum work

The separate resource observer made 160 requests at two-second slots with a 1.5 s
request deadline; none completed. No live CPU/GPU/memory/thermal conclusion is
available, and those requests themselves are additional workload. The deadline
belongs to the private observer; no product timeout was changed.

Stop completed on the server, but the UI initially retained MAPPING and
`SLAM_REQUEST_TIMEOUT`. A status refresh eventually showed IDLE while the old error
text persisted. Source review found the UI ignores the accepted STOPPING response
and treats a failed follow-up GET as a sticky action error. The error does not prove
that the backend continued mapping. This is recorded as an incomplete stop-status
presentation, not a failed camera cleanup or a newly qualified seamless UI Stop.

Next minimum software work: expose accepted-stop/readback-pending state and clear
only the matching transport error after authoritative reconciliation; profile
broker snapshot/serialization, resource-query scheduling and browser decode/draw
separately; explain full-map extent and provide a clearly labelled central-region
FIT while retaining full geometry/counts/export. For rotation diagnosis, collect
bounded per-pair and native tracking/calibration/exposure diagnostics across the
actual motion phase. Do not call outlier filtering a geometry repair or inflate
freshness/timeout limits. Absolute accuracy still requires independent measurements.

No new runtime code or deployment was made in this observation. The unchanged
implementation reuses its passing Python/JS/CI evidence; no full suite or VSLAM
installation was repeated. Private observer/analyzer tests: 26 pass; exact-session
guard: 19 pass; resource observer: 2 pass. Source/AST/lint checks are recorded with
the private tools. Production edits here are documentation only. No extra camera
session or background continuation is scheduled; keep the bridge OFF.
