# C5 local UI review reproduction

This is an opt-in browser presentation experiment. Production HTML, app,
navigation, renderer, shared CSS, C2 and C3 are unchanged. No product wiring,
service proxy, robot access, ROS, sensor acquisition or deployment is included.

## Pinned inputs

See [source-manifest.json](source-manifest.json) for the four exact Git SHAs and
SHA256 verification of inspected documents and peer feature files. The initial
ordinary clone fetched remote branches once; peer references were not refreshed.
Do not merge/copy peer implementation into this branch.

From the C5 clone, export the existing Git objects to a **new** temporary path:

```sh
mkdir -p /private/tmp/robot-scope-c5-sources/{c1,c2,c3}
git archive 50600c7bce6f5fae743cd836ca1d8ee68d91b05a | tar -x -C /private/tmp/robot-scope-c5-sources/c1
git archive 7625c87ede2489143c44862d883e10fc1791df28 | tar -x -C /private/tmp/robot-scope-c5-sources/c2
git archive 5bf58097f4a67806f5515b931a3b8013d65bf01e | tar -x -C /private/tmp/robot-scope-c5-sources/c3
chmod -R a-w /private/tmp/robot-scope-c5-sources
npm ci --ignore-scripts
npx playwright install chromium webkit
node tests/expansion_c5/browser.mjs
node tests/expansion_c5/peer_review.mjs
node tests/expansion_c5/scene_capture.mjs
```

Set `C5_PEERS` to a different existing export directory when needed. `hosts.mjs`
starts the repository's existing main static host, C2 fixture host and C3 fixture
host at 127.0.0.1 ports 4265–4268, and terminates only its child processes. It
refuses to reuse a host after a child exits. Run these scripts sequentially;
do not stop an unrelated server to free a port. No C2 service proxy is enabled.
Main uses the existing `installDashboardBackend`. C2/C3 use their actual peer
modules and supplied fixtures; no new renderer, solver, adapter or UI state
implementation is substituted.

`browser.mjs` injects the C5 CSS/module only after capturing the unenhanced DOM.
It checks Chromium/WebKit, 390/768/1440 CSS px, both themes, 2× DPR, 200% root
font size, keyboard, emulated touch, async states and explicit confirmation.
It preserves raw states and compares actual official URDF draw poses and mock
request payloads before/after. All actual browser network traffic is restricted
to the selected loopback host. Native iPhone Safari and real touch hardware
are not covered. Root font enlargement is not a claim of OS/browser zoom QA.

`peer_review.mjs` reads the exact archived C3 endpoint bodies, calls C3's actual
`adaptC1ScenePacket`, and displays them with the existing C3 feature. It does not
run C1/D1/D2/D3, renew timestamps, invent missing bulk assets, or simulate real
sensor acquisition. Archived native `REPLAY` and synthetic `SYNTHETIC` remain
separate. The `ACTUAL_C1_SERVICE` source enum is preserved by C3's adapter and
is not evidence of a current HTTP service run. The fixture banner identifies
the archived replay. The final checks reproduce C5-H1 against the untouched C3
module and compare expiry using a second unchanged C3 consumer.

## Existing regression

```sh
UI_REGRESSION_PORT=4275 UI_PROBE_PORT=4276 UI_EVIDENCE_ROOT=/private/tmp/c5-theme-regression npx playwright test --config tests/expansion_c5/regression.config.mjs --reporter=line
npm run test:unit
node scripts/check_frontend_syntax.mjs
python3 -m unittest discover -s tests -v
python3 -m ruff check robot_dashboard scripts
python3 -m mypy --config-file mypy.ini
python3 scripts/check_repository_secrets.py
```

Use a Python 3.12 virtual environment with requirements.txt,
requirements-competition-offline.txt and requirements-quality.txt. On macOS set
TMPDIR to a real, writable path such as `/private/tmp/c5-python-tmp` (create it
first, and ensure its group matches `id -gn`); `/var/...` symlink aliases violate an existing capture-path test. macOS inherits the parent directory group, so a wheel-owned temporary directory fails the existing ownership check when the test expects staff. Set
`OPENBLAS_NUM_THREADS=1`. Do not change that production path validation.

C5's custom browser and peer checks are **explicit local checks**, not added to
shared CI. Existing CI still checks the unchanged main behavior and general
repository regressions. Historical failures and final results are separated in
[HANDOFF](../../../docs/parallel-expansion-20261030/C5/HANDOFF.md).
