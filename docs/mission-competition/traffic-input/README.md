# C4 traffic input and offline replay

This opt-in package connects an explicit local owner model to original RGB,
native-coordinate detections, the existing VM color/quality implementation,
and its temporal filter. Importing the package starts nothing. There is no
camera acquisition, ROS subscription, HTTP ingestion endpoint, command
publisher, mission executor, or automatic registration.

2026-10-27 follow-up: the teammate's actual `best.pt` is acquired and loaded.
See [TEAMMATE_MODEL_INTAKE.md](TEAMMATE_MODEL_INTAKE.md) for the explicit three-class
consensus config, comparison commands, current validation and remaining RGB gap.
The historical model/environment and ROUND3/ROUND4 results below remain separate.

The pinned base actually contains `traffic_signals/detector.py::LocalUltralytics`,
not the prompt's proposed `OptionalYoloAdapter`/`detector_adapter.py` names.
The VM loader and `core.py` are imported read-only. `OwnerModel.infer` uses
the same loaded CPU model, collecting post-NMS class counts before allowlist filtering. Do not replace them
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
classes are checked against the actual loaded names; this generic model's IDs
carry no color semantics. Its class 9 is `traffic light`. The new teammate policy
uses a separately verified three-class mapping and preserves both model and C4 color.
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
clock. Temporal stability uses original arrival times, not inference completion
times. Source age, receiver elapsed time and inter-frame gap are distinct.
No subtraction of remote host monotonic values is performed. Offline records
retain original capture metadata but use `source_clock=fixture` and an
explicit virtual timeline; they can never enter the production projection.

The unchanged VM defaults are stability 0.4 s and TTL/gap 0.25 s. Gaps and
sequence holes reset stability; no interpolation or clock acceleration is
used. Raw diagnostic inference can still be recorded for a new frame after a
gap, but its stable observation remains UNKNOWN. Duplicate sequences, source
stamps or receipts do not call the detector again. Identical content is a
separate diagnostic and is allowed with verified advancing source identity.
`identity_verified` defaults to false; the trusted owner establishes it from
actual camera epoch/sequence/stamp, never from a payload flag or polling nonce.
Unverified identity blocks stable evidence even when counters advance.

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
source/receiver evidence. First receipt and source age at that receipt are stored
in the observation; a caller cannot reanchor them. `signal_status` exposes reasons,
original identity and last valid observation time when no fragment is available.
It returns only signal fields, never a complete
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


## Follow-up diagnosis and two clocks

`--clock-mode source-timeline` (default) preserves manifest capture intervals;
CPU duration is reported separately and never masquerades as capture staleness.
`--clock-mode wall-clock` paces a local fixture receiver at those intervals and
includes inference/queue delay in age. Delayed processing retains the scheduled
first receipt, so slow offline processing fails freshness in this workload mode.
Neither mode verifies the historical sensor clock or Jetson online readiness.
All records remain `fixture`; missing historical epoch/sequence are not invented
as real camera metadata. `--fps` only supplies timing when the input has none.
No subsampling, interpolation, TTL extension or threshold tuning is performed.

Per-frame `context.diagnostics` records post-NMS counts, non-allowlisted classes,
configured confidence rejections, expected-ROI IoUs, association/crop/color/time
rejections and repeated content. `DETECTOR_MISSING` means no remaining traffic
candidate; `EXPECTED_ROI_MISMATCH` means candidates exist outside the expected
region. The detector's 0.25 floor and NMS suppress raw predictions before this
boundary; below-floor counts are explicitly NOT_OBSERVABLE_AFTER_NMS. A lower
explicit config floor is honored by the loader, but this study uses 0.25 unchanged.
Terminal rejection is one ordered reason; stage diagnostics and quality flags
are non-exclusive and must not be added as disjoint counts.

Private labeled audit (labels are never detector input):

