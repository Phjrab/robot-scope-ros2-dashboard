# Field diagnostic repairs and unresolved incident audit

2026-11-16, Asia/Seoul. The robot is powered off. All work in this change is
local/offline; no robot connection, service restart, motion or deployment occurs.
The last verified robot release is 37b4f80, not this diagnostic-tool revision.

## Repaired diagnostic paths

The preserved `probe_ros_observed.py` used `list(message.position)` and similar
expressions. ROS arrays retained numpy float32 elements; `json.dumps(rows)`
raised TypeError. Its single chained finally block requested STOP successfully,
then failed exporting motion and never exported sent commands or final readback.
It also retained all samples only in memory until exit. Lost historical samples
cannot be recovered from the end reason or the operator's forward-motion report.

Use `scripts/run_go2_bounded_diagnostic.py` for the repaired bounded comparison,
not the archived ad-hoc script. It defaults to an offline plan, imports ROS only
inside explicit live mode, and requires fresh stopped/supervision/clear-corridor
confirmations. It retains the previous 0.20 m/s, 3 s, 0.15 m displacement,
0.30 s sample-age and 0.15 rad body tilt-change bounds. No watchdog, robot
safety policy, gait or obstacle-avoidance switch changes. Live execution has not
been tested with the robot powered off; the offline plan is not permission to move.

`field_trial_evidence.py` normalizes finite numeric scalars, rejects NaN/Inf and
unsupported evidence, and redacts credential fields. Motion rows are appended
and flushed while collecting, with fsync at least once per second when samples
arrive. A hard power loss can lose the last unsynced second; a partial trailing
JSONL row must be treated as incomplete, not valid evidence. The diagnostic
observer runs separately from the command sender. Logging failure reaches the
sender's failure check and ends the trial; it is not silently ignored.

STOP request, separate STOP readback, observer/ROS shutdown, journal closure and
each export are attempted independently. Atomic JSON replacement preserves a
previous good artifact if conversion or writing fails. A final export failure
also appears on stderr/stdout via the exit summary and a nonzero exit status.
No STOP readback is claimed when that query fails or returns nonzero commands.
This is software state evidence, never proof of a physical halt.

The earlier HTTP-polled 0.20 trial timed out before any corresponding Move.
It is excluded from the speed comparison. The repaired tool uses the existing
ROS subscriber for measurement; it does not poll HTTP inside the command loop.
This avoids the diagnostic polling dependency but does not establish the exact
cause of that historical timeout. No automatic rearm or motion retry is added.

For a Nav2 trial, use the tested `check_navigation_trial` contract. A running
navigation job legitimately owns an active `input_source=navigation` lease.
The manual probe instead requires STOP, no lease and idle navigation. Applying
the latter rule to a Nav2 trial caused a historical pre-goal cancellation.
The new check binds job, map revision, start position AND direction, localization,
zero pre-goal command, fresh policy readback and unchanged collision checking.
Its result explicitly does not authorize movement.

`initial_pose_payload` only builds the standard `map_id/map_revision/pose`
request. It cannot carry the `job_id` that incorrectly selected the manual
experiment path in the historical preparation helper. This is not a replacement
for server admission or fresh operator confirmation. Example offline inspection:

```sh
python scripts/run_go2_bounded_diagnostic.py
python scripts/check_field_trial.py saved-trial-before.json
python -m unittest discover -s tests -p test_field_trial_diagnostics.py -v
```

Keep historical archives immutable. Jetson-only `prepare_sequence.py`,
`run_new_draft.py` and other unpublished helpers cannot be inspected or replaced
while that device is off. Do not rerun them on restart; review their exact bytes
and migrate to these tested contracts first. The archived short-trial script
already contained the corrected navigation-lease check, but its export chain
still lacked independent failure handling. It is not the canonical next runner.

## Unresolved issues, including older releases

