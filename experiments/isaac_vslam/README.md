# Isolated Isaac ROS Visual SLAM lab

These wrappers run release-3.2 `isaac_ros_visual_slam` on the onboard Jetson. They do not publish movement commands, change host ROS, or integrate with operational TF/Nav2. See [measured results](../../docs/experiments/isaac-vslam/RESULTS.md), [runtime pins](versions.runtime.json), [official reference](../../docs/experiments/isaac-vslam/OFFICIAL_REFERENCE.md) and [launch contracts](config/README.md).

## Runtime already prepared

Host: `unitree@192.168.50.30`, root `/home/unitree/experiments/isaac-vslam-lab`:

- `code/`: this directory, mounted read-only in containers.
- `sources/`: exact NVIDIA/common/examples/NITROS/VSLAM and wrapper source SHAs; read-only during trials. VSLAM itself uses locked official apt binaries.
- `data/`: official downloaded sample and reviewed inspection, read-only.
- `runs/<session>/`: ownership, manifests, effective parameter dumps, measurements, logs and maps. Writable only within this experiment.
- `recordings/`: shared archive for all live recordings, writable in lab containers.
- `evidence/`: package/image locks, preflight, final restoration, bag hashes, legacy relocation records.

Image IDs are local immutable Docker images retained on this Jetson, not remotely pullable registry digests. The official base registry digest is in the manifest. The installed VSLAM image and camera image were verified by actual execution. A byte-identical clean reconstruction of the camera image was NOT_RUN. The camera image used a checked SDK source image and built the pinned wrapper with 2 workers; its installed SDK hash matched the source image build hash. Preserve the local image or use `docker image save` to a dedicated experiment archive with enough space before removing it. Do not replace it with `latest` and claim equivalent reproduction.

The official base was downloaded, official signed scoped apt trust was configured **inside the experiment container**, and locked VSLAM/common/interfaces/NITROS packages were installed there. Source references and full apt acquisition logs are in `runs/setup-20261013-0410/`. SDK is 2.55.1, wrapper commit `c04f43308c00a6f495f14a47cc84cc293047cdff`, installed overlay `/opt/vslam_lab/realsense`. The full source image SDK build is retained in that image. Host packages were not installed or changed. The supplied package lock and source SHA identify the observed combination; they do not prove any future apt dependency resolution or SDK rebuild will be identical.

## Preflight and sample rerun

Run these **on the Jetson** from the runtime code directory. Commands never require a password in an argument or script. Use existing SSH key/agent/control connection; if required use an interactive terminal with verified host key.

```sh
cd /home/unitree/experiments/isaac-vslam-lab/code
python3 preflight.py > ../evidence/preflight-new.json
```

Review other builds, recording, GPU/CPU load, temperature, free space, running containers, actual service environments and camera users. Unreadable process environments/device opens are NOT_OBSERVED, not proof of vacancy. Domain 0 was operational; 71 was checked and used here, but check again. `labctl start` rejects visible host processes using its candidate domain and runs with Docker network `none`; this is not security or GPU/USB resource isolation.

Choose a new session ID; never reuse/overwrite a prior run. After a fresh resource window:

```sh
python3 labctl.py start --run t0-new-session \
  --image sha256:3c3e4eb675ea79e1c84296ef447170b86a14cbcab76eb16a39730e7a3bdb0e2c \
  --domain 71 --cpus 2 --resource-window-confirmed
python3 labctl.py exec --state ../runs/t0-new-session/ownership.json -- \
  bash -c 'source /opt/ros/humble/setup.bash; python3 /lab/code/run_bag.py \
    --bag /lab/data/isaac_ros_visual_slam/quickstart_bag \
    --contract /lab/code/config/official_sample.input.json \
    --replay-spec /lab/code/config/official_sample.replay.json \
    --run-dir /lab/run/vo --mode vo --timeout 60'
python3 labctl.py exec --state ../runs/t0-new-session/ownership.json -- \
  python3 /lab/code/metrics/analyze.py /lab/run/vo/metrics.jsonl \
    --output /lab/run/vo/analysis.json --warmup-seconds 0
```

The source bag db3 SHA256 is `f9baa7b80d456aaf89ea69d1cc312775b763f185c073887ad5ac4c3f05e9afca`. `data/quickstart-inspection.json` contains the reviewed sample's actual calibration and selected static TF. `run_bag` selects only the front raw stereo sensors, publishes exact recorded camera transforms through `selected_static_tf.py`, and uses `/clock`/sim time. It never replays old estimator outputs/dynamic TF or runs simultaneously with a live input driver in that session. Observe actual tracker initialization, input/output/status and all failure logs before assigning PASS; launcher exit status alone is insufficient.

## Fresh live window

