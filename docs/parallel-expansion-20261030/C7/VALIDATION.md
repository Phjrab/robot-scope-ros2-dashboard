# C7 validation receipt

## 2026-10-30 remote CI follow-up

**Verification closure: BLOCKED_EXTERNAL_OWNER.** Original run
[40932918269](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40932918269)
at `3d77ac29e34205d8173085dae950bb999cfdf816` failed one browser test on each
Ubuntu image. Its original logs, artifacts, and failure counts are retained.
See [CI_INVESTIGATION.md](CI_INVESTIGATION.md) for separate cause assessments,
the source/environment comparison, and exact owner handoffs.

No existing C7 implementation or test changed. The follow-up adds manual
read-only reproduction probes and evidence documents only. Shared UI/tests,
workflow, dependencies, timeout values, assertions, and historical performance
results are unchanged. “After” below means an unchanged-source replay, **not a
fixed defect or demonstrated performance improvement**.

| Check / environment | Before | Follow-up result |
|---|---|---|
| Ubuntu 22.04 hosted / Python 3.10.22, C7 complete browser suite | 226 pass / history :90 fail (#54/227) | Original failure retained; local 22.04 standalone NOT_RUN |
| Ubuntu 24.04 hosted / Python 3.12.15, C7 complete browser suite | 226 pass / mount :343 fail (#143/227) | Original failure retained; hosted replay belongs to submission CI |
| Exact main hosted CI | Both 227-test browser suites and both 10-test mission suites pass | Baseline logs downloaded and compared |
| Local Ubuntu 24.04.5 / Python 3.12.3, each failing test in its own process | NOT_RUN in previous receipt | Main 1/1 + 1/1; C7 1/1 + 1/1; all PASS |
| Local C7 full browser suite, original order / one worker | NOT_RUN in previous receipt | 227 PASS, 7.8 min |
| Main/C7 controller overlap probes | NOT_RUN | Both REPRODUCED_SHARED_POLL_OPEN_RACE |
| Main/C7 real context-close probes | NOT_RUN | Both REPRODUCED_SHARED_FIXTURE_TIMER_LEAK; retained intervals 1→2→3 |
| C7 real-owner regression | Earlier macOS PASS | 7 PASS / 0 skip; isolated child executes 3 actual-owner checks |
| C3 exact pinned JS unit suites | Earlier macOS 38 PASS | 38 PASS / 0 skip |
| Full Python with C7 exports and C2 historical checks required | Earlier macOS 3,139 / 4 skips | 3,139 PASS, 2 existing skips, 99.227 s |
| Full JS / syntax | Earlier 700 / 112 PASS | 700 PASS / 0 skip; 112 modules checked |
| Local mission real-API fixture E2E | Original remote step not run after browser failure | 10 PASS, 39.9 s; synthetic fixture only |
| Ruff / mypy | Earlier PASS | PASS, including new C7 Python analyzer; mypy configured 4 files |
| Exact owner source verification | 8,690 immutable blobs | 8,690 verified after follow-up execution |
| Original results JSON→Markdown | PASS | Byte-identical regeneration; original data unchanged |

Local optional skips: SVG plotting dependency absent, rosbags backend absent.
The ordinary CI still does not provide `C7_DEPENDENCY_ROOT`; its pre-existing
external-owner wrapper skip is not claimed as real-owner validation. No skip was
added or removed. Local full-browser, Python, and extra browser workloads were
run sequentially; unrelated desktop/chat load was not controlled.

The initial local sandbox denied the static server's localhost bind (EPERM), so
that setup attempt did not run tests. The same tests then ran with authorized
local-process permissions. The first new manual socket probe used an already
created about:blank document and failed before opening the mocked socket; the
probe was corrected to navigate to an in-memory same-origin document after route
registration. Shared test and product sources were never changed for either.

### Commands executed for this follow-up

From the independent C7 clone, with dedicated dependencies installed from the
unchanged requirements and lockfile:

```sh
export PATH=/tmp/c7-ci-runtime/node-v20.20.2-linux-x64/bin:/tmp/c7-ci-runtime/venv/bin:$PATH
export PLAYWRIGHT_BROWSERS_PATH=/tmp/c3-scene-browsers
EVIDENCE=/home/desktop1/Documents/ChatGPT/robot/c7-ci-evidence-20261030
node experiments/expansion_20261030/c7_capacity/ci/history_poll_probe.mjs .
node experiments/expansion_20261030/c7_capacity/ci/history_poll_probe.mjs ../c7-ci-main-20261030
node experiments/expansion_20261030/c7_capacity/ci/socket_cleanup_probe.mjs .
node experiments/expansion_20261030/c7_capacity/ci/socket_cleanup_probe.mjs ../c7-ci-main-20261030
npx playwright test tests/e2e/global_observation_history.spec.mjs:90 --reporter=line --trace=on --output="$EVIDENCE/c7-history-single"
npx playwright test tests/e2e/mount_calibration.spec.mjs:343 --reporter=line --trace=on --output="$EVIDENCE/c7-mount-single"
npm run test:e2e:ci -- --output="$EVIDENCE/c7-full"
PYTHONDONTWRITEBYTECODE=1 python3 -m robot_dashboard.expansion_diagnostics prepare --output /tmp/c7-ci-runtime/owner-exports
PYTHONDONTWRITEBYTECODE=1 C7_DEPENDENCY_ROOT=/tmp/c7-ci-runtime/owner-exports python3 -m unittest discover -s tests/expansion_c7 -v
PYTHONDONTWRITEBYTECODE=1 C7_DEPENDENCY_ROOT=/tmp/c7-ci-runtime/owner-exports C2_CROSS_REQUIRED=1 python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node --test /tmp/c7-ci-runtime/owner-exports/C3/tests/expansion_c3/test_consumer.mjs /tmp/c7-ci-runtime/owner-exports/C3/tests/expansion_c3/test_canonical.mjs /tmp/c7-ci-runtime/owner-exports/C3/tests/expansion_c3/test_assets.mjs
node scripts/check_frontend_syntax.mjs
python3 -m ruff check robot_dashboard scripts tests/expansion_c7 experiments/expansion_20261030/c7_capacity/ci
python3 -m mypy --config-file mypy.ini
npx playwright test --config playwright.competition.config.mjs --reporter=line --output="$EVIDENCE/mission"
python3 -m robot_dashboard.expansion_diagnostics summarize experiments/expansion_20261030/c7_capacity/results.json --output "$EVIDENCE/regenerated-results.md"
cmp experiments/expansion_20261030/c7_capacity/results.md "$EVIDENCE/regenerated-results.md"
```

Both individual browser commands were also executed from the independent main
clone, using distinct `main-history-single` and `main-mount-single` outputs.
The initial two-test selections are preserved as additional focused runs in the
manifest; they are separate from the true individual runs and the full suite.
Probes are diagnostic observations, not tests declaring a known defect acceptable.

Logs/trace hashes and structured outcomes are in `VALIDATION.json` and
[`ci-evidence/manifest.json`](ci-evidence/manifest.json). The new commit's literal
SHA and terminal remote CI cannot be embedded in that same commit. Resolve the
submitted commit with `git log -1 --format=%H -- docs/parallel-expansion-20261030/C7/CI_INVESTIGATION.md`.
The final chat receipt records its literal SHA, remote equality, Actions run ID,
and terminal result. Never inherit a CI pass from main or a previous attempt.

## Historical implementation receipt (preserved)

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
