# Robot-side perception shadow runtime

## Status and boundary

WP03 adds a standalone, observation-only runtime for the Go2-mounted Jetson.
It does not add a dashboard result API; that belongs to WP04. It has no ROS,
motion, lease, control-key, model-upload or shell-command surface. The local
health endpoint is fixed to `127.0.0.1:8091/health` and accepts GET only.

The software boundary is:

```text
D435i color device
  -> existing realsense_mjpeg_relay.py (only camera owner)
       -> remote dashboard preview (fixed dashboard host)
       -> local shadow sidecar (exact relay host, one bounded viewer)
            -> LatestFrameHub (depth 1)
                 -> independent Lane worker
                 -> independent Object worker
                 -> optional Depth SUMMARY worker
            -> loopback health only
```

The relay attaches a per-process source epoch, source sequence and the
robot-kernel monotonic timestamp recorded when the encoded JPEG enters the hub
to every part. The sidecar refuses frames without that metadata and assigns a
separate monotonically increasing runtime result sequence across relay
reconnects. This is not a D435 hardware-clock timestamp. Both processes use
the same robot-side monotonic clock; WP04 must not subtract it from an
external-host monotonic timestamp.

Inference and preview never open the camera separately. A sidecar crash closes
one relay viewer; it cannot stop or restart the independent relay service.

## Verified target inventory (read-only, 2026-08-30)

| Item | Observed value |
|---|---|
| Architecture | `aarch64` |
| Python | 3.8.10 |
| Jetson release | R35.3.1 / JetPack 5.1.1 family |
| TensorRT Python | 8.5.2.2 |
| OpenCV | 4.2.0 |
| NumPy / Pillow | available |
| ONNX Runtime | unavailable |
| PyCUDA / cuda-python | unavailable |
| RealSense relay policy | active, disabled (manual start) |
| Relay at inspection | idle, zero viewers, no capture process |

This is compatibility inventory, not load acceptance. The installed relay hash
also differed from repository HEAD, so deployment must update the relay and
sidecar together before a hardware shadow test.

## Model contract

Manifests and artifacts live under the fixed root
`/var/lib/robot-scope/perception/models`. Environment values select one safe
manifest filename; they cannot provide paths, URLs or Python modules.

Required manifest shape:

```json
{
  "schema": "robot-scope.perception-model/v1",
  "model_id": "lane-demo-001",
  "task": "lane",
  "backend": "tensorrt",
  "artifact": "lane-demo-001.engine",
  "artifact_sha256": "<64 lowercase hexadecimal characters>",
  "source_model_sha256": "<64 lowercase hexadecimal characters>",
  "output_adapter": "lane_v1",
  "input": {"width": 640, "height": 480, "color": "RGB"},
  "target": {"machine": "aarch64", "jetpack": "R35.3.1", "tensorrt": "8.5.2.2"}
}
```

The loader rejects symlinks, path traversal, unknown schemas/tasks/backends,
oversize files, artifact hash mismatch and target/runtime mismatch. TensorRT
metadata is accepted only when it exactly matches the target where the engine
was built. WP03 does not silently fall back from TensorRT to ONNX.

The TensorRT 8.x adapter uses the target's fixed CUDA runtime library and does
not require PyCUDA or cuda-python. It accepts exactly one FP32 NCHW input with
the manifest dimensions, exactly one output, at most 16 bindings and at most
512 MiB of aggregate device buffers. Output tensors must use the fixed
`lane_v1`, `yolo_xyxy_v1` (postprocessed Nx6), or `depth_summary_v1` contract.
Deserialization, shape, allocation, copy or execution failure clears the
result and reports the engine `FAILED`; it never selects another backend.

The included ONNX adapter is comparison/development only and requires a
dedicated environment containing ONNX Runtime. It supports the fixed
`lane_v1` and `yolo_xyxy_v1` output adapters. The observed robot-side system
Python does not currently contain ONNX Runtime, and no package was installed by
this work.

