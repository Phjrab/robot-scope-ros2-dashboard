# C1 round 2 — actual contract and composition evidence

Branch: `review/20261029-x-c1-services`. Start HEAD:
`54629c793ad4ae0ea88127f00ed1b7f8805fc4e2`. BASE remains
`f469155c2b0c505f3e472e878f75029d7b8d39df`; fetched main was inspected only.
Canonical contract was published first at
`cb8ccc68be8d96a44b0d38adcff8186893ba2b08`, after 3,106 Python tests
(5 existing skips) and 77 JavaScript test files passed locally.

Final implementation SHA and remote CI receipt are recorded below after publication.
The final delivery HEAD is the commit containing this finalized report; resolve
with `git ls-remote origin refs/heads/review/20261029-x-c1-services`.
The final chat receipt supplies its exact hash (a commit cannot contain its own SHA).

## Changes and ownership

- `expansion_contracts/messages.py`, `time_binding.py`: observation/scene **0.2**
  alongside retained 0.1. Map contracts stay **0.1**. Host ns are lossless decimal
  strings, including receipt times nested in source provenance and full refs.
  The explicit D3 clock/epoch binding conservatively converts the original
  interval; no receipt-based TTL restart or UNKNOWN→CLEAR conversion.
- `expansion_services/scene.py`: accepts D3 full observation metadata refs and
  compares actual identity fields instead of requiring an exact two-key dict.
  Rejected source reset is atomic. Map/source reset clears pairings/assets.
  v0.2 exposes pending/ready/expired/unavailable and suppresses stale/unknown-clock
  payloads while retaining source diagnostics. Missing calibration is UNKNOWN;
  empty objects do not imply known-free. Legacy 0.1 retains its prior raw latest
  behavior with added diagnostics; use 0.2 for expiry suppression.
- `scene_assets.py`, service router: private bounded display-only asset storage
  and authenticated fixed bulk route. Polling returns opaque IDs/revisions.
- `export.py`, service router: bounded verified bundle list, alongside existing
  full-source immutable writer/get/reload. No new registration/solver/storage stack.
- `tests/expansion_services/`: exact composition harness, real loopback HTTP
  transport, dependency preparation, CI import reproducer, scene regressions.
  The one-line import change in **existing C1-owned**
  `tests/expansion_c1/test_services.py` fixes the actual CI defect. All prior test
  assertions remain. No test deletion or skip increase.

The actual baseline router lives in `expansion_services/router.py`; the follow-up
prompt's `api/routers/expansion_offline.py` does not exist in this C1 checkout.
No parallel router/framework was introduced. No counterpart code was edited,
merged, cherry-picked, or copied into the C1 package. No shared app/CI changes.

## Pinned read-only dependencies

| Role | Exact tested SHA |
|---|---|
| D1 | cbedd05ba6f97dad5506e8003302f689ed8fcb4c |
| D2 | c0d266e290a2d29c173d3b83520f8c96efea9447 |
| D3 | 09b68b692fa4b7ccdea39b1a16e3ff150794e12d |
| C2 | 5eed1a9959ca25a4f30bd5b5712806a5ad660c51 |
| C3 | 92658bccc253f31552415f9c9d667bbd28957a06 |
| C4 | b9d700d754f0d3d43b9afdcffcb86e9deb7b1020 |

Each `git archive <SHA>` export is read-only in the temporary dependency root;
composition extends package paths, keeping C1's local package first. Pins and
reproduction scripts are in `tests/expansion_services/`. Dependencies required by
unchanged historical CI comparisons were additionally fetched by exact SHA:
`765622ecbe20dd29b40296dd2ad24fa508ac9443`,
`380800ca9e211495769fe60ee8221e3f4fb40f16`,
`9e9ebcc0cbc613d5b0a7f50a27a7b256c3f829bd`.

## Actual executions and known failures

**Map: PASS / frozen.** Actual D1 `solve_contract` (`d1-rigid-0.1`) runs through
C1's worker. Actual pinned C2 `createC1Ports` produces HTTP requests using Node
fetch against loopback uvicorn. Two generated 400-point sources produce 800
full-source points. Review/apply/export, list/get/reload, XYZ/normals/intensity,
source/output hashes, root ancestry/shared-root rejection, stale apply and
cancellation publication fence pass. C2's existing report/host actually names
C1 `54629c7…`, not the prompt's `457cce8…`; this check builds on that success.
No additional C2/UI tuning or rewrite is needed.

