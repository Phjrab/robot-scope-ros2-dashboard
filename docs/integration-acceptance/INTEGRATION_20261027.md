# I1 and detection-only teammate integration — 2026-10-27

This intake starts from refreshed GitHub main `a79dc18b50a0cddee2056fe4748781cdca03aec9`.
The original local main `104692fa0070ef085eee918913ea05fdb2d88c05` was an ancestor,
not a newer replacement. Two unrelated user CSS edits remain uncommitted and
byte-for-byte preserved. Their contents are excluded from the release archive.

## Adopted source

- I1 `ca6e999639ad0f7d267f62b44a366de4975be3f7`: six commits, 35 files,
  fast-forwarded onto main. This includes the deployed `c98afbc9db6a` source,
  map-picked XY/yaw, bounded seeded registration, stored course regions, and the
  explicit seeded-local residual-cap option. No I1 code was downgraded.
- C4 source `3f9f2ba33021f18418bb9bf2ab379f972d16f029`: reviewed exactly its nine
  changed paths, rather than merging the C4 branch. Adopted `config.py`,
  `consensus.py`, `inference.py`, `model.py`, `pipeline.py`, `teammate_compare.py`,
  `check_teammate_c1.py`, `test_teammate.py`, and `teammate-model-example.json`.
  The source patch depended on an emitter experiment absent from main; that
  experiment and the mission-mode consensus path were deliberately excluded.
- The explicit teammate policy now rejects any mode other than `detection-only`,
  both at construction and processing. Model/C4 agreement is diagnostic only;
  canonical/stable mission state remains UNKNOWN. Crosswalk is excluded.
  Consensus settings participate in the existing inference settings hash.
- Model SHA-256:
  `3bae0ae05522fe92cbda850b4d604e9babaa34ebbd130fd69cd9c7e61a9e44ec`.
  No weights, RGB, maps, credentials, or device configuration are committed.

C1 worker/ingress, C2 trusted pin, FIRST_RECEIPT, epoch/source stamps, TTL and
STOP ownership fences are unchanged. C3 `8aef2fb` and D0 `83d3038` experimental
changes are not adopted. L1 `d8c3be6` is diagnostic evidence, not a branch merge.

## Reproduced fixes

The I1 browser's sampled FAST-LIO cloud and pose need not contain the same
source stamp. Seed readiness now uses the existing fixed-frame registered-cloud
display contract with independently fresh IMU pose. Backend capture still
requires exact source-stamp pairing. Explicit candidate application selects the
existing continuous observation/recovery path; merely editing/calculating a
candidate does not replace an anchor. Stale input hides geometry, both streams
must advance before recovery, and new map/source epochs invalidate the anchor.
Fresh input without a recoverable anchor reports `ANCHOR_RECONNECT_REQUIRED`
instead of retaining the old STALE label.

A failed mapping start previously finished owned cleanup in IDLE but retained
`unsaved=true`, keeping ownership busy. It now clears that empty draft only after
runtime stop and exact camera-owner release both succeed. Cleanup errors retain
their blocking state; accepted mapping data still requires explicit discard.
The regression failed before the change and passes afterward. The old USB
failure was not reproduced on the current device: current scope and owner probe
already identify the live USB device, and a stationary Stereo session succeeds.

## Local software evidence

- Required Python discovery: 2,995 tests, no failures/errors, 3 skips (optional
  rosbags and two Linux-only `/proc` tests), 128.998 seconds.
- JavaScript unit: 681 passed; frontend syntax: 110 modules passed.
- C4 focused: 97 passed. Real hash-pinned model load and current-main C1/C2
  worker/ingress cross-check: 173 passed, no skips. Input is a training
  visualization, not independent real-signal accuracy evidence.
- Full browser E2E: 207 passed (7.2 minutes). Observation subset: 30 passed, including mismatched sampled stamps,
  stale hiding/recovery, source replacement, saved course and residual policy.
- Mission real-Python-API fixture browser E2E: 10 passed. The first local run
  could not start because macOS default temporary paths resolve through `/var`
  symlinks; rerun used the canonical `/private/tmp` test directory without
  relaxing the application path check.
- Ruff, configured mypy (four sources), and source credential scan passed.

CI must be evaluated on this resulting main commit, not inferred from earlier
branches. I1 `40461729393` and baseline main `40447991087` succeeded. C4
`40449742322` and L1 `40494880316` failed browser E2E on both OS jobs. No workflow
run was returned for exact C3 HEAD `8aef2fb`. These historical outcomes are not
relabelled by integration success.

## Device baseline and qualification

Before deployment the actual PID was 1032, cwd
`/home/unitree/robot-scope-releases/robot-scope-c98afbc9db6a`; all 2,130 release
source hashes matched its manifest. Current maps number 31, not the historical
28. Existing releases/backups, map revisions, anchor/course presets and private
configuration are preservation gates. Control is disabled with no lease or
pending action/output. The normal dashboard service management path is used.

Current stationary Stereo observation collected 80 stream snapshots over
65.4496 seconds, sequence 95→254, all TRACKING, maximum heartbeat age 0.138s.
Real IR, pose, features and trajectory were visible. Normal stop returned IDLE,
`unsaved=false`, and released the camera. This is current-device evidence on the
old release, not yet a claim about this integration's deployment.

Release activation, exact resulting main CI, post-deployment PID/cwd/hash
readback, preservation/rollback receipts and actual-device rechecks are recorded
separately by the integration operator. No movement, ARM, navigation goal,
velocity/posture command, initialpose, operational TF change or automatic
departure is authorized by these observations. Signal temporal accuracy, body
extrinsics and physical stop/go qualification remain NOT_RUN/NOT_QUALIFIED.
