# C4 offline adapter reproduction

Run from repository root. `PYTHONPATH=.:tests` exposes only this checkout and its
fixture generators. Install the root requirements plus httpx/Pillow in a private
temporary venv for repository regression tests; runtime ports need only stdlib.

```bash
python3 -m unittest discover -s tests/expansion_c4 -t tests -v
PYTHONPATH=.:tests python3 experiments/expansion_20261029/c4_runtime/smoke.py
PYTHONPATH=.:tests python3 experiments/expansion_20261029/c4_runtime/compat_c1.py --export /tmp/c4-c1-2402c02c-readonly
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
```

In this desktop's restricted sandbox, the first full unittest run stopped in
asyncio teardown because cross-thread self-pipe wakeups were suppressed. The
successful full run used an unrestricted local process with the test-only
`offline_test_guard.py` copied to `/tmp/c4-network-guard/sitecustomize.py`, then
`PYTHONPATH=/tmp/c4-network-guard:. python3 -m unittest discover -s tests -v`.
The audit hook rejects non-loopback connect/bind/sendto and external DNS before
any endpoint is contacted. No robot/ROS/remote graph was used. Focused async
tests use a test-only timer, matching the repository's existing documented
sandbox workaround. System Node 18 had seven ESM loader failures; the bundled
Node 24.22.1 passed all 77 JS files without product changes.

For the compatibility check, independently obtain a read-only export of
`robot_dashboard/expansion_contracts` at exact C1 SHA
`2402c02c6f91ba54064894b21735e01b98610acd`. The script imports that external
package through an explicitly extended package search path; no C1 source belongs
in this branch. C1's service was absent at that bootstrap SHA, so its method
signature is a fixture. D2/D3/C3 remain fixtures/pending exact published SHAs.

The smoke feeds 1,200 generated padded PointCloud2 messages through D2 fixture,
existing latest-only worker and a bounded scene sink. It verifies ZERO/hold at
the actual memory-only command sink. Clock is virtual; zero timing values are
not a hardware latency benchmark. It never initializes ROS or a detector.

Profile generation can be checked offline:

```bash
PYTHONPATH=. python3 experiments/expansion_20261029/c4_runtime/prepare_profile.py \
  --envelope-radius-m .65 --padding-m .1 --output /tmp/c4-review-parameters.yaml
```

The radius is a synthetic fixture value. D3 must supply real reviewed envelope
inputs before interpreting planning safety. Native launch execution and its
matrix belong to D3; this C4 environment has no ROS/native plugin installation.
See INTEGRATION_POINTS for opt-in arguments, isolation preflight, required
effective readback, observations versus enforcement and rollback boundaries.
Nothing in these commands contacts a robot or changes product registration.