The last operational camera service has been restored and its resource window is closed. Coordinate a **fresh** exclusive camera window before any new live trial. Do not stop other drivers, assume a lab lock binds other chats, or start against the on-demand operating RGB relay just because it currently has no open USB file. Use the user's approved operational procedure to return the camera; these tools do not stop that service automatically.

Confirm the device's current serial, USB node and speed, actual supported stereo/motion profiles, SDK/firmware/wrapper, open devices and resource window. The old USB node `/dev/bus/usb/001/011` is an observation, not a persistent device path. A new camera contract must identify the real evidence and a ownership check within five minutes. Example contracts are intentionally NOT_OBSERVED and refuse launch. Do not set evidence flags from examples alone.

After fresh handoff, create a new camera session with the observed exact USB device:

```sh
python3 labctl.py start --run live-new-session \
  --image sha256:f9d47c621390b34544de684fea8d62c9bba82f834daa6696733277773f85fdb5 \
  --domain 71 --cpus 2 --resource-window-confirmed \
  --camera-usb /dev/bus/usb/001/011 --camera-window-confirmed
```

Put newly checked `camera-contract.json` and observed `d435i-input.json` in `../runs/live-new-session/`. The prior actual input contract is retained under `runs/live-post-reboot-20261013/d435i-input.json`; preserve calibration metadata and recheck it instead of copying validity assertions. The pinned right CameraInfo convention is documented in the results and guarded by an explicit source/evidence exception. A namespace does not change a message frame_id.

For an initial stereo/IMU input trial with short input recording:

```sh
python3 resource_watch.py --duration 100 \
  --output ../runs/live-new-session/resources.jsonl \
  --summary ../runs/live-new-session/resources-summary.json \
  --state ../runs/live-new-session/ownership.json
# In a separate terminal during that finite watcher:
python3 labctl.py exec --state ../runs/live-new-session/ownership.json -- \
  bash -c 'source /opt/ros/humble/setup.bash; source /opt/vslam_lab/realsense/setup.bash; \
    python3 /lab/code/run_live.py --camera-contract /lab/run/camera-contract.json \
      --run-dir /lab/run/input --mode input --duration 40 --record-seconds 30 \
      --stationary-confirmed'
```

`--stationary-confirmed` requires the operator's real assurance; it does not move or hold the robot. Input mode requests the observed supported 200Hz gyro/100Hz accel candidate. Do not call this a verified IMU rate: this camera yielded zero actual IMU messages. VO mode disables motion streams and does not fuse IMU. Never start VIO until actual IMU rate, units, axes, timestamps, calibration and camera transform are observed; current stored contract correctly rejects VIO.

For the stationary VO trial, refresh ownership evidence, run a watcher for about 350 seconds and:

```sh
python3 labctl.py exec --state ../runs/live-new-session/ownership.json -- \
  bash -c 'source /opt/ros/humble/setup.bash; source /opt/vslam_lab/realsense/setup.bash; \
    python3 /lab/code/run_live.py --camera-contract /lab/run/camera-contract.json \
      --input-contract /lab/run/d435i-input.json --run-dir /lab/run/vo \
      --mode vo --duration 310 --stationary-confirmed'
python3 labctl.py exec --state ../runs/live-new-session/ownership.json -- \
  python3 /lab/code/metrics/analyze.py /lab/run/vo/metrics.jsonl \
    --output /lab/run/vo/analysis.json --warmup-seconds 10
```

All camera/estimator/collector/player/recorder commands go through `labctl exec`, which clears operational DDS settings and sets the same domain, local SHM/loopback profile, ROS logs and explicit session identity. Both VSLAM output TF flags and ground-plane constraints are false. World frames are `vslam_lab_map`/`vslam_lab_odom`; base is the calibrated camera, not Go2 body. GUI/RViz is optional and would need the same container/domain/profile and lab frames. No RViz or remote display bridge was added.

## Mapping, saving and reuse

After VO validation, use `--mode slam_vo --duration 75 --save-map-after 30` with a fresh run directory/ownership check. `save_map.py` verifies actual SLAM path and runtime mapping enabled before calling the lab save service, then requires nonempty files and SHA256 inventory. Data lives only in that run's `map/`; it is not a Robot Scope PCD/PGM/YAML map.

For a separate active SLAM estimator run, call:

```sh
python3 labctl.py exec --state ../runs/live-new-session/ownership.json -- \
  bash -c 'source /opt/ros/humble/setup.bash; python3 /lab/code/reuse_map.py \
    --current-run /lab/run/slam-reuse --saved-run /lab/run/slam-save \
    --pose-hint /lab/run/pose-hint.json'
```

The explicit pose hint JSON has `position:[x,y,z]`, normalized `quaternion_xyzw:[x,y,z,w]` and nonempty `evidence`, with map-to-camera-base meaning. Do not invent a camera-body transform. This version's `load_map` only sets a folder and returns success; actual `localize_in_map` and pose/output review are essential. The initial single-thread run timed out in 20s and blocked image/output callbacks. The 2026-10-14 recorded-sensor A/B trial changed the default to `component_container_mt`: localization returned false (`CUVSLAM_CAN_NOT_LOCALIZE`, code 3) in 0.547s while odometry continued, and shutdown was clean. Map reuse and loops are not established. `executor:=single` is retained only for reviewed A/B diagnosis. The helper preserves failure and does not retry forever.

