# C4 traffic input and offline replay

This opt-in package connects an explicit local owner model to original RGB,
native-coordinate detections, the existing VM color/quality implementation,
and its temporal filter. Importing the package starts nothing. There is no
camera acquisition, ROS subscription, HTTP ingestion endpoint, command
publisher, mission executor, or automatic registration.

The pinned base actually contains `traffic_signals/detector.py::LocalUltralytics`,
not the prompt's proposed `OptionalYoloAdapter`/`detector_adapter.py` names.
That implementation and `core.py` are imported read-only. Do not replace them
with an unrelated detector or silently copy another branch's revisions.

## Setup and commands

From the repository root, create a dedicated environment; do not change the
robot's environment. A CPU environment tested here uses Python 3.12.3,
torch 2.6.0+cpu, torchvision 0.21.0+cpu, Ultralytics 8.3.203,
OpenCV 4.10.0 and NumPy 1.26.4.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r robot_dashboard/competition_traffic/requirements-replay.txt
export YOLO_CONFIG_DIR=/absolute/private/work/yolo-config
export MPLCONFIGDIR=/absolute/private/work/mpl-config
export YOLO_OFFLINE=true
export YOLO_AUTOINSTALL=false
.venv/bin/python -m robot_dashboard.competition_traffic.replay \
  --input /absolute/original-rgb-directory --fps 5 \
  --output /absolute/new-inspection-directory --dry-run
.venv/bin/python -m robot_dashboard.competition_traffic.replay \
  --model /absolute/owner-model.pt --config /absolute/config.json \
  --input /absolute/frames.jsonl --fps 5 \
  --output /absolute/new-replay-directory --acknowledge-trusted-pickle
