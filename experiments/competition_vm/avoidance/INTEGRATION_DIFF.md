# Integration proposal (not applied)

Baseline b1077e39e4ee456621c47eada49b1f0c85453661; no production files changed.

- `navigation_collision_profile.py` lines183–223 currently enforce NavFn, overwrite RPP, reject polygon footprint and patch fixed layers. Keep this qualified path unchanged. Add a *new* profile ID `competition-vm-v1` in the integration owner's branch, preserve old default. `profiles.py` builds candidate expected snapshots; `assert_effective` rejects silent RPP overwrite or footprint/layer change. It is not a production authorization.
- `robot_dashboard/ros/policy_readback.py`: extend only new-profile expected readback with MPPI model/time_steps/model_dt/batch_size/vx/vy/critics, footprint and dynamic layer sources. Current allowlists are not bypassed. Compare installed plugin versions/accepted parameters and final generated snapshot before enabling.
- `NavigationJobManager` snapshot generation: select versioned profile once; hash after all canonical patching, validate after generation (not before it gets overwritten). No runtime_policy_enforced constant or blanket allowlist disable.
- `NavigationCoordinator` currently uses `/robot_scope/nav/cmd_vel_raw`; bridge remains single-owner. Proposal: controller → smoother → mission constraints → Collision Monitor → existing freshness/watchdog bridge. Do not use this experiment's `/competition_vm/cmd_vel_untrusted` as a hardware input. Release needs new command sequence.
- Existing `robot_scope_collision_replan.xml` supplies NavFn/RPP periodic replanning without clear/spin/backup. Candidate BT retains that structure, with 2Hz DESIGN_INITIAL. Signal waits must pause/cancel acknowledged approach action before hold, then start a new navigation leg; do not keep SimpleProgressChecker ticking during red hold.
- No TF renaming from FAST-LIO IMU body to base_link. Actual extrinsics, footprint, braking and native live readbacks remain required.

# Native candidate boundary

`config/*_vm_candidate.yaml`, `config/replan_vm.xml` and `ros2_adapter/native_candidate.launch.py` are prepared only. Launch is guarded by localhost/domain183; autostart false, no device launch or control bridge. Full native map/TF/scan/kinematic plant wiring and lifecycle activation **NOT_RUN**. Real RPP-vs-MPPI comparative performance cannot be inferred from the fallback simulator. First native task: provision supported Ubuntu22.04/Humble VM, record apt package versions, wire a sandbox plant, dump accepted params, run same 15 cases and 3 seeds for both plugins.

Source references reviewed: https://api.nav2.org/nav2-humble/html/md_nav2_mppi_controller_README.html and repository canonical Humble YAML. docs.ros.org installation page returned access denied; no access bypass attempted. No installing a whole distro inside this VM merely to claim native coverage.