```sh
python -m robot_dashboard.competition_traffic.diagnose \
  --input-root /absolute/private/work \
  --labels docs/mission-competition/traffic-input/real-labels.json \
  --config /absolute/owner-v3-config.json --model /absolute/yolov8n.pt \
  --output /absolute/new-private-label-audit --acknowledge-trusted-pickle
```

This writes original-coordinate overlays, exact native crops, contact sheets and
`evaluation.json`. Cyan=detector; yellow=fixed expected ROI where applicable;
magenta=visually labeled target. Display enlargement uses nearest-neighbor,
without color enhancement. Manual-crop oracle color is reported separately from
localized raw predictions and is never used for stable production evidence.
NO_LIGHT images count false GREEN from any candidate, without requiring a GT box.
See [FOLLOWUP](../../parallel-review/20261024/C4/FOLLOWUP.md) for dataset bias,
exact counts, integration contracts and minimal missing inputs.

## C1 dedicated CI jobs

Weight-free unit/contract job: Python 3.12, numpy==1.26.4,
opencv-python-headless==4.10.0.84, jsonschema==4.10.3; no torch, Ultralytics,
model, ROS, hardware or private imagery is needed. Require zero skipped tests:

```sh
python - <<'PYTEST'
import unittest
suite = unittest.defaultTestLoader.discover('tests/competition_traffic', top_level_dir='tests')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() and result.testsRun >= 90 and not result.skipped else 1)
PYTEST
```

Private replay job: additionally use CPU torch/torchvision plus the pinned
requirements-replay.txt environment above and provision the owner weights,
config and original files from private storage. Run both clock modes to separate
algorithm timing from local workload, then the labeled audit. Keep image artifacts
private. Exit 0 verifies execution, not green performance or robot readiness.
The base CI installs neither cv2 nor jsonschema and may SKIP these optional
modules; that is not a perception test PASS. No CI/shared requirement was edited.

## Round 3: fixed search profiles and bounded image association

The default remains `full640`. Opt-in `--inference-profile full960`, `full1280`
or `upper-overlap640` uses the same frozen CPU weights. The last profile combines
one full image and three predefined overlapping upper tiles, each at imgsz 640:
normalized xyxy `[0,0,.5,.6]`, `[.25,0,.75,.6]`, `[.5,0,1,.6]`. Internal crop-edge
boxes are rejected, offsets map to native pixels once, and class-aware native
NMS uses IoU .5. Tile positions never depend on a label, target ROI or color.
The canonical `inference_settings_sha256` covers model, resolution, tile geometry,
confidence floor and fusion settings; keep it alongside config/model/binding hashes.

`--observation-mode detection-only` records each detector box and raw color in
`context.free_observations`. These have no mission identity or stable state.
The separate `detection_only_overlay` PNG labels raw boxes and the observation
stage. It is never used as `processed_image` or as a canonical signal ROI.
`observation_stage` distinguishes detection-only, verified associated, and stable.
A diagnostic fixed ROI remains unverified even when a box overlaps it.

In mission mode, bounded image association requires a unique expected-region
match and geometric continuity; it ignores transient detector IDs and color.
After occlusion, ambiguity, geometry jump, invalid input, model failure or stale
processing, two fresh consistent detections must re-establish association.
Temporal stability then starts again. This is an image-space constraint, not
moving-camera pose/crossing calibration. `verified` must come from the trusted
camera/crossing/approach binding, never be set from this match alone.

`--lamp-experiment` appends diagnostic measurements for UNKNOWN/AMBIGUOUS detector
crops: whole housing, fixed upper 55% combined color, and upper raw HSV. It does
not change the VM core, mission color, minimum pixels or TTL. The required real
samples did not improve, so this experiment is not an adopted classifier.
`--no-image-artifacts` retains JSON without writing PNG copies during timing runs.

