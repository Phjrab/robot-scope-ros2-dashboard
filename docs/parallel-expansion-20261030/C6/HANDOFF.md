# C6 run review handoff

A bounded offline module now imports existing goal evidence, versioned C1 scene
records, and recorded D3 native simulation evidence. It provides play/pause,
seek, one-event step, reverse playback, speed, per-event source time/identity,
C3 scenes, condition-first comparison and allowlisted JSON/Markdown summaries.
Every display is REPLAY; there is no robot/control transport.

## Run locally

From this branch's repository root, with Python project dependencies and Node:

```sh
# Required exact peer objects are included in a normal full clone. No automatic fetch.
python3 tests/expansion_c6/prepare_dependencies.py /private/tmp/c6-owner-deps
PYTHONPATH=. python3 tests/expansion_c6/fixtures.py /private/tmp/c6-fixtures \
  --deps /private/tmp/c6-owner-deps
python3 experiments/expansion_20261030/c6_run_review/serve.py \
  --deps /private/tmp/c6-owner-deps --port 8766
```

Open `http://127.0.0.1:8766/`. Select `review-0.json` for arrival, `review-1.json`
for heading error, `review-2.json` for cancellation, or `review-3.json` for a
C1 scene with a supplied synthetic obstacle, path, expiry, source reconnect and
map change. Select a second bundle in B to compare. The examples are generated
through existing GoalPrecision/GoalEvidenceSink and C1 producer, never REAL.
The server exposes only fixed JS/CSS/HTML roots; imports use the browser file
picker, do not upload files, and do not issue API requests. No directory listing,
CORS, remote binding, or write methods. The host exists only in the C6 experiment.

To import a real file, place an internal manifest beside an accessible local copy
(or provide an explicit root and a safe relative filename):

```json
{
  "schema": "robot-scope.run-review-manifest.v1",
  "format": "goal-evidence-v1",
  "file": "events.jsonl",
  "goal_id": "the-exact-recorded-goal-id",
  "data_kind": "REAL",
  "source_id": "local-recording-label",
  "code_sha": null,
  "clock_domain": null,
  "source_epoch": null
}
```

Unknown metadata stays null. Set code SHA/clock/epoch only from evidence; a source
label is operator-declared provenance, not hardware qualification. Multiple goals
in one sink are selected by exact ID. Use a second manifest for another goal.

```sh
python3 -m robot_dashboard.run_review --root /private/path/to/local-copy \
  --manifest run-a.json --compare-manifest run-b.json \
  --deps /private/tmp/c6-owner-deps --output /private/tmp/c6-review-output
```

Outputs must be new paths. `review.private.json` and `compare.private.json` retain
bounded detailed data and belong in private storage. `summary.json`, `summary.md`
and comparison outputs contain only the public allowlist. The event table is
limited to 80 entries, with explicit truncation. Raw contexts, logs, URIs, IPs,
paths, weights, environment files, videos, PCD and assets never enter that
projection. Free-text identities are hashed. Requested goal, numeric pose/error
and original ns fields are allowed; they are not rounded. Output files are 0600.

## Supported formats and time semantics

- `goal-evidence-v1`: actual `robot-scope.goal-evidence-log.v1` JSONL. The producer's
  sparse samples, dispatch/accepted/result/zero/stop rows are supported. Independent
  missing events are UNOBSERVED. An endpoint is labelled ENDPOINT_ONLY; it is not
  converted into an invented path. Result state and final XY/yaw are separate.
- `c1-scene-v1`: JSONL archive records with schema
  `robot-scope.c1-scene-record.v1`, `packet` (unaltered canonical C1 0.1 or 0.2),
  `context` (explicit C3 map/frame/units/source and stream epochs/clock/calibration),
  and `recorded_at: {stamp_ns, clock_domain, source_epoch}`. This is **C6's internal
  archive envelope, not a new C1 DTO**. See generated `scenes.jsonl` and fixtures.py.
  Actual pinned C1 validation is mandatory. Retired source sequences, rollback and
  returned retired contexts fail import; seek cannot bypass their rejection.
- `d3-native-v1`: fixed existing `competition-nav2-result.v1` /
  `c3-native-observations.v1` result, trace and observations JSON files, with explicit
  result/trace/observations filenames and the fixture's recorded goal/map identity.
  Existing C1 SceneSnapshotService projects recorded path/2D pose into display
  envelopes. Float seconds stay original in event payloads; ns used by C3 are
  explicitly rounded display values, not original ns capture precision. Source
  sim clock and recorded host monotonic receipt remain distinct. Native result
  has no result receipt timestamp, so its terminal metrics are labelled native
  report final, never near-result or measured-stop samples.

