# VM avoidance handoff

## Scope and result boundary

All changes are under `experiments/competition_vm/avoidance`, local only. No robot/Mac connection, device ROS graph, service restart, deployed code, bridge output, git stage/commit/push. Baseline is `b1077e39e4ee456621c47eada49b1f0c85453661`, newer than the prompt's c00cc baseline. Preserve production's existing qualified NavFn/RPP profile.

Implemented: closed-loop first-hit virtual laser → dynamic occupancy → inflated A* replanning → differential motion → polygon swept checks → same goal. This is `vm_astar_rotate_follow_v1`, not a mock labeled Nav2. Static geometry and known-free prior are independent of hidden dynamic truth. Ground truth is used only by sensor raycasting and contact evaluator. Dynamic expiry becomes unknown, never free. Observed clear rays alone clear dynamic occupancy. Terrain always hands off.

## Reproduce

Python3.12 with pinned `requirements.txt`; existing environment already provided these packages. From repository root:

    python -m unittest discover -s experiments/competition_vm/avoidance/tests -v
    python experiments/competition_vm/avoidance/profiles.py
    python experiments/competition_vm/avoidance/arena_contract.py
    python experiments/competition_vm/avoidance/simulate.py --seeds 3

Simulator now includes16 scenarios ×3seeds. The first final sweep ran15 cases before map_misalignment was added; its independent3 runs are in results/map_misalignment.json. Combined acceptance is described in VALIDATION_RESULTS.json. Reproduction single-command reruns all16.

## Coverage, without inflated claims

- Synthetic closed loop: empty; unknown central obstacle; blocked branch; complete barrier then observed removal; dropout; narrow feasible and physically infeasible passage; real .55m static/observed geometry offset; terrain reject; injected RED hold plus obstacle removal; staleTF; revision/cancel/restart; immutable leg corridor. Obstacle_variant is a redundant seed fixture, not additional algorithm coverage.
- Unit evidence: occupied occlusion/expiry; clear-ray removal; invalid/stale/duplicate receipts; bounded identity; stop arbitration; same-goal identity; polygon/swept collisions; support-plane separation, low obstacles, self/range/NaN and ring counts; metre rigid transform and double-registration rejection; profile readback mismatch and silent MPPI→RPP overwrite rejection.
- Read-only arena contract: actual revision/scenario schemas inspected and hashed. Its frame arena_design has null map transform, course graph DRAFT, different assumed footprint. Full arena asset navigation remains NOT_RUN, not silently substituted by the 6×3.6m fixture.
- Two-signal perception+X-branch integration NOT_RUN here. The leg_corridor test does not demonstrate perception association. RED state is explicit mission-input fixture, not vision prediction.
- XT16 native raw/registered replay, reflectance false-positive/negative comparison, Patchwork++, RGB-D calibration fusion, locomotion/slip/braking and true leg envelope: NOT_RUN / INPUT_REQUIRED.

## Native blocker and candidate eligibility

Debian13 x86_64 VM has no ROS2/Humble/Nav2, container runtime or supported native plugin environment. Native planner/controller/lifecycle and RPP-vs-MPPI comparison are BLOCKED. Plugin installed versions/accepted parameter dump do not exist. Config structure tests are NOT native parameter validation. No controller recommendation can be made from substitute A* performance; retain existing qualified RPP until true comparison.

Candidate YAMLs, BT and guarded launch are preparatory, `native_launch_eligible=false`. Launch needs ROS_LOCALHOST_ONLY=1, ROS_DOMAIN_ID=183, autostart false; no robot drivers or hardware bridge. Separate isolated map/TF/odom/scan/clock/plant integration and validation is still needed. Use only supported Ubuntu22.04/Humble VM and record actual plugin versions and final parameter readback before lifecycle activation. Production-only runtime section removed. Full candidate dictionaries are compared after canonical generation; never disable allowlists.

## Numbers and sources

SOURCE_CONFIRMED: repository production wiring/validators and Humble MPPI docs https://api.nav2.org/nav2-humble/html/md_nav2_mppi_controller_README.html . RULEBOOK values live in arena revision only, none used to claim fixture scale is a measured course.

DESIGN_INITIAL: fixture6×3.6m, resolution0.1m, sensor720beams/8m, body0.50×0.36m, v0.25m/s, w0.8rad/s, dt0.1s, replan0.5s, freshness0.3s, dynamic expiry2s, collision sweep0.5s. Narrow gap0.95m versus0.25m. Native candidate resolution0.05m,horizon1.5s,batch256. All are simulation assumptions, not measured Go2 dimensions or safe field limits.

MEASURED_VM: generated execution wall times, A* planning latency, peak RSS; simulated arrival/path/contact counts are synthetic outputs. `scheduled_simulated_tick_s` is not ROS publisher timing; command gap/CPU utilization/native realtime latency are NOT_RUN. Peak RSS is process lifetime high-water, not per-case incremental RAM. Clearance metric subtracts circumscribed radius from cell-distance and is conservative/quantized, not exact body clearance.

## Failure history

Development initially expired all observed free space, making the occluded goal unknowable; new_obstacle timed out. Fixed: static known-free prior remains independent; previously observed occupied cells expire to unknown. Initial narrow-infeasible fixture used0.50m (physically feasible bodywidth0.36m but conservative circle rejected); corrected to0.25m. Review fixed nonfinite command/receipt validation, OOB planning, footprint-dependent sweep, production-topic config leakage and misleading scenario labels. `results/development/pre-review.json` and `results/development/interleaved-run.log` are historical, not final acceptance. The historical log contains interleaved prior process output and null gaps; final-run.log is clean authoritative sweep output.

## Integration and rollback

See INTEGRATION_DIFF.md for file-specific production proposal. No production diff was applied. Integrator must add new versioned profile and precise policy readbacks, preserve current default, wire single-owner mission constraints before final Collision Monitor and bridge. No nonzero command after collision stop; no cached command replay. Node/session cancellation stays latched.

First hardware work, by separately authorized integration owner only: stationary sensor shadow → measured narrow low-speed goal → new obstacle → full barrier/removal. This handoff does not authorize hardware motion. Rollback is to leave this entire experiment directory unreferenced; no production services or configuration need reverting.

## License and artifacts

New project-local code uses the repository license. Runtime dependencies retain upstream licenses (NumPy/SciPy BSD, Pillow HPND-family, PyYAML MIT); package versions are pinned, source/licensing metadata should be retained in redistribution. No downloaded model weights/raw private sensor recordings/credentials included. Generated GIF/PNG are synthetic fixture visualizations. SHA256SUMS hashes delivered files excluding itself and cache; CHANGED_FILES enumerates the local subtree. Parent's source package is the applyable artifact, not a staged git change.

Cross-module integration is separate: traffic defaults to ROS domain173, avoidance183; there is no direct ROS wiring between them. Integration owner's explicit fail-closed adapter is under sibling `integration/`, not proven by hardcoded RED fixture. Native command freshness/identity remains required regardless of synthetic integration results.

Late review added a retired-sensor-epoch set to reject delayed old-process data before any map mutation; dedicated test passes. The final scenario batch was already running with earlier same-epoch logic; all scenario sensors retain sensor-1, so this change is covered by unit regression, not claimed as a multi-epoch closed-loop replay. CPU utilization and native publish-gap measurements remain NOT_RUN.

## Git publication (2026-10-24)
This source snapshot is prepared for publication on main. Earlier no-publication statements describe the authoring stage. See experiments/competition_vm/PUBLICATION.md for included artifacts, exclusions and final test status. Module checksums describe the Git publication subset, not the separately delivered immutable ZIP. No real robot measurements are included.
