# WP05: read-only offline experiment view

## Implemented boundary

`/static/experiments.html` is a separate dashboard page linked from the
sidebar and overview. It uses the existing dependency-free `RobotScene3D` for
two bounded scenes: synthetic reference-map preview and registered query
preview aligned by the experimental `T_target_source`. Initial and estimated
poses are marked separately to avoid overlapping labels; numeric results show
both full 6DoF poses, synthetic truth and error when present, candidate/reject
reason, overlap, residual, runtime, memory, optional SE2 comparison, source
commit, input digests and implementation digests. It contains no apply, ARM,
lease, initial-pose, goal or mission action.

The browser reads a user-selected local JSON file using `File.text()`. There
is no result upload, new HTTP API, arbitrary server path, or persistence.
Only the existing synthetic SE3 benchmark schema is accepted at present.
`RECORDED_DATA`, `SIMULATION`, and `LIVE_VERIFIED` are not displayed because
the available benchmark does not supply evidence for them. The label
`SYNTHETIC · NOT LIVE` remains visible throughout. An absent truth is shown
as **정답 없음**, never as zero error. The Nav2 field is explicitly
`ACTUAL_NAV2_NOT_RUN` rather than a mock path presented as Nav2.

The updated benchmark emits a UTC generation time and at most 256 deterministic
preview points per cloud per case; its PCDs still live only inside a temporary
directory. The read-only viewer rejects files over 5 MB, malformed results,
unsupported provenance, timestamps over 30 days old or over five minutes in
the future, and comparison against a different manifest, reference/query PCD
digest, or seed. The synthetic target digest is a **revision surrogate for this
experiment**, not a D0 map-family ID or a verified production map revision.
Recorded or live experiments will need an explicit D0 lineage-aware report
contract before this view accepts them. Displayed local artifacts are
validated for structure and consistency, not cryptographically attested.

The scene renderer's pre-existing optional-bounds check was fixed: a cloud
without advertised bounds now uses sampled bounds instead of throwing. This
also preserves existing live/Cockpit behavior and has a dedicated regression
test.

## Reproduce without robot or Jetson

```sh
python3 scripts/benchmark_experimental_se3.py --output /tmp/se3-baseline.json --require-expected
python3 scripts/benchmark_experimental_se3.py --output /tmp/se3-candidate.json --require-expected
```

Open `/static/experiments.html` on a locally served dashboard, select the
candidate file, then optionally the baseline file. The browser compares only
when exact synthetic inputs match. A prepared bounded-SE2 executable can be
passed with `--se2-executable` to include its separate 3DoF result; the viewer
never derives z/roll/pitch from SE2. Browser-file selection does not contact
the dashboard server. Do not commit the generated JSON if it contains new
recorded data or derived PCD payloads.

One local WP05 rerun from the same synthetic cases yielded 11 cases,
6 SE3 candidates, 0 false candidates, 0 expected-status mismatches, a
10.3 ms p50 and 112.3 ms p95 runtime, and a 442,281-byte JSON report.
These are MacBook numbers from the new benchmark run, not Jetson or robot
measurements. The working tree was dirty while generating this sample; its
report honestly records `source_tree_dirty=true`. Loading that report and a
same-input baseline into the local browser displayed both scenes and a
zero-delta self-comparison. A no-truth repeated-structure case displayed
“정답 없음 · 정확도 계산 안 함.”

## Validation and deferred work

The focused JS validator rejects a forged live label, stale report, malformed
point and mismatched input. The renderer regression checks absent advertised
bounds. The existing SE3 Python test checks deterministic preview points and
the timestamp. Local browser smoke verified the page layout, 3D scenes,
baseline comparison, provenance and no-truth display. The automated Playwright
spec is included, but could not run on this MacBook because the Playwright
executable is absent and the npm registry was unreachable; this is not a
passing E2E result.

Final checks on this checkout: focused report/scene JS tests 13 passed;
`npm run test:unit` passed 334; `node scripts/check_frontend_syntax.mjs`
checked 68 modules; and the existing dependency-complete Python environment
passed 1,483 tests with one Linux-only skip. The required plain
`python3 -m unittest discover -s tests -v` ran 1,441 tests but ended with
five missing FastAPI/Pydantic import errors in the system interpreter; those
same tests passed with the already-present dependency environment. Running
`npm run test:e2e -- --grep 'offline experiment'` returned
`playwright: command not found`. No package or system dependency was installed.

Actual recorded clouds, independent ground truth, a D0-linked map revision,
real Nav2 planner-only results and live hardware evidence remain unavailable
or unverified. Once the robot is powered, those require a separate approved
plan for recording sensor/TF provenance, checking true 3D localization error
against independent truth, validating map-family lineage and planning under
isolated Nav2. None is run or scheduled here. No operating service, map,
calibration, control threshold or hardware process was changed.
