# SLAM display deployment and stationary observation — 2026-10-17

The user confirmed current stationary conditions and approved candidate
`91f9006de6162d9e48f635f5f79a76e014950fd8`, bridge stop, dashboard/broker restart,
one 60-second Stereo observation and owned cleanup. Deployment and that observation
are complete. No second camera session or background continuation is scheduled.
Exact source, runtime/config identifiers, counts and private evidence hashes are in
[SLAM_DISPLAY_RUNTIME.json](SLAM_DISPLAY_RUNTIME.json).

## Deployment and preservation

Both Linux CI jobs passed for the exact candidate:
[CI 38998046853](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38998046853).
The previous device source was `cdebee40d212759703300ffc1e2de17ed93a4846`, with
three already published UI assets outside its commit. Current bytes matched the
candidate. Private copies, a named Git stash and a previous-source archive were
retained before a fast-forward. No reset, clean, stash pop/drop or data deletion
was used. All 1,307 candidate file hashes matched after deployment and observation;
the robot checkout is clean. HTTP serves the optimized dashboard module and the
preserved presentation assets with matching hashes and `Cache-Control: no-store`.

This was a full tested-main update: it also includes previously published native
diagnostics and policy observation source. No native-mask harness, new policy
enforcement, Nav2 pipeline or localization/reuse operation was executed.
The dashboard remains domain 0/CycloneDDS; the preserved Isaac image runs the
UID 1000 broker on domain 71/localhost/FastDDS. The shared broker socket remains
`/run/robot-scope-slam/broker.sock`; the broker imports `/home/unitree/robot-scope`.
The environment and all four stereo configuration hashes remained unchanged.
No dependency, VSLAM installation, calibration, freshness, pairing or timeout change
was made. The dashboard-owned Hesai preview restarted with the dashboard and is
running; FAST-LIO/navigation remained idle.

The seven existing native packages retained their native/preview revisions and
all 17 protected state/metadata JSON hashes matched. An initial audit compared
JSON-decoded lists to in-memory tuples and falsely reported inequality. Per-file
hashes and JSON-normalized rows matched; both receipts were kept. This is metadata
and revision preservation evidence, not a new full binary audit of every bag/map.
Only the new temporary session was discarded; no new package was saved.

## Real observation

The deployed browser's Stereo mapping button started session
`8ff8b15104b2476b9ccc1838fa3055bb`, generation 1. A separate guard was attached to
that exact session. The negotiated read-only receiver on the user's Mac observed
60.122 seconds from 08:14:15Z to 08:15:15Z (17:14–17:15 KST).

| Signal | Observed result |
| --- | --- |
| Received messages | 176, one connection, no malformed-frame rejection recorded |
| Receipt gap | median 0.334 s; p95 0.431 s; maximum 0.496 s |
| Image / camera pose / tracking | each available in all 176 messages |
| Overlay | 174 available; two `NO_VALID_TIME_ALIGNMENT` cases withheld |
| Current observations / trajectory | each available in all 176 messages |
| Global map | 158 points; first available after 47.17 s of receiver observation |
| Global geometry protocol | one full layer followed by 38 valid references |
| Uncompressed JSON size | median 140,565 bytes; maximum 150,926 bytes |

The browser visibly displayed real IR pixels, matching green overlays and camera
6DoF values. After stopping, it correctly hid stale image/pose/current overlays
while retaining the 158-point static map and 1,024-point trajectory (400 points
drawn). Camera reference is `vslam_lab_camera_link`; Go2 body pose remains
unqualified. Screenshots and hydrated full snapshots are private.

This confirms real reference delivery and channel independence. It does not
establish camera/browser FPS or sensor-to-screen latency. The receiver includes
its own parsing/hydration/disk overhead, disables compression and runs alongside
the browser. This stationary 158-point map is not a controlled comparison with
the previous moving 13,993-point sample. The earlier frozen-sample 93.54% byte
reduction must not be generalized to every live frame. Trajectory changed in all
176 messages and was sent in full each time.

## Stop and current ownership

The collector completed its 60-second window. The independent guard issued stop
at session age 90.786 s and confirmed cleanup at 96.275 s, within its 150-second
budget. By the time the manual browser Stop action was attempted, the guard had
already stopped the session and the control was disabled. Therefore manual UI
stop is not newly qualified by this window; guard/API cleanup is qualified.

Final state: SLAM IDLE, cleanup not required, camera reservation clear, owner probe
free, and no owned native camera/VSLAM/collector/guard processes left. The broker
and dashboard remain running. No operating TF, initialpose, goal, mission, actual
movement or bridge restoration was performed.

Reboot had started the systemd-enabled control bridge despite dashboard
`ROBOT_SCOPE_CONTROL_BRIDGE_AUTOSTART=0`. It was normally stopped before deployment.
The user then ran the prepared administrator script; readback at 08:19:45Z confirms
`inactive / disabled / MainPID=0`. Dashboard autostart remains off. The bridge's
SOFTWARE STOP/watchdog is unavailable while it remains off.

## Validation and remaining work

The unchanged implementation reuses its passing full Python result (2,164 pass,
two skips), 393 JS checks and exact-candidate CI. The private read-only observer
adds 17 passing offline checks, Python 3.10 syntax and Ruff verification.
No unchanged full suite or existing installation experiment was restarted.

Actual observation succeeded. Remaining visualization/performance work is a
representative larger-map profile that separates upstream broker/serialization,
network receipt and browser decode/draw costs. The current received cadence is
about three messages per second; smooth camera-rate drawing is not established.
No precise end-to-end latency or independent accuracy evaluation was performed.
The reported overlapping walls during turns remain a separate tracking/geometry
investigation, with no calibration fault or repair established here. Retained-map
completeness, map reuse and MR-MS-003 remain separate follow-ups. Driving is not
applied or qualified.
