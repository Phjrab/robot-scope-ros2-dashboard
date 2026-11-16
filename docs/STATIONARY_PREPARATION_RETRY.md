# Stationary preparation: startup readiness and retry state

The November 16 field helper stopped a valid startup when the pipeline first
reported `running` while `can_set_initial_pose` was still false. Its next attempt
retained the previous proposal geometry, producing `MAP_PAIR_CHANGED` because
the pair was invalid, even though the map files had not changed.

`scripts/prepare_go2_stationary.py` replaces that one-off helper. It performs a
single preparation attempt through the existing dashboard APIs, ending at
`can_send_goal`. It never submits a goal, arms manual control, clears STOP,
changes parameters, edits maps, or bypasses proposal/footprint/match admission.

## Changed behavior

- Wait up to the existing helper's 45-second startup budget for
  `can_set_initial_pose`, not merely `pipeline=running`. Retain the job identity;
  terminal startup, changed job or changed navigation map fails closed.
- Before starting observation, require an inactive job/goal, zero command, no
  lease, and confirmed inactive observation with released bridge guard. A stopped
  startup may retain `failed` history with no job; that alone is not an active job.
- Check the freshly supplied draft's pair generation, map IDs/revisions and
  calibration hash. Renew old geometry through the normal pair selection API,
  preserving the existing operator declaration or conversion-lineage relationship.
  Require a new generation, identical map/calibration identities, no seed geometry,
  and a valid pair before proceeding. No map files are rewritten.
- Recover only recognized lifecycle states. Source/context or map/calibration
  changes still require review. No looping retries and no bypass of `pair.valid`.
- Use a fresh operator pose, with no built-in field coordinates. Every proposal,
  confirmation, initial pose and match remains server-validated with the existing
  bounds, freshness, stationary evidence and receipt requirements.
- Save HTTP conflict details and stage snapshots. Cleanup attempts navigation and
  observation stop independently even if a request or log export fails, then
  collects readbacks. An unconfirmed cleanup is not proof of physical stopping.

## Offline and future field use

The input is JSON with `pair` copied from the current
`GET /api/v1/navigation/operational-3d` response and `pose` containing the operator's
current map `x`, `y`, `yaw`. A pair copied from yesterday must not be reused.

```text
python scripts/prepare_go2_stationary.py --draft CURRENT_DRAFT.json
```

The default only validates the input format, without network or ROS. It does not
certify a saved pose's current validity or authorize movement. Live use additionally
requires Linux on the robot, `--execute`, `--stationary-supervision`,
`--conditional-prior-acknowledged`, and `--output NEW_DIRECTORY`. These flags are
fresh operator confirmations; this change does not itself authorize a live run.
The local dashboard URL is fixed to loopback. The operator should not change the
map or start a different operation while the preparation attempt is executing.

No robot connection, deployment or service transition was performed while making
this change. The earlier helper under the robot's diagnostics directory is still
an old artifact until explicitly replaced. Do not execute it. The desktop's
`nav2-live-analysis-20261115/prepare_latest_pose_20261116.py` now delegates to this
maintained entry point; its previous source is retained as `.retired.txt` evidence.
The separate frozen-cloud capture helper remains a diagnostic tool, not a dependency
of this preparation sequence. This sequence records API evidence, not raw clouds.

## Verification and limits

Offline tests reproduce old geometry plus a delayed-ready Nav2 startup through
initial pose/match/goal readiness, and verify that no goal or parameter request is
sent. Negative cases cover occupied control, active jobs/goals, held observation
guard, changed map/calibration/generation, source errors, proposal rejection,
startup timeout/termination, changed job/map, and cleanup failures. A real synthetic
map-catalogue test renews used geometry and verifies map bytes and policy unchanged.

The 31–45 cm draft/candidate discrepancy is a separate unresolved sensor/map
registration issue. This helper does not make every position pass. It also does
not establish final goal arrival or validate the deployed approach-speed policy.
Physical validation remains pending until the robot is powered on and supervised.