**Observation cores and C4 obstacle sink: PASS on SYNTHETIC inputs.** Actual C4
PointCloud2 layout normalization feeds actual D2 `process_lidar` + `Tracker.step`;
the C1-owned thin test port calls actual D3 `assess` on that output. C4's actual
worker/projection/sink publishes the obstacle into C1. All 2,051 generated raw
points reach D2. The explicitly synthetic clock binding has offset/uncertainty 0;
this is not evidence of any real sensor clock calibration. D3's original
1,000,000,000..1,250,000,000 ns interval is retained after conversion.
Full refs, sensor provenance, geometry bounds and PARTIAL/SPARSE coverage survive.
Positive clearance and an empty scene both remain UNKNOWN. Calibration unknown,
calibration change, source restart/sequence reset, stale/duplicate input, map
revision change and unknown clock are checked separately. Wrong TTL/aliases and
clock/epoch bindings are rejected in contract tests. Missing-input and expiry
examples come from the actual SceneSnapshot service.

**Full observation composition: FAIL at current published consumers.**

- C4 `C1SceneSink` forwards obstacle only. The harness separately supplies the
  real D3 result through C1's explicit converter/ingest port; it does **not** claim
  that C4 forwarded the assessment, pose/joints, plans or costmaps.
- Actual C4 `constraint_from_d3` rejects the converted actual result with
  `D3_COMMAND_CONTEXT_MISMATCH`: command/lease/generation binding is absent and
  its proposed validity keys differ. No permission or COMPLETE_SYNTHETIC evidence
  is fabricated. No command sink is run; no protection is silently downgraded.
- Actual C3 `adaptC1ScenePacket` rejects actual C1 0.1 with
  `C1_DISPLAY_PROFILE_REQUIRED` and 0.2 with `C1_VERSION_UNSUPPORTED`.
  No hand-authored display JSON was substituted to claim a pass. This is a
  consumer compatibility failure, independent of the regression test exit code.

C1's earlier fixture solver and fault-injection unit cases remain **mock/plumbing**
evidence only. Real D1/D2/D3 algorithms here use **generated synthetic** maps and
points, not measured registration accuracy, real YOLO performance, native Nav2,
controller/plant/contact or robot avoidance. ROS/native execution: **NOT_RUN**,
D3-owned follow-up. Real maps/bags/calibration/weights: **INPUT_REQUIRED**.

## Stable scene locations and resource limits

[Canonical contract/matrix](ROUND2_CONTRACT.md),
[actual service examples](round2-scene-examples.json),
[machine-readable results](ROUND2_EVIDENCE.json).

| Data | Produced location / delivery |
|---|---|
| Reference/live cloud, large costmap display bytes | `sources.assets[]`, role `saved_reference_cloud`, `live_cloud`, or `costmap`; ID/revision/byte count/media type/source/`DISPLAY_ONLY` |
| Asset bytes | authenticated `GET /api/v1/extensions/scene/assets/{id}/{revision}`; replaced IDs/revisions return 404 |
| Pose | top-level `robot_pose` observation envelope with `data/health` |
| Plan | top-level `global_path` observation envelope with `data/health` |
| Controller trajectory | top-level `controller_local_trajectory` observation envelope with `data/health` |
| Costmap metadata | top-level `costmap_snapshot` observation envelope; large display bytes use bulk asset ref |
| Assessment | top-level `collision_assessment`; status, original/conversion provenance and validity diagnostics in `sources.collision_assessment` |
| Missing source | null slot, `sources.<slot>.status=unavailable`; no invented source/display profile |

Asset publication is an explicit trusted DI call. Only allowlisted roles/media
and bytes are accepted; no filesystem path, arbitrary URL or shell resolution.
At most 8 assets, 2 MiB each, 8 MiB total; each replacement retires its old ID.
Revision is hashed at publication, never each poll. A tested 1 MB asset stays
outside polling JSON and retrieval/snapshot do not rehash. Map/source reset clears
assets. UI assets are separate from full D1 registration and D2 safety inputs;
no display decimation touches those inputs.

