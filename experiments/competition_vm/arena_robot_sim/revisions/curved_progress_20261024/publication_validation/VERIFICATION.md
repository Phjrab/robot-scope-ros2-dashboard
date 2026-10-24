# Publication-copy verification — 2026-10-24 UTC

- PASS: unchanged progress 22 tests and watchdog 15 tests, zero skips.
- PASS: actual frozen planner timeout, 0.111100 s measured; 11 recorded zero
  gate samples; worker cleaned. This is a VM measurement, not a time bound.
- PASS: rerooted original geometry reviewer produces all six reports exactly
  equal to frozen evidence. Both rerooted watchdog race probes retain
  TIMEOUT/CANCELLED, no result and zero output. This is a reproducibility replay,
  not another independent reviewer or new physical validation.
- PASS: all 44 copied original artifacts, five complete lossless fixtures and
  seven unchanged existing dependencies match their expected source bytes.
  Both original frozen manifests verify (26 + 20 entries).
- FAIL: full Python suite ran 2691 tests in 90.659 s: one known manifest
  integration failure, 25 socket PermissionErrors, one skip. Every error's
  traceback was inspected for the local socket restriction. No test was
  removed or converted to a skip. See the included failure excerpt.
- PASS: JavaScript 660 tests, zero failures/skips; tracked-source secret scan;
  extended new-file scan including uncompressed gzip contents; diff check.
  Pattern-based secret scanning is not a guarantee of absence of all secrets.
- Preexisting 2161 tracked files were compared by hash. Only the parent
  publisher's concurrent D0 REVIEW.md edit differs; this preparation did not
  edit any preexisting file or git ref. Original source and frozen output
  bytes were rechecked after tests.

Full Python/JavaScript output and redundant replay logs remain local to keep
this subset small. SUMMARY.json records their exact sizes and hashes and the
actual commands, status and environment. Focused test logs and fresh timing/race
summaries are included separately from the immutable original records.

NOT RUN: scenario regeneration/repeat simulation, profile/memoization rerun,
new articulated-mesh or animation validation, native ROS/hardware/physical stop,
publication or remote CI. No realtime/integrated-navigation claim follows
from a passing zero-output gate or offline saved-trace test. The preexisting
manifest integration blocker remains unresolved. No UI, main or hardware
configuration was changed.