## Storage, cleanup and verification

The shared recording archive is mounted at `/lab/recordings`; cumulative limit applies across containers. `bounded_record.py` allowlists stereo images/CameraInfo, optional D435i IMU and lab static TF, records at most 60s, splits SQLite files, reserves shutdown/cache headroom and records rate/cap violations. No `record -a`. Original failed bags were retained. Legacy archives were moved without deletion using `consolidate_recordings.py --apply` after checking each owning container was stopped. If future recordings exist outside the shared archive, consolidate them before recording again. Root-owned raw folders can be inspected from an owned container/archive mount or via an authorized read-only privileged terminal; do not change home permissions globally. `hash_recordings.py` writes fresh closed-bag hashes into `evidence/`.

```sh
python3 labctl.py cleanup --state ../runs/live-new-session/ownership.json
```

Cleanup compares full container ID, ownership label and creation time before stopping only that container. It leaves images/stopped containers/logs/data in place. Finite launchers stop only their own Popen process groups. Watchdog first stops this lab on repeated overload; never stop unrelated work or use prune/pkill. Restore any operational service temporarily stopped under the agreed camera procedure, then check its original active state and operational domain for lab nodes. No `.bashrc`, host-wide environment, firmware, power/clock, ROS or network modification is needed.

Last-session cleanup is idempotent:

```sh
python3 labctl.py cleanup --state ../runs/slam-final-20261013/ownership.json
python3 labctl.py cleanup --state ../runs/live-post-reboot-20261013/ownership.json
```

Offline verification from the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_isaac_vslam_*.py' -v
python3 -m unittest discover -s tests -v
npm run test:unit
npx playwright test -c playwright.resources.config.mjs --reporter=line
```

Optional `rosbags` backend tests skip if unavailable; actual ROS bag inspection/replay was performed in the experiment environment. Synthetic/offline tests check guards, ownership, timing/clock semantics, quotas and evidence; they are not substitutes for hardware or motion validation. No live auto-driving test is included.

## Follow-up diagnostics and replay (2026-10-14)

The current live input is still USB2; no firmware or wiring change was made. SDK motion-only diagnosis also received zero gyro/accel callbacks in 10s. Noise/bias values were zeros, which are not a measured IMU calibration. VIO remains blocked. Build and run this read-only probe only in an owned camera container after exclusive handoff, then release it before any driver:

```sh
python3 labctl.py exec --state ../runs/NEW/ownership.json -- \
  g++ -std=c++17 /lab/code/sdk_motion_probe.cpp -I/usr/local/include \
  -L/usr/local/lib -Wl,-rpath,/usr/local/lib -lrealsense2 -pthread \
  -o /lab/run/sdk_motion_probe
python3 labctl.py exec --state ../runs/NEW/ownership.json -- \
  timeout --signal=INT --kill-after=5s 25s /lab/run/sdk_motion_probe 242322077753
```

For reviewed recorded-sensor replay, use `--evidence-type recorded_sensor_bag`, not `official_bag`. The input contract must set `source.kind=bag_ros`, the actual bag path, and `static_tf_source_topic=/vslam_lab/tf_static` for the retained live bag. Preserve exact sensor transforms; exclude estimator dynamic TF and unverified IMU transforms. `inspect_bag.py` now inventories both recognized static topic names.

An optional bounded reuse attempt can be scheduled by `run_bag.py --mode slam_vo --executor multi --reuse-map-after 10 --saved-run /lab/data/REVIEWED_SAVED_RUN --pose-hint /lab/run/REVIEWED_HINT.json --timeout 45`. Reuse requests require at least 20s remaining. Save/load folder acceptance does not prove localization. The tested existing bag, contracts, hint, copied map and failures are in `runs/followup-offline-20261014/`.

For a fresh coordinated T3 stationary window, the live VO command above accepts `--duration 610` (10s warmup + 600s measurement), with a roughly 650s owned resource watcher. It collects statistics only when `--record-seconds` is omitted. Current follow-up cleanup is:

```sh
python3 labctl.py cleanup --state ../runs/followup-live-20261014/ownership.json
python3 labctl.py cleanup --state ../runs/followup-offline-20261014/ownership.json
```

After the live driver has exited, `sdk_motion_probe 242322077753 --options-only` reads firmware/emitter without opening motion or video streams. Run it inside the still-owned container before cleanup to verify final values. Restore the operational camera service using the approved procedure after cleanup; these wrappers do not manage it. A new camera launch always needs a fresh ownership contract and a new session directory.
