# C4 round 2 — reproducible actual owner composition

Run in the existing C4 clone, Python 3.10+ with repository dependencies and scipy.
No package here starts ROS, HTTP listeners, device acquisition or a controller.
The HTTP test uses FastAPI/Starlette ASGI TestClient and the **actual C1 router**;
authorization is a synthetic host fixture, no TCP server or product router mount.

Fetch these explicit objects once (GitHub only), then export outside the repo:

```sh
git fetch origin \
  54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 \
  c0d266e290a2d29c173d3b83520f8c96efea9447 \
  09b68b692fa4b7ccdea39b1a16e3ff150794e12d \
  92658bccc253f31552415f9c9d667bbd28957a06
python3 -m experiments.expansion_20261029.c4_runtime.round2.prepare_dependencies \
  --root /tmp/c4-round2-deps
export C4_ROUND2_DEP_ROOT=/tmp/c4-round2-deps
export C4_ROUND2_REQUIRED=1
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s tests/expansion_runtime -t tests -v
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 -m experiments.expansion_20261029.c4_runtime.round2.report \
  --node node --output /tmp/c4-round2-composition.json
```

`report` intentionally returns **2** for the current actual C1→C3 mismatch:
`C1_DISPLAY_PROFILE_REQUIRED`. This is not an expected-pass disguise. Its JSON
keeps C4/core/C1 successes distinct from that failed downstream check. Use Node
20+ (local run: bundled Node 24.22.1). Old Node 18 ESM discovery is unsuitable.

`dependencies.load` verifies Git blob hashes and read-only permissions for every
owner package file before import. Existing shared relocalization/PCD sources
must match the pinned owner trees. It never resolves current remote HEAD. The
ordinary whole-repo CI does not fetch these new owner pins: its actual-core tests
are visibly skipped unless supplied by this explicit required-mode command.
Missing imports with required mode fail; no mock algorithm replaces either core.

The local environment's restricted event-loop wakeup issue requires execution
with local syscall permissions. Network remains loopback-only via the existing
C4 test audit hook copied to `/tmp/c4-network-guard/sitecustomize.py`:

```sh
PYTHONPATH=/tmp/c4-network-guard:. PATH=/tmp/c4-runtime-venv/bin:$PATH \
  timeout --signal=INT --kill-after=5s 180s \
  python3 -m unittest discover -s tests -v
```

This hook is local test isolation, not a product modification. No baseline tests
are filtered out. Native ROS is probed by module availability only, without DDS
initialization or graph/device discovery. Synthetic clock durations are not
performance measurements; processing timestamps are distinct fields even when
the deterministic fixture clock gives equal values.
