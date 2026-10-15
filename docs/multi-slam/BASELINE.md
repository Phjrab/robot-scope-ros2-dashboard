# Baseline and integration ownership

Audit: 2026-10-15 KST. Repository AGENTS and the user's MS/MR boundary apply.
`robot_scope_multi_slam_new_chat.md` was not present locally; the supplied pack
explicitly identifies ALL_IN_ONE and its individual chapters as equivalent.
Those documents define scope and acceptance, not a hardware execution approval.

- Checkout initially clean main `1b0ae5b172325f1952175a41f66ed850069b2fd5`.
  Its existing new-map hardware follow-up commit is preserved unchanged.
- Fresh origin/main: `eb9026a68a0529dd328148a9475289219be25c6a`.
- CI run [38554448122](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38554448122)
  failed both matrix entries in Ruff before tests. Original logs and local
  reproduction confirmed six issues. Fixes retain public module aliases, split
  three semicolon statements and narrowly explain the doctor's required import
  after direct-script path bootstrap. No CI rules or safety thresholds changed.
- Historical deployed checkout `416d25c` and installed Isaac ROS 3.2.6 are from
  VSLAM/hardware handoff, not a new device inspection. No deployment or SSH trial.

Reused: MappingCoordinator/MappingJobManager fixed process recipes and LiDAR save
publication, SavedMapCatalog identities/revisions, existing CameraHub/relay,
RobotScene3D, same-origin/competition/manual-mode dependencies, pipeline lock,
existing safety HUD and control transport. Legacy routes remain additive.

MS owns slam modules/router/scoped UI/tests/docs. MR owns mission/route code.
MS is the agreed single integrator for app/runtime/index/shared hooks and the
existing CI correction. MR initially drafts outside this checkout. Full suites
and Git operations run only in agreed windows; no concurrent full suites.

Read first for historical boundaries: GO2_ONBOARD_MIGRATION,
ADR_GO2_ONBOARD_OPERATION, experiments/isaac-vslam/HANDOFF and RESULTS,
hardware-validation 02/03/04. Their stationary VO/native-save evidence is not
new visualization, map reuse, motion, operational pose or performance acceptance.
