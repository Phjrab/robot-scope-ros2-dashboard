# D3 ROUND2 actual results — 2026-10-29

## Source, tests and publication

- ROUND2 parent: `09b68b692fa4b7ccdea39b1a16e3ff150794e12d`.
- Initial canonical/coverage/native-CI source: `75379f4e47863a45a7255ed807ad3e67f22bfd1b`.
- **Actual final native source/test SHA: `fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d`.**
- Equivalent local tested SHA: `aaeda01db56abad0fa0257ca669935ca88eef16f`;
  complete tree `1cd4cf63e18263e83a91cda81318b38d981153bf` equals published source.
- This results-only delivery adds documentation and non-sensitive summaries;
  final submission SHA is the commit containing this document / branch HEAD.
  It does not alter source, tests, workflow, native parameters or evidence.
  Exact final SHA and terminal standard-CI state are reported in delivery and
  independently visible in that commit's GitHub Checks.

Only D3-owned paths and the expressly authorized new
`.github/workflows/expansion-native-offline.yml` changed. Existing CI/deploy,
product common files, main, controllers, other branches and robot were untouched.
Publication used original remote parent trees and ordinary fast-forward refs;
changed blobs and complete remote/local trees were compared, no force-push.

## Actual levels of execution

| Level | Actual result and boundary |
|---|---|
| D3 focused UNIT | **29 PASS**, including namespace allow/production-deny regression |
| D2 actual core | **PASS**, current 7313f0a and original c0d266e both executed |
| C1 actual canonical validator/clock binding | **PASS**, cb8ccc6 v0.2; no TTL restart; >2^53 lossless strings |
| C4 actual consumer + CommandGate | **PASS**, b9d700d; ACTIVE UNKNOWN→HOLD; command sink is MEMORY_ONLY |
| C4 production ROS wrapper | **NOT_RUN**; not replaced by a mock success claim |
| C1 HTTP publication/service | **NOT_RUN** in D3; real core validation is not HTTP evidence |
| Local whole discover, known blocked cases excluded | **2969 run, PASS, 11 skips**; 36 previously established environment-blocked cases explicitly excluded, not retried |
| Local exclusions | 25 socket permission failures + 11 missing-cv2 cases from ROUND1; not counted as PASS |
| Local JS/syntax/static/secret scan | **699 JS PASS**, 112 syntax modules PASS, whole Ruff PASS, staged-source secret scan PASS |
| Hosted exact-source compatibility | **PASS** for new and old D2 with real latest C1/C4 |
| NATIVE_NAV2_SIM | **5/5 PASS**, actual controller/lifecycle/action/plant/feedback/evidence validator |
| Physical robot / measured mount/coverage qualification | **DEVICE_NOT_RUN / INPUT_REQUIRED** |

Local safe-discovery's first invocation used stdin, causing one unrelated
multiprocessing child to fail opening `<stdin>`. Moving the same selection into
a normal guarded Python file fixed the test runner; final 2969-test run passed.
No product/test criterion was relaxed. Standard hosted CI runs ALL tests, without
these local environment exclusions. Source `fa8e26e` standard CI is
[run 40840774821](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840774821);
at the 08:21 UTC evidence snapshot, both Python/JS matrices and offline integration
had passed and browser tests were still running. This timestamped snapshot is not
an assertion of final CI completion; final delivery verifies the final commit.

## Actual native run

**[Native run 40840774827 — SUCCESS](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840774827)**,
source `fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d`.
[Full native evidence artifact](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840774827/artifacts/12882393645)
contains actual raw commands, actuator/pose trace, scan/odom feedback, costmap,
plan, lifecycle/action, ownership/cleanup checks, params, image lock and
namespace-adaptation hashes. [Machine-readable summary](round2-native-summary.json)
retains both attempts and the first blocker; raw build/install/log data is not Git.

| Scenario | Native action | Outcome | Controller commands | Contact / boundary violations | Raw conservative minimum m |
|---|---|---|---:|---:|---:|
| Empty lane | SUCCEEDED (4) | GOAL_REACHED | 347 | 0 / 0 | 0.000 |
| Spacious single obstacle | SUCCEEDED (4) | GOAL_REACHED | 561 | 0 / 0 | 0.277162 |
| Fully blocked | ABORTED (6) | SAFE_WAIT | 0 (43 behavior commands) | 0 / 0 | 0.000 |
| Appearing obstacle | SUCCEEDED (4) | GOAL_REACHED | 616 | 0 / 0 | 0.264946 |
| Sensor dropout | CANCELED (5), SENSOR_STALE | SAFE_WAIT | 45 | 0 / 0 | 0.000 |

