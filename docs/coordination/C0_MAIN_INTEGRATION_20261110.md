# C0 changes integrated on main — 2026-11-10

## Scope

Ported the changes from `d70e58c92e6039be13dea4d485920459ec8218e3`
and `5bdd038e44455ec8b0bee40745481087a11130a3` onto main
`24150c0e8c6bb5a98dc9f1326264e5a3733a2371`.
The source branch was two commits ahead and 45 behind main; its tree was
not used to replace main. The manual 2D navigation admission guards remain.

- Map pairs can use an explicit, revision-bound operator declaration of
  shared coordinates. This is an identity-transform assumption, not measured
  registration. Calibration, geometry, freshness and motion admission remain.
- Observation ownership copies run on the coordination event loop while native
  systemd reads remain in workers. Real foreign-thread contention still
  invalidates observation and preserves the first bounded failure diagnostic.
- The three previously failing pre-navigation draft browser cases now check
  the required map confirmation before applying the pair, and assert that
  submission consumes the confirmation. Their pending/stale-read assertions
  and checks for no initial-pose or goal request remain intact.

## Local validation

Windows host, Python 3.12.14, Node 24.22.1, Playwright 1.62.1:

- JavaScript unit tests: **765 passed**. The working copy needed LF line
  endings for source-extraction test helpers; this is not a product change.
- JavaScript syntax: **135 dashboard modules passed**.
- Ruff, configured mypy scope (four source files), and tracked-source secret
  scan: **passed**.
- Navigation preparation and pre-navigation draft browser tests: **96 passed,
  6 failed to start their Python fixture** because the tests invoke `python3`,
  which resolves to the Windows Store alias on this host. All three original
  pair-mutation failures passed. The six fixture cases are not counted as passes.
- Full `python -m unittest discover -s tests -v` was attempted, produced import
  errors and was interrupted without a completed suite result. A focused run
  of the three changed Python test modules confirmed the Linux-only `resource`
  import is unavailable on Windows. These are not Python regression passes;
  Linux GitHub CI must validate the integrated commit before deployment.

## Deployment handoff

No Jetson deployment, service restart, map change, observation start, initial
pose, navigation goal or movement was performed in this integration task.
A read-only health request to the configured dashboard returned
`robot_online=true` and `robot_target_connected=true`; it does not establish
the running source revision or stationary motion state.

After Linux CI passes, deploy only in an explicitly authorized device window:
record the current dashboard/bridge revisions and protected-data hashes,
prepare the exact tested commit as a separate immutable release, validate it
with the Jetson environment, and retain the existing release for rollback.
Service transition and field localization/driving validation are separate
steps. Do not treat either the operator map declaration or software tests as
evidence of successful physical alignment or driving.
