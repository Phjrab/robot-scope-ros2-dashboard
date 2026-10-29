# C1 frozen candidate validation — 2026-10-29 KST

All C1 input is generated synthetic data. No robot endpoint, ROS graph, model,
camera, sensor, deployment or operational bridge was used. Temporary binary PCDs
and bundles exist only under /tmp and are not tracked. Root product files are
unchanged. This is independent service implementation, not END_TO_END_IMPLEMENTED.

| Check | Result | Evidence class |
| --- | --- | --- |
| `python -m unittest discover -s tests/expansion_c1 -v` | PASS, 20 tests, no skips (also included in final full discovery) | UNIT / SYNTHETIC |
| `python -m unittest discover -s tests -v` | PASS, 3,103 run, 5 skip, 101.563s | repository offline UNIT / SYNTHETIC regression |
| bundled Node `--test tests/*.mjs` | PASS, 77/77, no skips | existing JavaScript fixture regression |
| bundled Node `scripts/check_frontend_syntax.mjs` | PASS, 112 modules | static |
| `python -m experiments.expansion_20261029.c1_service_host.smoke` | PASS: localhost bearer auth, enqueue/status/review/export/GET reload, scene and shutdown | SYNTHETIC HTTP smoke |
| `python -m ruff check robot_dashboard scripts` | PASS | static |
| `python -m ruff check robot_dashboard/expansion_contracts robot_dashboard/expansion_services tests/expansion_c1 experiments/expansion_20261029/c1_service_host` | PASS | static |
| `python -m compileall -q robot_dashboard/expansion_contracts robot_dashboard/expansion_services tests/expansion_c1` | PASS | static |
| `python -m pip check`, `git diff --check`, tracked-source secret scan | PASS | packaging / source hygiene |
| D1 / D2 / D3 actual exact-SHA compatibility | NOT_RUN: designated remote refs absent when checked | counterpart |
| REPLAY_REAL / NATIVE_NAV2_SIM / UI_FIXTURE | NOT_RUN for this C1 contribution | not claimed |
| DEVICE_NOT_RUN | no device access; no activation/deployment/driving | device |

The final full-suite five skips are existing tests:

- `competition_native.test_inference_binding.InferenceBindingTests`: old pinned dependency `9e9ebcc0cbc613d5b0a7f50a27a7b256c3f829bd` absent.
- `competition_native.test_round3_cross_contract.C1RuntimeCrossTests` and `C4CrossTests`: old pinned dependency `380800ca9e211495769fe60ee8221e3f4fb40f16` absent.
- `test_inspect_se3_pair.PairInspectionTests.test_overlay_artifacts_label_synthetic_and_not_operational`: optional SVG plotting dependency absent.
- `test_isaac_vslam_inspect_bag.RosbagsBackendTests.test_real_humble_cdr_serialization_is_decoded_offline`: optional rosbags backend absent.

These are preserved skips, not new expansion counterpart evidence. Old role
branches/dependencies were neither fetched nor resumed.

Focused coverage includes strict IDs/no paths/unknown fields, oversized JSON,
nonfinite values, bad SE3, request idempotency/conflict, single heavy worker and
bounded admission/history, private read-only snapshots and aggregate bytes,
progress, cancel/late result rejection, changed or mutated pins, proposal revision
and manual review labels, complete-source normals/scalar preservation, original
VIEWPOINT sidecar, heterogeneous schema rejection, checksum tamper, duplicate
immutable export, staging failure and rename/durability rollback, cancellation
before publication, 2→3 provenance and cycle/duplicate ancestor rejection, tilted
annotation prisms/missing-Z review state, UNKNOWN/no inferred free occupancy,
1,200 latest-only scene samples, map/stream/source epoch fences, clock UNKNOWN,
missing calibration, collision reference/validity fences, authenticated/origin
router wrapper and import with thread/process/network starts trapped.

Earlier diagnostic attempts (not final results):

- Restricted-sandbox Python discovery was interrupted, then bounded at 120s:
  TIMEOUT (exit 124), stopping after an existing coordinator test. The same
  sandbox also stalled TestClient portal startup; faulthandler showed event-loop
  wakeup waiting. Explicit localhost-only tests outside that sandbox completed.
- First complete unsandboxed discovery: FAIL, 2,957 run / 1 error / 15 skip, due
  to absent cv2. Installed the repository's `requirements-competition-offline.txt`;
  final stable environment passes above.
- System Node 18.19.1: FAIL, 70/77 and 7 ESM/CommonJS loading failures in existing
  tests. Bundled Node 24.22.1 passes all 77 without product changes.
- An early router test asserted `.path` on FastAPI's new included-router wrapper:
  fixed the test to inspect OpenAPI paths; request flow itself passed.
- One development focused run overlapped the dependency replacement: transient
  mixed numpy imports caused 1 error and a subprocess failure. That test run was
  invalid; installation was completed and the stable 20-test and full-suite
  runs above passed. Dependencies were not changed during final validation.

Reproduction environment: Linux x86_64 7.0.0-38-generic, Python 3.12.3 in
`/tmp/robot-scope-c1-venv`, FastAPI 0.162.0, Starlette 1.10.0, httpx 0.28.1,
numpy 1.26.4, scipy 1.11.4, PyYAML 6.0.1, opencv-python-headless 4.10.0.84,
ruff 0.6.9, bundled Node 24.22.1. Starlette emits a non-failing httpx deprecation
warning; no production dependency files were changed.