```sh
python -m robot_dashboard.competition_traffic.experiments \
  --input-root /absolute/private/work \
  --labels docs/mission-competition/traffic-input/real-labels.json \
  --config /absolute/owner-v3-config.json --model /absolute/yolov8n.pt \
  --output /absolute/new-search-comparison \
  --include-confidence-ablation --acknowledge-trusted-pickle
python -m robot_dashboard.competition_traffic.replay \
  --input /absolute/private/frames.jsonl --fps 5 \
  --config /absolute/owner-v3-config.json --model /absolute/yolov8n.pt \
  --inference-profile upper-overlap640 --observation-mode detection-only \
  --output /absolute/new-free-observation --acknowledge-trusted-pickle
```

The comparison uses already viewed exploratory labels, not an independent test.
Confidence .10 is a separately reported ablation; no gain justified adoption.
A recovered GREEN target does not qualify a profile for deployment: the full
session also exposes false GREEN on bus-stop signs and unreadable signal backs.
See [ROUND3](../../parallel-review/20261024/C4/ROUND3.md),
[results](round3-results.json), [post-selection audit](round3-green-audit.json),
and the [synthetic timing I/O example](round3-timing-example.json).

C1/C2 must call `signal_fragment(obs, now_s=now)` or confirm
`received_s=obs.context['first_received_s']`. The previous instruction
`received_s=processed_s` is invalid and raises `FIRST_RECEIPT_MISMATCH`.
Preserve source age at first receipt separately from age at completion;
`queue_residence_s`, `processing_started_s`, `processed_s`, `pipeline_wall_s`
and detector `inference_wall_s` expose delay. Source age at use is
`source_age_at_first_receipt_s + now - first_received_s` on the same host.
No completion timestamp, polling time or new inference profile refreshes TTL.
An inference beyond .25 s remains inspectable but cannot supply fresh GREEN.

## Round 4: frozen, unadopted emitting-region candidate

`--emitter-profile enclosed-chroma-v1` enables one experimental validator on the
original native detector crop. It checks an interior chromatic component's size,
position, HSV V intensity and dark surrounding ring. It uses the original VM
color mask; it does not enhance pixels or prove physical emission/front-facing
identity. Raw diagnostic color is always retained. Unsupported results are
UNKNOWN in the candidate view; the opt-in pipeline restricts the selected color
accordingly. The default is **off**. This candidate is **not qualified for
production or a live mission**: on the viewed data it rejected all 153 boxes,
including every known real GREEN and readable RED. No threshold retuning followed.

The existing `inference_settings_sha256` includes the complete optional
`emitter_validation` descriptor. There is no second emitter hash. The old hash
is unchanged when the option is absent. Changing the combined profile resets
existing temporal/association evidence. First receipt/source age semantics are
unchanged; emitter time is included in completion/freshness accounting.
`context.emitter_validation_wall_s` and each free box's duration expose its cost;
model-reported preprocessing/inference/postprocessing times are diagnostic seconds.
The overlay keeps raw color and `emit UNKNOWN/RED/GREEN` distinct from mission stage.
The earlier first-receipt integration request is already resolved in C1
`85c5b6b8` and C2 `8a58370b`; ROUND4 does not reopen it. If C1 later adopts new
search/emitter settings, bind the combined settings hash at the trusted owner
boundary. This unadopted candidate does not request production enablement.

```sh
python -m robot_dashboard.competition_traffic.experiments \
  --input-root /absolute/private/work \
  --labels docs/mission-competition/traffic-input/real-labels.json \
  --config /absolute/owner-v3-config.json --model /absolute/yolov8n.pt \
  --output /absolute/new-emitter-audit \
  --emitter-profile enclosed-chroma-v1 --acknowledge-trusted-pickle
```

This mode freezes search to upper-overlap640/confidence .25 and refuses confidence
ablation. Labels only score outputs. The existing replay CLI accepts the same
optional profile. Do not use latency from overlapping or aborted runs as an A/B
benchmark. See [ROUND4](../../parallel-review/20261024/C4/ROUND4.md),
[results](round4-results.json), [GREEN audit](round4-green-audit.json) and the
[one-window data request](EMITTER_DATA_REQUEST.md). The candidate is frozen pending
new independently reviewed data; it is not a successful false-GREEN solution.
