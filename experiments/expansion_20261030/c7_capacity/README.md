# C7 capacity diagnostic reproduction

This opt-in tool reads exact exported owner sources and synthetic inputs. It does
not connect to ROS, devices, robot HTTP/SSH/DDS, or start a production service.
Its results are **not driving authorization**. Nothing changes thresholds,
threads, TTL, geometry, controller settings, or other owners' source files.

## Setup and fixed sources

Use a separate ordinary clone on `review/20261030-x-c7-capacity-diagnostics`.
The seven exact SHAs and inspected main are in
`robot_dashboard/expansion_diagnostics/dependencies.py` and every result JSON.
Fetch those objects if absent; `prepare` and `run` never fetch or follow branches.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt scipy httpx
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m robot_dashboard.expansion_diagnostics prepare \
  --output /tmp/c7-exact-deps
# Exactly one small baseline first.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m robot_dashboard.expansion_diagnostics run \
  --deps /tmp/c7-exact-deps --output /tmp/c7-baseline.json
# Optional real browser fixture: use your existing Playwright package installation.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m robot_dashboard.expansion_diagnostics browser \
  --deps /tmp/c7-exact-deps --playwright /absolute/path/to/playwright/index.js \
  --output /tmp/c7-browser.json
# Finite comparison. Omit --browser-report when browser evidence is unavailable.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m robot_dashboard.expansion_diagnostics run \
  --deps /tmp/c7-exact-deps --profile bounded --browser-report /tmp/c7-browser.json \
  --config-snapshot /tmp/c7-baseline.json \
  --output /tmp/c7-results.json
# Regenerate Markdown without executing cores or touching source inputs.
.venv/bin/python -m robot_dashboard.expansion_diagnostics summarize /tmp/c7-results.json \
  --output /tmp/c7-results.md
```

`prepare` requires a new output directory and creates read-only whole Git exports.
`run` verifies all Python/JS/HTML/JSON/CSS files against the Git blobs before and
after execution, and verifies owner module import origins. Existing exports
with changed or writable source fail before execution. Only synthetic PCDs in a
scoped temporary directory are generated, then removed. No PCD, map, image trace,
rosbag or private sensor input is published. The browser command temporarily
serves the original C3 static fixture on an ephemeral **127.0.0.1** port and shuts
it down in `finally`; the original C3 runner blocks nonlocal/non-GET/API requests.

`run` writes JSON plus a same-stem Markdown file.
`--config-snapshot` accepts a previous result's configuration or a plain config
JSON and verifies equality with the actual owner defaults; it never changes
thresholds. A mismatch fails before the baseline executes.

A reported failed diagnostic
check returns exit 2; setup/runtime exceptions return nonzero, never a false PASS.
Expected capacity rejections are evidence and do not themselves make the
reproducer fail. Unknown or unsupported contracts are not repaired by a temporary
validator or fallback. Saved browser results require the pinned C3 SHA; they
remain a separate run and are not used to construct a cross-run improvement.

## Bounded workload and evidence meanings

- Reuse D2's sparse sample generator and its cone/ground generator, plus C1's
  PointCloud2 builder. Objects 0/1/4/12/16/32 × two geometries × metadata 0/4096
  bytes; one warm-up + three measured repetitions per case. Exactly two extra
  cone counts (14/15) locate the demonstrated 12..16 transition. Each port is
  fresh; this warms imports/code/OS caches, not tracker history.
- Large metadata is explicitly added to the generated frame's health after the
  numerical core. It is **metadata injection**, not synthetic geometry reduction
  or a sensor capture. JSON key/quotation overhead adds 34 bytes to the 4096-byte
  value. The full/compact byte partition accounts for every JSON byte.
- The real provenance compactor's encoder is observed before it raises. Its
  rejected candidate is only measured; it is never delivered as an accepted
  frame. Separate fresh-service probes demonstrate wire-versus-ingest behavior.
- The asynchronous C4 worker has a finite explicit gate before actual D2 work.
  The 60-input burst ensures one executing + one pending; it is not an observed
  production overload rate. Gate wait and real core execution are separate.
- The current synchronous C4 Runtime executes actual D2 → D3 → canonical ports
  → C1 ASGI HTTP → actual Node C3 parser/adapter/consumer. C4's asynchronous
  worker and synchronous Runtime are **separate existing paths**, not claimed as
  one fully wired ROS chain. No pose/joints/path or collision geometry is invented.
- D1's original 400/20,000/200,000-point-per-source generator supplies two map
  inputs. Small-map D1 solve is real. Larger cases measure C1 export/storage with
  explicitly supplied generator transforms and no claimed large-map solver
  quality. Counted stream reads forward every byte unchanged; these are logical
  reads, not measured physical disk traffic. Full 256 MiB / 20M-point limits are
  source-inspected and **not stress-tested**.
- C3's original 1,200-packet browser runner and existing cache are reused. The
  cache probe uses explicit memory Response transport; it is not HTTP evidence.
  Browser performance and canonical core/Node results remain separately labeled.

Duration events use Python `perf_counter_ns`; queue health uses one real host
`monotonic_ns` clock; JS uses Node/browser `performance.now` independently.
Synthetic source/host clocks validate freshness and are never timing benchmarks.
Without measured mapping, sensor-to-render latency is **UNKNOWN**. The ASGI
HTTP timing includes fixture app/client setup and authorization checks; it is
not network response latency. No controller execution time is inferred from
message intervals. p50/p95 use nearest rank, with sample count and warm-up flags.
The three-sample p95 equals max and does not qualify an operating rate.

## Regression

On macOS, use a real, nonsymlink temporary directory with the current user's
UID/GID. `/var` is a symlink and `/private/tmp` can inherit a different group;
the existing path/ownership guards correctly reject those fixtures. Create an
owned test parent without modifying any production path or guard:

```sh
python3 - <<'PY'
import os
from pathlib import Path
p = Path('/private/tmp/c7-tests-owned')
p.mkdir(mode=0o700, exist_ok=True)
os.chown(p, -1, os.getgid())
PY
```

```sh
PYTHONDONTWRITEBYTECODE=1 C7_DEPENDENCY_ROOT=/tmp/c7-exact-deps \
  .venv/bin/python -m unittest discover -s tests/expansion_c7 -v
TMPDIR=/private/tmp/c7-tests-owned PATH="$PWD/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
  C7_DEPENDENCY_ROOT=/tmp/c7-exact-deps python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
node --test /tmp/c7-exact-deps/C3/tests/expansion_c3/test_consumer.mjs \
  /tmp/c7-exact-deps/C3/tests/expansion_c3/test_canonical.mjs \
  /tmp/c7-exact-deps/C3/tests/expansion_c3/test_assets.mjs
.venv/bin/python -m ruff check robot_dashboard scripts
.venv/bin/python -m mypy --config-file mypy.ini
.venv/bin/python scripts/check_repository_secrets.py
```

Ordinary CI does not fetch owner branches. Without `C7_DEPENDENCY_ROOT`, the one
external integration wrapper explicitly skips; local diagnostic units still run.
This skip is never counted as real-owner coverage. Browser requires Playwright
and Chromium; its absence is NOT_RUN, not a synthetic performance substitute.
