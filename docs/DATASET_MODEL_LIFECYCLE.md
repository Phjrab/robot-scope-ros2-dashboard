# WP05 Dataset and model lifecycle

## Safety boundary

Dataset export and model lifecycle never publish ROS topics or motion commands.
The dashboard exposes model state through `GET /api/v1/models` and
`GET /api/v1/models/active`; there is deliberately no remote activation or
rollback endpoint. Browser refresh, service restart and network reconnect do
not change the active model. The target operator performs every model mutation
locally with `scripts/model_registry_tool.py`.

Runtime datasets, exports, model packages, ONNX files, TensorRT engines, build
logs and registry files stay below private runtime roots and are not Git
artifacts. A Dataset label is an operator-facing session name, not ground
truth. Raw JPEG files remain unlabelled until the laptop labelling step.

## Dataset manifest v2

The existing session and atomic sample directory layout is unchanged. Manifest
v2 adds capture profile, robot-side source identity, network topology revision,
deployed Git commit, preview profile, shadow state, model IDs, created/finalized
timestamps, drop counters and the exact quota/reserve policy. Existing
`started_at`, `completed_at`, `drop_counts` and gallery fields remain available.

Each sample records the external receive sequence and leaves
`capture_source_sequence=null` because neither current camera transport exposes
a trustworthy hardware capture counter. It also records the camera snapshot
timestamp with an explicitly unverified domain, external Orin receive monotonic
time, image SHA-256 and an optional bounded perception result reference.
`cross_host_clock_verified=false` is mandatory until WP07 records a measured
clock-domain contract.

Set these deployment values before collection:

```text
ROBOT_SCOPE_NETWORK_TOPOLOGY_REVISION=<reviewed-topology-revision>
ROBOT_SCOPE_GIT_COMMIT=<exact-lowercase-deployed-commit>
ROBOT_SCOPE_MODEL_REGISTRY_DIR=<absolute-private-runtime-directory>
```

## Finalized export contract

The Sensors Dataset folder view enables `EXPORT FINALIZED ZIP` only for a
completed session. The server creates the name and opaque export ID. Export:

- accepts only a managed session ID and `state=completed` manifest;
- walks only expected manifest/sample/JPEG paths and rejects symlinks;
- allows at most 4,096 files and 20 GiB, additionally capped by session quota;
- checks the existing filesystem reserve before and during publication;
- stores entries without decompression ambiguity;
- writes `SHA256SUMS.json` for every exported file;
- replaces the private temporary archive atomically, then publishes metadata;
- removes temporary, archive and sidecar artifacts on cancellation or failure;
- counts as Dataset work, so dashboard lifecycle stop/restart remains blocked.

The browser receives only an opaque download URL, filename, size and hashes.
The exported manifest replaces the dashboard's private filesystem path with
`managed-dataset-root`.

## Laptop handoff

1. Stop and finalize each raw session in Robot Scope.
2. Export and copy the ZIP to the laptop. Verify the outer SHA-256 shown in the
   UI and every entry in `SHA256SUMS.json` before extraction.
3. Preserve each session as one indivisible split group. Do not place
   consecutive frames from the same session in both train and validation/test.
4. Label copies of raw images with a versioned class taxonomy. The session
   label is not imported as an image label.
5. Record train/validation/test session IDs, training code commit, metrics and
   preprocessing. Train on the laptop or another external GPU system, never on
   either competition Jetson.
6. Export ONNX and create a root-only ZIP with exactly:

```text
model.onnx
labels.yaml
metadata.json
evaluation.json
sha256.txt
```

`labels.yaml` must be the exact class-name list in `metadata.json`.
`sha256.txt` contains one line: `<model.onnx sha256>  model.onnx`. Use
`deploy/model-package-metadata.json.example` as the metadata contract.

## Target Jetson validation

Actual TensorRT generation remains `BLOCKED` until a supervised hardware run.
For an approved stationary test, keep Control DISARMED, Navigation STOPPED and
the perception service manually managed:

1. Copy the package ZIP to a private temporary path on the Go2-mounted Jetson.
2. Set `ROBOT_SCOPE_MODEL_REGISTRY_DIR` to the same reviewed private registry
   root used by the dashboard service.
3. Run `python3 scripts/model_registry_tool.py stage <package.zip>`. This only
   produces `staged`; it never activates.
4. Build `engine.plan` on that exact Jetson with the installed TensorRT. Record
   JetPack, TensorRT and GPU identity. Keep the build log below 256 KiB and
   redact credentials/private values.
5. Run the WP03 shadow smoke and resource gates. Do not set either evidence
   boolean true without recorded PASS evidence.
6. Hash the engine and build log, fill
   `deploy/engine-validation.json.example`, then run:

```text
python3 scripts/model_registry_tool.py validate-engine <model_id> <engine.plan> <evidence.json> <build.log>
```

Invalid package/hash/schema evidence and secret-like logs fail closed. A target
identity, shadow-smoke or resource-gate mismatch records `rejected`. Every
failure leaves the active model unchanged.

## Explicit activation and rollback

After reviewing the `validated` record:

```text
python3 scripts/model_registry_tool.py activate <model_id> --confirm <model_id>
python3 scripts/model_registry_tool.py active
```

The registry re-hashes the immutable package and engine, then atomically swaps
one registry manifest. The old active entry becomes `previous`. If publication
fails, the in-memory and on-disk active record stay unchanged. Reconfirm health
after activation; if runtime health fails, stop the shadow service using the
approved manual procedure and roll back:

```text
python3 scripts/model_registry_tool.py rollback <task> --confirm-active-model <current_model_id>
```

Rollback re-hashes the previous engine and atomically exchanges `active` and
`previous`. It does not delete packages, engines, datasets or maps.

## WP05 rollback

To disable only the dashboard projection, remove the optional model registry
argument/environment value and restart later under the normal lifecycle gate.
Do not delete the registry. Dataset manifest v2 remains backward-compatible
with the existing gallery fields. Export ZIP files may be copied off-host and
removed later only through an explicitly reviewed retention procedure; WP05
adds no browser delete API.