| Incident | Established evidence | Still unresolved / required evidence |
| --- | --- | --- |
| Sensor readiness timeout | The 04:59 UTC failure reports a 15 s timeout. A later boot had two LiDAR-active/IMU-empty intervals; after stabilization, IMU was about 500 Hz and LiDAR 10 Hz. | The earlier failing input window was not preserved. Do not assign the later IMU gap as its proven cause. On the next boot retain raw readiness stdout/stderr and simultaneous raw IMU, cloud and DDS graph timestamps. |
| Motion observation stays INVALID | `SportModeStateObservation._observe_motion` deliberately latches malformed/regressed/jumped/gapped input for the process generation. A later valid sample does not clear the first invalid reason. | Restarting reset the generation, not the upstream cause. Do not remove the latch or automatically restart/rearm to make readiness green. Record the first rejected sample and preceding source/receive timestamps. |
| Initial refinement requires STOP | Operational initialization requires two continuous seconds below 0.03 m/s and 0.05 rad/s, with odometry received within 0.5 s. These are odometry-derived, not an operator checkbox. | The historical rejection does not prove physical movement. Freshness loss, short observation and estimated body sway need contemporaneous data to distinguish. Ten seconds of observed settling allowed a later pass; it is not a policy fix. |
| Draft versus sensor pose mismatch | Sparse registered clouds had roughly 350 points; exact-stamp inverse-transform comparison agreed within about 5e-7 m. Dense fits and candidate bounds sometimes disagreed with the clicked draft. | Physical wall identity, body-centre/IMU reference and absolute pose remain unmeasured. Low RMSE/conditional candidate acceptance is not independent ground truth. Do not enlarge prior limits or silently adopt the candidate. |
| Stored map versus physical room | The inspected 2D occupied cells matched the 3D projection (4,541/4,541). The edited map converted 49,759 UNKNOWN cells to FREE in that preserved comparison. | A uniform 2D/3D map offset is unsupported; this does not establish physical clearance, outer-wall identity or that edited free cells were observed clear. Existing maps are not modified by this change. |
| Walking correction jump | The stopped goal exceeded SO(3) correction 0.1 rad with a 0.1054 rad step; residual and translation remained below their limits. XT16 decimation's 4/16-channel loss was independently reproduced and fixed. | No preserved rejected transform/raw pair proves channel loss was the sole cause of that step. Later trials did not reproduce it but do not establish long-duration stability. Record rejected candidates, accepted correction, exact odometry and raw IMU/cloud together. |
| Low commanded speed without forward travel | Operator reported stepping/swaying at 0.09/0.16 m/s and clear forward motion at 0.20. Last approach stalled near 0.28 m. | This brackets observed behavior in that state, not a universal motor dead zone. `mcf` readback does not establish the user-facing gait. Native avoidance readbacks differed across separate sessions (earlier false, later true); cause/timing of that change is unknown. Do not disable avoidance or remote input as a speculative fix. |
| Final arrival and heading | Last completed deployment changed approach policy and removed recovery retry while retaining XY 0.05 m/yaw 0.10 rad and other limits. | No post-37b4f80 physical arrival trial exists. Deceleration-to-translation, final heading/settling and single failure termination need an uninterrupted supervised run. |

The 59 cm command-timeout incident and later 28 cm stall are different events.
The latter ran beyond 59 cm and ended with an explicit operator-supervised STOP;
its later `lease lost` is the consequence of that STOP. Likewise MAP ERROR was
an independently fixed retained UI message, not proof of localization failure.

## Evidence gaps to close before the next goal

The later goal monitor began about 12 seconds after goal submission. API samples
are not a complete 200 ms command-gap trace. Start the independent ROS recorder
before admitting a goal, verify each required topic has samples, retain source
and receive clocks separately, and continue through terminal action plus zero
command/readback. The repaired micro-probe journal alone does not replace raw
LiDAR/IMU/TF/command recording for a full Nav2 root-cause investigation.

Do not infer a physical pose from vendor position displacement alone, nor claim
goal success from a bound-triggered diagnostic stop. A new operator pose and
current sensor/map checks are required after power-on and any repositioning.

Local evidence reviewed: `nav2-live-analysis-20261115/RESUME_TRIAL_RESULT_20261115.txt`,
`GOAL_STOP_ANALYSIS_20261115.txt`, `SUPERVISED_GOAL_RESULT_20261115.txt`,
`APPROACH_DEPLOYMENT_HANDOFF_20261115.txt`, `resume-trial-evidence.zip`,
`approach-evidence/probe_ros_observed.py` and the 2026-11-14 map/scan audit docs.
These remain outside Git where they contain full field data.