The raw zero conservative clearances are retained, not rewritten to positive
values or interpreted as confirmed contact. Independent swept contact count is
zero. Blocked/stale are expected safe failure/wait, NOT goal success. Maximum
plant wall gap was 0.117994 s; each run recorded one >75 ms deadline miss. These
are hosted-VM timing observations, not physical stopping-distance or Jetson claims.

The appearing-obstacle evidence independently reports: actual appearance 3.05 s;
first hit scan 3.10 s (27 beams); costmap 3.60 s (16 lethal cells); first changed
detour plan 3.70 s, 191 points versus 197 initial path points. Merely publishing
an input was not accepted as ingestion. The native controller's real Twist drives
the plant; a truth/reference path is never used as a motion command.

### Baseline and protection identity

Stock **NavFn + direct RPP**, not RotationShim; no current heading patch included.
Humble Nav2 package versions were actually checked at **1.1.20**, rclpy **3.3.22**.
Actual RPP shared-library SHA256:
`d63cca14c5cd1f5d85b61d2d37e40f70c1cba0133fe2dcd574595386b969f497`.
Resolved config SHA256:
`03e662b688603f63dfdc3d90a0008ce4342b5939dcf1b948d6aad9552c5c940a`.

- Immutable image: `sha256:39debc1b93d26f811c0e20d283f4a15ffb4587885c3c6940dc3f42c7cbb84930`.
- Base: `ros@sha256:d9bcf2e6f72df127fdee07048c2e87b1b4b9a59a74af0592f4489fc2844aa855`.
- `/robot_scope_review_x`, domain 194, ROS_LOCALHOST_ONLY=1, Docker network none,
  no host network/device mounts/robot secrets; existing fake actuator sink only.
- Original footprint .716×.324 m, v<=.18 m/s, |w|<=.6 rad/s, tolerances/settings
  unchanged. Spacious obstacle is the existing conservative .6 m square proxy,
  not a measured cone mesh. Original narrow-route failures remain unchanged.
- Existing native RPP collision detection/stale command boundary ACTIVE.
  **New D3 URDF coverage constraint ADVISORY_ONLY** in this native baseline.
  It was not silently enabled or downgraded; no new 3D protection is claimed.
- This native test reuses the existing scan/costmap harness. It is NOT a claim of
  end-to-end C4 production ROS-wrapper→D2→Nav2 integration. Those layers are
  explicitly separated from the actual Python core composition tests above.

### First actual blocker retained and fixed

[Initial run 40839918176](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40839918176)
built/verified Humble 1.1.20 and started the network-none container, then failed
before ROS launch: the old config guard rejected substring `/robot_scope` inside
approved `/robot_scope_review_x`. Workflow/attempt FAIL; ROS/goal execution there
was NOT_RUN. The fix normalizes ONLY the exact approved prefix for that textual
guard in the ephemeral export; a regression proves `/robot_scope/production_map`
is still rejected. No safety/controller/geometry/goal criterion changed.
The successful rerun includes the full minimum and gated two-case extension.

## Canonical example and dependencies

[Actual canonical core example](round2-canonical-example.json): v0.2 UNKNOWN,
explicit original clock interval and ClockBinding provenance, no renewed TTL.
Canonical JSON hash (without trailing newline):
`5675e001b282492584e6c18185205e5064b1a5c05c9a56491af9578dfb341246`.
Exact committed file hash (including newline):
`8286b8af15127307a877099379db251f30be9e452edb7664ae7d400ff53f2f3d`.
Both hosted new/old-D2 combinations reproduced the same canonical hash.

C1 `cb8ccc68be8d96a44b0d38adcff8186893ba2b08`; C4
`b9d700d754f0d3d43b9afdcffcb86e9deb7b1020`; D2 latest
`7313f0a31c00ae87ae216b84ca41a23804e91917` and original
`c0d266e290a2d29c173d3b83520f8c96efea9447`. Exact exports only; no foreign code
merged or published. See [ROUND2.md](ROUND2.md) for reproduction and boundary APIs.

**Next one item:** qualify real horizon/swept-volume sensor coverage with measured
mount/calibration inputs before enabling the additional D3 ACTIVE constraint.
Until then it remains explicitly ADVISORY_ONLY; ACTIVE insufficient coverage
must HOLD. Product integration, robot access and deployment still require separate
user authorization. No further parameter sweeps are needed for this candidate.
