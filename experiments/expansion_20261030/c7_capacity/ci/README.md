# C7 CI failure reproductions

These manual diagnostics import unchanged shared sources. They do not add hooks
to the application, modify another owner's source, run a robot service, skip a
test, change a timeout, or change an assertion. An output beginning `REPRODUCED_`
means a defect was observed, not that the product passed validation.

Use separate clones at these exact revisions:

```sh
git clone --branch review/20261030-x-c7-capacity-diagnostics https://github.com/Phjrab/robot-scope-ros2-dashboard.git c7-ci
git -C c7-ci rev-parse HEAD
git clone --no-hardlinks --no-checkout c7-ci main-ci
git -C main-ci checkout --detach 5154761bba6fa4f171881e61f986901e2b415ed9
```

The original C7 failure source is `3d77ac29e34205d8173085dae950bb999cfdf816`.
Keep a separate checkout at that SHA when repeating the original unmodified
suite; run the new probes from the investigation checkout with the target
repository as their argument. No branch reset is needed.

With Node 20.20.2 / npm 10.8.2 on PATH, run `npm ci --ignore-scripts` in each
target clone, then `npx playwright install chromium`. The lockfile pins
Playwright 1.62.1 / Chromium 151.0.7922.34. The static server's origin probe
also requires the repository Python dependencies; use an isolated venv.

## Original evidence

```sh
mkdir -p evidence
for job in 123655803080 123655803545 123655803596; do
  gh api repos/Phjrab/robot-scope-ros2-dashboard/actions/jobs/$job/logs > evidence/job-$job.log
done
for artifact in 12924402324 12924267721; do
  gh api repos/Phjrab/robot-scope-ros2-dashboard/actions/artifacts/$artifact/zip > evidence/artifact-$artifact.zip
done
python3 experiments/expansion_20261030/c7_capacity/ci/summarize_original_traces.py \
  evidence/artifact-12924402324.zip evidence/artifact-12924267721.zip > evidence/original-trace-summary.json
```

The parser reads ZIP members as JSON/text data without executing trace content.
Raw archives should be retained separately; the report includes their hashes.

## Exact tests and suite order

Run in each target checkout, separately from Python and other browser workloads:

```sh
npx playwright test tests/e2e/global_observation_history.spec.mjs:90 \
  --reporter=line --trace=on --output=/tmp/c7-history-single
npx playwright test tests/e2e/mount_calibration.spec.mjs:343 \
  --reporter=line --trace=on --output=/tmp/c7-mount-single
npm run test:e2e:ci -- --output=/tmp/c7-full
```

Use distinct output directories per SHA/environment/run. Do not conflate the
individual test runs with the full 227-test sequence. The original CI configuration
already uses one worker and no retries. A local Ubuntu 24.04 / Python 3.12.3 run
does not represent Ubuntu 22.04 / Python 3.10.22 or hosted Python 3.12.15.

## Deterministic history overlap

```sh
node experiments/expansion_20261030/c7_capacity/ci/history_poll_probe.mjs /absolute/target/checkout
```

The real controller polls behind an explicit promise gate. The probe attempts
one historical open while the status read is pending, completes the status read,
then separately retries. It records changed notifications, detail requests and
the missing-job error, without modifying the controller or requiring a server.

## Shared fixture lifetime

```sh
node experiments/expansion_20261030/c7_capacity/ci/socket_cleanup_probe.mjs /absolute/target/checkout
```

This uses the target checkout's actual `installDashboardBackend` and Playwright.
It opens one intercepted synthetic camera socket, closes the entire browser
context, and observes fixture interval callbacks for 300 ms, three times in one
process. No WebSocket connects to a server. Node interval interception only
observes calls originating in `tests/e2e/dashboard_backend.mjs`. The probe clears
all intervals it recorded and restores the original functions in `finally`.
Its local cleanup is not a patch to the shared suite.

Full evidence and owner acceptance criteria are in
[`CI_INVESTIGATION.md`](../../../../docs/parallel-expansion-20261030/C7/CI_INVESTIGATION.md).
