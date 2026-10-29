# C7 validation receipt

The source/evidence commit is the commit containing this file. Resolve its exact
SHA with `git log -1 --format=%H -- robot_dashboard/expansion_diagnostics` and the
submitted branch HEAD with `git rev-parse HEAD`. Final chat receipt reports the
literal pushed HEAD, remote equality and that exact commit's terminal CI status.
CI is not claimed successful in advance or inherited from another owner/commit.

## Local result

| Check | Result |
|---|---|
| First small baseline | PASS, actual C4 normalization/D2/D3/C1, preserved separately |
| Finite capacity comparison + exact wire/sample/compact boundaries | PASS |
| Current canonical C4/D2/D3 → C1 ASGI HTTP → C3 parser/consumer | PASS; drawable collision intentionally unavailable |
| Delayed actual C4 worker with actual D2 | PASS; one executing + one pending, 58 replaced / 2 processed / 1 latest |
| Stale/map/clock + history | PASS |
| C1 aggregate/assets; actual C3 existing cache | PASS |
| C3 existing browser load | 11 PASS; generated UI fixture, not canonical render or native evidence |
| Focused C7 | 7 PASS, no skip; external wrapper executes 3 real-owner tests |
| Unfiltered repository Python | **3,139 run, OK, 4 existing skips**, 139.568 s |
| Repository JS | **700 PASS**, zero skip/failure |
| C3 pinned JS unit suites | **38 PASS**, zero skip/failure |
| Shared JS syntax | **112 modules PASS**; C7 two CLI JS probes separately checked |
| Ruff | PASS, repository robot_dashboard/scripts plus C7 tests |
| mypy | PASS, existing configured 4-file scope |
| Secret scan / whitespace / ownership | PASS after staging; no protected file changes |
| Source export verification | PASS, 8,690 matching read-only source blobs before/after |
| JSON → Markdown regeneration | PASS, byte-identical summary from saved results |
| Robot/ROS/native/controller/real sensor/Jetson | **NOT_RUN** |
| Sensor-to-render latency | **UNKNOWN**, no measured cross-clock mapping |

Four existing skips: optional SVG plotting, optional rosbags, Linux process
sessions `/proc`, and Linux fd inventory. No test was removed or criterion changed.
The ordinary remote CI has no exported owners and explicitly skips C7's external
wrapper; it must not be relabeled local real-owner integration coverage.

## Initial failures retained

1. Default macOS TMPDIR under `/var`: 3,139 run, 125 errors, 2 failures, 4 skips.
   All 125 errors were existing symlink/path storage guards. Acceptance fixture
   also failed path checks. One overlay timing test failed here and passed on
   isolated rerun and in both later full runs. No threshold was changed.
2. `/private/tmp`: 3,139 run, 3 errors, 7 failures, 4 skips. Parent group inheritance
   caused existing calibration artifact ownership checks to fail (9 cases).
   One supervisor subprocess timed out at its unchanged 3 s criterion.
3. Created a private temporary parent with actual current UID/GID and no symlink.
   The affected 15-test subset passed; unfiltered full suite passed with that
   environment. This changes only the test temporary directory, not source,
   calibration policy, production directories, or a test assertion.

Log hashes and precise test summaries are in [VALIDATION.json](VALIDATION.json).
Large full logs remain local `/tmp/c7-*`; no private hardware data is published.

## Exact executed commands

From the independent C7 clone; initial `prepare` output `/tmp/c7-exact-deps` is
read-only and pinned. Dependencies use a dedicated `.venv` (Python 3.13).
The final JSON records actual numerical package versions. This environment is
not claimed identical to the Linux CI matrix's pinned dependencies.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m robot_dashboard.expansion_diagnostics prepare --output /tmp/c7-exact-deps
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m robot_dashboard.expansion_diagnostics run --deps /tmp/c7-exact-deps --output experiments/expansion_20261030/c7_capacity/baseline.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m robot_dashboard.expansion_diagnostics browser --deps /tmp/c7-exact-deps --playwright /Users/hajoonpark/자율설계/robot-scope-ros2-dashboard/node_modules/playwright/index.js --output experiments/expansion_20261030/c7_capacity/browser.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m robot_dashboard.expansion_diagnostics run --deps /tmp/c7-exact-deps --profile bounded --browser-report experiments/expansion_20261030/c7_capacity/browser.json --config-snapshot experiments/expansion_20261030/c7_capacity/baseline.json --output experiments/expansion_20261030/c7_capacity/results.json
TMPDIR=/private/tmp/c7-tests-owned PATH="$PWD/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 C7_DEPENDENCY_ROOT=/tmp/c7-exact-deps python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 C7_DEPENDENCY_ROOT=/tmp/c7-exact-deps .venv/bin/python -m unittest discover -s tests/expansion_c7 -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
node --test /tmp/c7-exact-deps/C3/tests/expansion_c3/test_consumer.mjs /tmp/c7-exact-deps/C3/tests/expansion_c3/test_canonical.mjs /tmp/c7-exact-deps/C3/tests/expansion_c3/test_assets.mjs
node --check robot_dashboard/expansion_diagnostics/consumer.mjs
node --check robot_dashboard/expansion_diagnostics/cache.mjs
.venv/bin/python -m ruff check robot_dashboard scripts tests/expansion_c7
.venv/bin/python -m mypy --config-file mypy.ini
.venv/bin/python scripts/check_repository_secrets.py
.venv/bin/python -m robot_dashboard.expansion_diagnostics summarize experiments/expansion_20261030/c7_capacity/results.json --output /tmp/c7-regenerated.md
cmp experiments/expansion_20261030/c7_capacity/results.md /tmp/c7-regenerated.md
git diff --cached --check
```

C7 only uses observational wrappers around owner public calls and logical file
reads, restoring temporarily wrapped I/O functions in `finally`. No owner source
file is edited. Large generated PCDs and browser trace/screenshot files are scoped
temporary artifacts and are removed. Source archive locations and local developer
venv are not included in the Git submission.