.venv/bin/python -m unittest discover -s tests/competition_traffic -t tests -v
```

`--dry-run` hashes and decodes originals without model loading. Exit codes:
0 successful complete requested replay/inspection; 2 missing model or binding
configuration (an inspection can still have decoded every image); 3 setup,
dependency, schema, I/O or model-load failure; 4 decoded-frame/model-inference
failure. A valid UNKNOWN/RED/ambiguous detection is not a CLI failure. Inspect
`summary.json`, `failure.json` when present, and `observations.jsonl`.
An output directory must not already exist. No original file is overwritten.

Input can be one image, a directory's direct image children, a Robot Scope
dataset (`samples/*/go2_front.jpg`), a local video file, or explicit JSONL.
Device indices, URLs, live streams and camera subscriptions are not accepted.
VideoCapture appears only in the local-video provider after file validation.
The explicit `--fps` is a replay schedule, never proof of sensor time.
JSONL preserves gaps using `replay_time_s`; images must remain under its
parent directory. Example row (replace the hash with actual original bytes):

```json
{"image":"00000001.jpg","sha256":"0000000000000000000000000000000000000000000000000000000000000000","replay_time_s":0.0,"captured_at":"recorded timestamp","source_clock_verified":false}
```

`owner-model-example.json` is a deliberately unverified binding for the
provided v3 Go2 imagery. Its manually inspected ROI is a diagnostic image
region, not a calibrated course/map association. Do not promote it to a
production binding. `verified=false` always prevents stable GREEN. Model
classes are checked against the actual loaded names; class IDs are never
interpreted as RED/GREEN. The provided model's class 9 is `traffic light`.
Its checkpoint says version `8.0.0.dev0`; 8.3.203 is the explicitly tested
compatible replay loader, not a claim about its exact training environment.
The SHA and user-supplied path establish which file was inspected, not a
general guarantee that arbitrary pickle weights are safe. The CLI requires
both provenance configuration and explicit trusted-pickle acknowledgement.

## Time, identity and fail-closed behavior

`Frame` carries source ID, epoch, sequence, source nanoseconds as a string,
source-clock type/verification, independently computed source age, receiver
monotonic arrival, binding ID, image handle and provenance. The existing
camera owner transfers an immutable JPEG through `from_owner_jpeg` or a
decoded BGR `Frame`; this module never acquires a stream demand token.

`TrafficPipeline.process(frame, now_s=receiver_monotonic)` accounts for model
latency using its same-host clock for live sources. Tests can inject that
clock. Source age, receiver elapsed time and inter-frame gap are distinct.
No subtraction of remote host monotonic values is performed. Offline records
retain original capture metadata but use `source_clock=fixture` and an
explicit virtual timeline; they can never enter the production projection.

The unchanged VM defaults are stability 0.4 s and TTL/gap 0.25 s. Gaps and
sequence holes reset stability; no interpolation or clock acceleration is
used. Raw diagnostic inference can still be recorded for a new frame after a
gap, but its stable observation remains UNKNOWN. Duplicate sequences, source
stamps, receipts or repeated image handles do not call the detector again.
The repeated-content guard is conservative: identical consecutive JPEG bytes
are withheld even if an upstream owner reports a new sequence.

Epoch retirement and sequence high-water marks survive invalid/stale color
updates. They are per pipeline instance and in memory; create one instance
per owner lifecycle, and use a new producer epoch after restarting the owner.
The owner must enforce durable replay protection across process restarts.
`current_state(now_s=...)` is a read-only watchdog: it never manufactures a
new observation, sequence, image or source timestamp from an old GREEN.

Native Ultralytics boxes are never inverse-letterboxed twice. Explicit
letterbox results use the original VM inverse function, with an earlier
padding/truncation check so clamping cannot hide a clipped ROI. Different
image sizes, missing mappings, uncertain candidate association, multiple
equally plausible detections, tiny/corrupt/saturated/black ROIs, model errors
and stale clocks fail closed. Color/quality thresholds were not tuned to
make the real images pass.

## Evidence and artifacts

`Observation.signal` is a subset of fields in the existing canonical
`competition-evidence.v0.1`, validated against those definitions in tests.
It is deliberately incomplete: mission ownership, map pose, goal identity,
feet, physical STOP, posture, obstacle/path clearance and crossing completion
are not fabricated. The sidecar `context` records local provenance and null
unconnected components; it is not a new canonical runtime enum/schema.

`signal_fragment` rejects offline records, unverified bindings and expired
source/receiver evidence. It returns only signal fields, never a complete
mission Evidence or departure authorization. The trusted in-process C2 owner
must retain the original receiver arrival time (never reset it on polling),
validate source/epoch/sequence and expected signal/crossing, and join separate
physical evidence. Do not accept a browser-supplied fragment as trusted data.

Replay artifacts distinguish original decoded full image, native ROI crop,
and processed color mask. Source file hashes identify original JPEG/video
bytes; a lossless PNG decode is explicitly labeled a decoded original, not
the original compressed byte stream. `processed_image` references a mask.
The VM classifier exposes its CLAHE branch's state/metrics but not its pixels;
no fabricated enhanced image is saved. A future D0 change could return those
pixels through an optional diagnostic field without changing classifications.

## Integration proposals (not applied)

1. C1: keep ownership in `robot_dashboard/ros/cameras.py` and its
   `snapshots()`/`camera_snapshot_locked()` path, as reused by
   `dataset_capture.py`. The snapshot API's unverified camera stamp and remote
   monotonic fields are insufficient to claim `synchronized_*`; add verified
   source metadata at the existing owner boundary before calling this package.
2. C1: register image handles in the existing authenticated/private image
   delivery path. The replay directory mapping is local only; no endpoint or
   startup wiring was added here. Keep work off the camera callback thread.
3. C2: join the signal fragment only after mission identity/generation/owner
   validation. Keep command TTL 0.25 s separate from the fixture executor's
   0.5 s evidence gap. A green color does not establish physical stop or feet.
4. D0: preserve this wrapper's read-only imports and validate new signatures
   before integration. Detection indices are transient, not permanent tracks.
   Expose CLAHE diagnostic pixels only as a separate optional return value.

No other branch was merged/copied. Integration compatibility remains NOT_RUN.
Rollback removes the new package, dedicated tests and documentation; existing
app/runtime/VM/camera/schema files and robot state are unaffected.

## Dependency references

Loader version: [Ultralytics 8.3.203](https://pypi.org/project/ultralytics/8.3.203/).
CPU package pairing: [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/).
The actual installed code and successful local replay, not the newest web
examples, establish the compatibility result reported here.