## Resource protection

- one latest frame only; no per-engine image queues;
- each worker owns an independent thread and rate gate;
- slow workers skip sequence gaps and increment `superseded_frames`;
- results are erased on stale input or inference exception;
- at most 120 latency/FPS samples are retained;
- detections are capped at 100;
- JPEG and multipart headers have fixed size bounds;
- thermal sysfs is read without commands; unavailable throttle data remains
  `UNVERIFIED`;
- systemd caps memory, tasks and file descriptors;
- systemd uses a closed device policy with only the observed JetPack GPU nodes;
  no `/dev/video*`, CSI, ISP, encoder or decoder node is granted;
- point-cloud mode accepts only `OFF` and `SUMMARY`; raw and decimated modes
  are rejected in WP03.

Health includes model ID/hash/backend, FPS, p50/p95 inference time, source age
and sequence, superseded/stale/failure counts, thermal availability and a
bounded redacted error. It explicitly reports `motion_authority=false`, zero
command publishers, and `raw_pointcloud_generated=false`.

## Deployment gate (do not run without a separate operator approval)

The unit examples do not enable or start anything. Before installation, record
the existing relay state and verify the model package offline. Install into a
dedicated Python environment if ONNX comparison is required; never modify the
system Python as a convenience.

```bash
systemctl is-enabled robot-scope-realsense-camera.service
systemctl is-active robot-scope-realsense-camera.service
sha256sum /usr/local/libexec/robot-scope/realsense_mjpeg_relay.py

# Review and install exact root-owned files, but do not start either service.
sudo install -o root -g root -m 0755 scripts/realsense_mjpeg_relay.py \
  /usr/local/libexec/robot-scope/realsense_mjpeg_relay.py
sudo install -o root -g root -m 0755 scripts/robot_side_perception_shadow.py \
  /usr/local/libexec/robot-scope/robot_side_perception_shadow.py
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-perception-shadow.service.example \
  /etc/systemd/system/robot-scope-perception-shadow.service
sudo systemctl daemon-reload
systemctl is-enabled robot-scope-perception-shadow.service
systemctl is-active robot-scope-perception-shadow.service
```

Expected pre-test state is `disabled` and `inactive`. A separately approved
manual test starts the already-reviewed relay first, then the sidecar, without
changing enablement. Local health should show `mode=SHADOW`, the exact model
hashes, queue depth no greater than one, and no command publishers.

```bash
sudo systemctl start robot-scope-realsense-camera.service
sudo systemctl start robot-scope-perception-shadow.service
curl -fsS http://127.0.0.1:8091/health
```

Hardware acceptance remains `BLOCKED` until approved model artifacts exist and
the following are recorded: relay+Lane+YOLO coexistence, source FPS/age,
per-model and combined FPS/p50/p95, CPU/GPU/RAM/swap, temperature/throttling,
preview on/off comparison, current robot-service freshness, and a 30-minute
soak. No public benchmark substitutes for these measurements.

## Rollback

Stop only the sidecar first. Its failure must leave the relay unchanged.

For a model-only rollback, stop the sidecar, verify the immutable previous
manifest and artifact hashes, atomically install a mode-0600 host-local env
that selects those previous filenames, and start the sidecar manually. Do not
rename a new artifact to an old model ID and do not edit a manifest hash. The
health model ID/hash must match the recorded previous pair before the shadow
session resumes.

```bash
sudo systemctl stop robot-scope-perception-shadow.service
systemctl is-active robot-scope-realsense-camera.service
sudo rm -f /etc/systemd/system/robot-scope-perception-shadow.service
sudo rm -f /usr/local/libexec/robot-scope/robot_side_perception_shadow.py
sudo systemctl daemon-reload
```

Restore the previously recorded relay script only if the WP03 relay metadata
change itself must be rolled back and only after preserving its previous
active/disabled state. Never remove model or dataset directories as part of a
runtime rollback. Unknown or mismatched model artifacts remain inactive.
