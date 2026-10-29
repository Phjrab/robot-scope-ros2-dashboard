# Contract bootstrap

BASE_SHA: f469155c2b0c505f3e472e878f75029d7b8d39df

`python3 -m unittest tests.expansion_c1.test_contracts -v`: PASS, 2 UNIT/SYNTHETIC tests.
AGENTS full discovery was attempted in /tmp venv before this commit; the existing
competition_native.test_coordinator test_cancel_ack_delay... prints ok and hangs
in teardown inside the restricted sandbox. Interrupted after several minutes;
bounded diagnostics confirmed an event-loop wakeup restriction. Unsandboxed
localhost-only synthetic runs proceed; final results are recorded in HANDOFF. No C1 service was imported by that test. JS baseline on Node
18.19.1: 70/77 PASS, 7 FAIL (existing ESM/CommonJS load failures). Final runtime
and baseline comparison follow in HANDOFF. DEVICE_NOT_RUN. No robot connection.

This is the first focused wire contract publication, not a service completion or
counterpart integration claim. Contract commit is this file's containing commit.
