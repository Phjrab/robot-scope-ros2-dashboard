# C2 synthetic / exact dependency test host

This host exercises the insertable module only. It reads shared theme and
RobotScene3D files; it does not load the product app or connect to a robot.
Generated points/PCDs remain in memory or temporary directories. Only generators,
checks, verification reports and explicitly labeled screenshots are committed.

Local fixture view:

```sh
node experiments/expansion_20261029/c2_map_ui/server.mjs
# Open http://127.0.0.1:4182 only; ?scenario=ambiguous / disconnected / empty /
# unsupported / loading-failure / preview-failure / job-failure / save-failure / large
```

Unit checks (Node >=20):

```sh
node --test --test-isolation=none tests/expansion_c2/*.test.mjs
```

Exact dependencies (no merge/copy into submission):

```sh
C1_EXPORT=/tmp/c2-c1-exact-54629c7
D1_EXPORT=/tmp/c2-d1-exact-cbedd05
mkdir -p "$C1_EXPORT" "$D1_EXPORT"
git fetch origin 54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 cbedd05ba6f97dad5506e8003302f689ed8fcb4c
git archive 54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 \
  robot_dashboard/expansion_contracts robot_dashboard/expansion_services robot_dashboard/pcd_editing \
  | tar -x -C "$C1_EXPORT"
git archive cbedd05ba6f97dad5506e8003302f689ed8fcb4c \
  robot_dashboard/multimap_core robot_dashboard/relocalization/experimental_se3.py \
  experiments/expansion_20261029/d1_multimap | tar -x -C "$D1_EXPORT"
PYTHONPATH="$C1_EXPORT" python3 experiments/expansion_20261029/c2_map_ui/export_c1_fixture.py > /tmp/c2-c1-contract-fixture.json
C2_C1_FIXTURE=/tmp/c2-c1-contract-fixture.json C2_C1_EXPORT="$C1_EXPORT" \
  node --test --test-isolation=none tests/expansion_c2/*.test.mjs
PYTHONPATH="$C1_EXPORT:$D1_EXPORT" OPENBLAS_NUM_THREADS=1 \
  python3 experiments/expansion_20261029/c2_map_ui/exact_service_host.py
# It prints C2_EXACT_URL=http://127.0.0.1:<ephemeral port>; use that below.
```

In another terminal, with Playwright/Chromium available:

```sh
C2_C1_FIXTURE=/tmp/c2-c1-contract-fixture.json \
C2_C1_SERVICE_URL=http://127.0.0.1:<printed-port> \
  node tests/expansion_c2/browser.e2e.mjs
```

`C2_PLAYWRIGHT_MODULE` may point to an installed Playwright `index.mjs`;
`PLAYWRIGHT_BROWSERS_PATH` may select a temporary browser install. The run binds
only loopback, audits browser requests and fixture ports, writes
`browser-results.json` and screenshots under the owned C2 documentation path.
C1/D1 imports are read from external exports; C2 never copies their code.
Dependencies for the actual synthetic service: repository requirements plus
scipy. The final regression environment is recorded in `python-environment.txt`.

The exact service host composes C1's existing router/catalogue/manager/store with
D1's existing `solve_contract`; it invokes the D1 generator to create two 400-point
synthetic sources. Known transforms are entered through the UI as manual priors.
C1 performs full-source export and GET verifies the manifest/hash. Product source
registration remains deferred by C1 and is displayed honestly by C2.