Source ns and C1 0.1 integer ns are normalized losslessly in Python to decimal
strings before JS sees them. JS uses BigInt. Replay offsets are a separate clock:
within a known clock/epoch they use recorded deltas; missing time, clock changes
and rollback use explicit record-order fallback, not latency. Same-time events
are ordered by 1 ns in the playhead only. Original timestamps are unchanged.
Pausing freezes the replay clock, not a sensor clock. Recorded age/expiry is added
to replay elapsed time; it is never reset to current browser/server time.

Seek/reverse/map or context changes destroy the C3 consumer, subscriptions,
overlay and scene state before rebuilding the selected historical slice. Bulk
asset references are retained as metadata but **never fetched**. Therefore there
is no cross-map asset cache or external URL resolver. Path and obstacle geometry
must be present in the supplied record. Missing pose/joints/shape remain missing.
The host's main renderer lacks a public articulated-joint setter, so it hides the
robot model when that capability is unavailable; exact numeric pose remains in
the event inspector. No guessed joint pose is drawn. Native costmap bytes are
metadata-only in this minimal adapter; no new grid/URDF/point-cloud renderer.

ZERO issuance, bridge ACK, measured stop and contact are distinct. The goal sink
has no Nav2 success timestamp, so the UI and summary say result receipt. Body
motion/map correction is reused only for the producer's exact-stamp paired SE3
samples with the same generation; its translation norm is 3D, not XY. Simulation
contact counts are labelled simulated and never physical contact confirmation.

Comparison shows code, parameter revision/observed-parameter digest, map identity,
goal identity/pose and source kind first. Unknown or different metadata means
REFERENCE_COMPARISON_NOT_SAME_CONDITION_AB. Matching metadata is still not causal
proof. No algorithm improvement percentage is generated.

Limits: 32 MiB per input file, 256 KiB JSONL records, 20,000 rows/events,
32 MiB retained event/frame budget, depth 32, at most 24 h replay time in browser.
Native result JSON alone permits 4 MiB because the existing report includes graph
snapshots. Paths must be local relative JSON/JSONL below the explicit root;
no-follow FD traversal rejects symlinks/traversal/nonregular files. General
archives are rejected. The optional prepare_native helper handles only the exact
hash-pinned reviewed artifact and four fixed member names per case, with byte
limits; it never extracts arbitrary archive paths.

## Actual artifacts and verification

Dependency pins and reuse inventory: [INTAKE.md](INTAKE.md).
Results and honest boundaries: [VALIDATION.md](VALIDATION.md).

The existing D3 artifact is run 40840774827, artifact 12882393645, SHA256
`0f09cf101555dbef3368fc6913acd9cdd61e380ad45c51472ea5e6b1b3cdc6aa`.
If a local downloaded copy is available:

```sh
python3 tests/expansion_c6/prepare_native.py /private/tmp/native.zip /private/tmp/c6-native
PYTHONPATH=. python3 tests/expansion_c6/verify_artifacts.py \
  --deps /private/tmp/c6-owner-deps --native-root /private/tmp/c6-native \
  --output /private/tmp/c6-artifact-check
C6_DEPS=/private/tmp/c6-owner-deps python3 -m unittest discover -s tests/expansion_c6 -t tests -v
node --test tests/expansion_c6/test_replay.mjs
```

The artifact verifier optionally accepts `--goal-root` and `--goal-code-sha` for
local real evidence. It checks exact original goal/pose/stamp equality and input
hash immutability. No private path is hardcoded in published code or summaries.
`browser.mjs` uses the existing Playwright installation and loopback host; set
C6_FIXTURES, C6_NATIVE_REVIEW and C6_SCREENSHOT. C6_PLAYWRIGHT_PACKAGE is optional
when dependencies are installed in this clone. C6 tests are included in normal
Python discovery; actual peer tests require C6_DEPS and report explicit skips
without it. The mock JS clock/adapter tests run in normal CI via the Python test.
No workflow was changed to fetch peer branches or private data.

## Product connection and remaining inputs

Future host: import `mountRunReview(host, {scene, mountScene, adaptScene,
clearScene})`; inject C3's existing mount and adapter. `scene` supplies C3's canvas,
project, setRobot and optional view/focus hooks. The isolated host reuses the
existing renderer's `_project` read access as C3's own host does; a product-owned
public projection/joint port is required for product integration. No app mount or
API root wiring is included here. C6 does not require any C7 output.

INPUT_REQUIRED only for a real producer-owned canonical C1 archive, recorded joint
observations/calibration, and independent bridge ACK/contact evidence if those
claims are desired. The accessible real goal sink and all five D3 simulation
records were available and checked. Generic bags, camera datasets, 3D bulk assets,
live DDS, robot access, deployment, physical motion and a full production
C4→D2→D3 chain are outside this candidate and NOT_RUN. The candidate is frozen at
the commit containing this handoff; resolve its exact HEAD with `git rev-parse
HEAD`. The delivery receipt reports that SHA, remote equality and its CI URL.
