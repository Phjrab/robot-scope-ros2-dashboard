# Independent VSLAM measurements

`collect.py` subscribes inside the **already isolated ROS container**. It does not start a camera, launch VSLAM, command the robot, alter parameters, or record image pixels. `analyze.py` uses only the Python standard library. These tools have synthetic test coverage; no Jetson, CUDA, ROS subscriber, real-camera or motion validation is implied by those tests.

## Before collecting

- Independently verify the experiment domain is unused and differs from the operating domain. These commands use `71` only as an example; the collector verifies its argument equals the environment, not global ownership.
- Set the domain and localhost-only discovery for **all** experiment publishers and subscribers through the experiment wrapper. Avoid inheriting operational CycloneDDS settings. Do not change `.bashrc`.
- Verify actual topics and message types. All topic arguments accept overrides. Set `--imu` only to the D435i IMU after its rate, axes, units, timestamps and extrinsic have been checked.
- For replay, use `--use-sim-time`, play `/clock`, and set `use_sim_time` consistently on VSLAM and diagnostics. Do not run live publishers simultaneously.
- Output parents must exist. Outputs are created exclusively; an existing result is never overwritten.

Example within the experiment container, from the Robot Scope clone root:

```sh
ROS_DOMAIN_ID=71 ROS_LOCALHOST_ONLY=1 python3 experiments/isaac_vslam/metrics/collect.py \
  --domain 71 --run-id T1-VO-20261013-001 \
  --duration 310 --evidence-type live_stationary \
  --output /work/runs/T1-VO-20261013-001/metrics.jsonl

python3 experiments/isaac_vslam/metrics/analyze.py \
  /work/runs/T1-VO-20261013-001/metrics.jsonl \
  --warmup-seconds 10 --expected-stereo-hz 30 \
  --output /work/runs/T1-VO-20261013-001/summary.json
```

The `310` second collection includes 10 seconds of warmup and a 300 second measurement window. Starting while no images arrive is recorded as missing data; the tool does not wait forever for a stream. `--max-events` provides a second finite limit (default 250,000 messages). SIGINT/SIGTERM ends collection with a `run_end` reason; SIGKILL or a crash without a final record is analyzed as `INCOMPLETE`. Only signal the PID owned by the experiment wrapper.

For T0 replay, use `--evidence-type official_bag --use-sim-time` and override camera topic arguments to the selected, remapped input topics. For VIO, add `--imu /vslam_lab/camera/imu` only if that is the observed topic. For SLAM, add `--slam-path /vslam_lab/visual_slam/tracking/slam_path`; the collector records its newest pose and the number of path poses, not the entire historical path. Loop closure and saved-map relocalization require separate evidence and are not inferred from these summaries.

## Clock and timing interpretation

Every sample records monotonic arrival time. Header time and ROS arrival time are separately recorded. FPS and gaps use each clock independently. The reported FPS is `(N−1)/(last−first)` over observed samples; startup and ending silence remain visible as separate durations. Gap counts count intervals exceeding `--gap-ms` (default 100 ms), not missing frame estimates.

Header-to-subscriber data age is `N/A` unless `--clock-contract-evidence` contains the evidence that both timestamps use the same ROS clock. Merely adding this option does not synchronize clocks. Example acceptable evidence should cite the driver timestamp-domain check or the replay clock and stamp inspection, plus the run artifact that records it. Backward timestamps, negative ages, a stalled ROS clock, and live ROS clock changes relative to monotonic greater than 1 second invalidate the age estimate. This detection cannot prove the clocks are aligned; the verified clock contract remains mandatory. Simulation time is not assumed to track wall time. A camera hardware-clock timestamp is never subtracted from host monotonic time.

Release 3.2 status durations are handled separately: `node_callback_execution_time` covers the node's processing through output publication; `track_execution_time` covers cuVSLAM pose tracking. Their reported seconds are converted to milliseconds. Reported rolling mean/max fields are identified as such and are not independent per-frame timing samples. These fields are not camera-to-consumer age and not a GPU utilization measurement.

## Analysis contract

- JSON summaries contain sample count, mean, p50, p95 and maximum; percentiles use linear interpolation. Empty distributions use `null`, never NaN/Infinity.
- Left/right pairing uses the nearest of the adjacent timestamp candidates without reusing a right sample; distant pairs are excluded and unmatched counts are retained. `--stereo-tolerance-ms` controls analysis matching only, not a sensor acceptance threshold. This greedy diagnostic pairing is not a globally optimized assignment.
- Camera period deviation uses `--expected-stereo-hz`, which must match the selected profile. Release 3.2 sensor requirements are at least 30 Hz, period jitter ±2 ms and stereo offset ±100 µs. They differ from the VSLAM warning/matching parameters. The analyzer does not increase or configure those parameters.
- Raw `CameraInfo` matrices, image frame/encoding/size, IMU vectors/covariances and static transforms remain in JSONL for input auditing. No calibration or camera-to-body transform is invented. Static TF often arrives during warmup, so inspect the full JSONL for extrinsic evidence even if its measurement-window sample count is zero.
- `vo_state` is decoded only when observed message fields match the pinned release 3.2 schema: `0=UNKNOWN`, `1=TRACKING` (success), `2=LOST` (failed). This is the published **VO** return code, not proof of loop closure or global localization. Unknown/unmapped samples are not classified as success.
- `lost_entries` includes an initially lost sample and labels that condition separately. Recovery measures subscriber monotonic time from the first failed sample to a successful sample. Unrecovered intervals are retained through the window end. No samples, `NO_RECENT_INPUT`, and an explicitly stopped estimator are distinct. Absence alone cannot establish the cause or a loss count.
- Pose summaries use translation and quaternion angle from the first valid pose, reject changed frames and account for equivalent quaternion signs. They describe pose change. Calling this stationary drift requires an independently verified stationary camera. The endpoint displacement is **not** automatically a return error. No measured reference means no ATE, RPE or absolute accuracy.
- Resource samples contain container-visible host memory, swap, load average and accessible temperatures. Missing GPU/CPU process metrics are not zero; capture experiment-owned `tegrastats` separately. A ROS image subscriber adds memory-copy and scheduling overhead even though pixels are not stored. Include that observer overhead in the run manifest.
- No metric automatically sets `INSTALL_PASS`, `LIVE_INPUT_PASS`, `VO_PASS` or `VIO_PASS`. Interpret these with the run's input evidence and predeclared acceptance criteria.

Pinned status source: `NVIDIA-ISAAC-ROS/isaac_ros_visual_slam` commit `e31f4cc1d41a329a01946e5fe63669f8b15da677`, `isaac_ros_visual_slam_interfaces/msg/VisualSlamStatus.msg`.

Synthetic tests from the clone root:

```sh
python3 -m unittest discover -s tests -p test_isaac_vslam_metrics.py -v
```