The existing scene bound stays 16 KiB/sample and 80 KiB latest payload total.
The complete 128 KiB wire budget now also accounts for duplicated source health,
with 16 KiB reserved for bounded envelope/asset metadata. Queue/history bounds
remain unchanged. Real synthetic D2 size measurements and rejection reason are
in ROUND2_EVIDENCE.json; 16 objects exceed the default sample limit. The entire
frame is rejected, not silently truncated, and no safety coverage is claimed for
that rejected publication. C4's pinned sink ignores C1's boolean rejection result;
this remains a consumer observability risk for aggregate/fence rejection.

## CI diagnosis and reproducibility

Previous actual C1 run [40828241138](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40828241138)
failed both Python 3.10.22 and 3.12.15 jobs: **3,119 tests, 1 import error,
2 existing skips**. First error is C1's `fastapi.testclient.TestClient` import:
`The starlette.testclient module requires the httpx2 package to be installed.`
No ASCII/UnicodeEncodeError was found in either actual log. The prompt's
3,208/22-error claim is not evidence for this SHA.

Base [40826730094](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40826730094)
at f469155 passed: 3,116 tests/2 skips in Python 3.12.15. Base and branch used the
same CI/workspace path, ubuntu-24.04, Python 3.12.15, FastAPI 0.162.0 and Starlette
1.10.0 with no httpx/httpx2 installed. Locale was not printed by those runners,
so exact remote locale equality is unverified. Base has no C1 TestClient import.
The local venv's optional httpx had masked this defect in round 1.

`reproduce_ci_import.py` executes old and current C1 test-module imports in the
same cwd/interpreter/locale with optional httpx imports blocked. Both ASCII (`C`,
PYTHONUTF8=0, PYTHONCOERCECLOCALE=0) and C.UTF-8 reproduce old FAIL/current PASS.
Local Python is 3.12.3, not the runner's 3.12.15; do not conflate them. The fix uses
already-declared uvicorn plus stdlib real loopback HTTP, preserving assertions.
No shared dependencies, locale settings, workflow or protected code was changed.

```sh
# In the C1 clone, fetch only the exact SHAs in pins.json, then:
python -m tests.expansion_services.prepare_dependencies
PYTHONDONTWRITEBYTECODE=1 python -m tests.expansion_services.composition \
  --deps /tmp/<reported-readonly-dependency-root> --node /path/to/node-24 \
  --output /tmp/c1-round2-composition.json
python -m unittest tests.expansion_c1.test_services \
  tests.expansion_contracts.test_time_binding tests.expansion_services.test_scene -v
C2_CROSS_REQUIRED=1 python -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python -m ruff check robot_dashboard scripts
python scripts/check_repository_secrets.py
LC_ALL=C PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 python -m tests.expansion_services.reproduce_ci_import
LC_ALL=C.UTF-8 python -m tests.expansion_services.reproduce_ci_import
```

## One next action

Have C3/C4 adopt this exact C1 0.2 contract and publish an explicit assessment/
command-context consumer boundary, then repeat this pinned composition. Keep
C2/D1 frozen. Native D3 evidence remains NOT_RUN until its owner supplies it;
this branch makes no native execution claim.

No robot access, main integration, shared product mount, deployment, TF/command
publication or motion occurred. Only the existing C1 branch is published.

## Local final verification and artifacts

- Python 3.12.3: full required suite **3,146 tests PASS, 2 existing skips**
  (optional SVG plotting and rosbags); no newly skipped tests.
- Focused C1 services/contracts/scene: **28 PASS**; historical cross: **33 PASS**.
- Node 24.22.1: **77 test files PASS**, **112 module syntax checks PASS**.
- Ruff over robot_dashboard/scripts, tracked secret scan, diff whitespace: PASS.
- Local mypy: NOT_RUN (module absent); unchanged remote workflow runs it.
- Actual pinned composition: map PASS; D2/D3/C4 obstacle ingestion PASS;
  complete C3/C4 assessment consumer chain FAIL as detailed above.
- Generated display asset/plan example is labelled SYNTHETIC and is not actual
  Nav2/costmap/controller execution.

Artifact file SHA-256 (including final newline):

- `round2-contract-example.json`: `255316ee5218598d2789ab73bb354b1774eda47023522127b5ac6fdc0d210a08`
- `round2-scene-examples.json`: `61b272fb825a7b2b8b8d4c899128c5b16c97bf7f1c3708a20d785266394952b2`
- `ROUND2_EVIDENCE.json`: `d4a8446a477efb4e75108a433b2fbc962e46d42075b9c8266add2f3b881d88df`
