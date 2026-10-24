# VM competition work: Git publication, 2026-10-24

## Scope and provenance
This snapshot publishes VM-only work authored against b1077e39e4ee456621c47eada49b1f0c85453661, integrated after upstream main ebce05c (including 6f71a1a and 4f77133) without changing production code. BASE_COMMIT files preserve the authoring baseline. No physical robot access, deployment, actuation, real raw measurements, or service restart was performed by this publication task.

- Arena revision: `assets/competition-arena/revisions/rulebook-20261015/`. Blender/GLB geometry, source, semantic contracts, seven scenarios and previews. Dimensions and competition permissions remain provisional; see ASSUMPTIONS and DIMENSION_DIFF.
- `avoidance/`: hardware-free planner and safety arbiter, 48 synthetic runs, zero recorded contacts/hold violations. This is not native Nav2 RPP/MPPI validation; supplied ROS configurations are candidates only.
- `traffic_signals/`: synthetic vision/stop-go replay and guarded optional detector adapter. Real camera images, trained weights and class names remain INPUT_REQUIRED.
- `integration/`: synthetic traffic FSM to avoidance arbiter contract checks. No native ROS publisher is wired.
- `arena_robot_sim/`: actual repository-derived Go2 morphology, planar kinematics and ideal four-height raycasts. Empty and off-center cone cases reach the goal; fully blocked case waits safely. Exact pose is SIM_GT, not VSLAM; sensor model is not calibrated XT16. Static legs are not gait/contact physics. The final footprint enters the parking opening by 7.8 cm; this is a disclosed local experiment, not a qualified competition route or full-course result.

## Included and excluded artifacts
Source, tests, configuration, synthetic JSON/JSONL observations and traces, authored scene geometry, representative previews, Blender/GLB models, two MP4s and a GIF are included. Synthetic scene mesh fixtures are not measured maps. Official Go2 derivative provenance/license remains in the existing asset tree and rendering directory.

Generated `arena_robot_sim/results/static_grid.npy`, caches, virtual environments, raw/labelled rendering frame sequences, Blender backups, transient build/test/render logs (summaries retained), development-only intermediate avoidance results, and duplicate source ZIP/tar archives are excluded. Original local files and previously delivered immutable ZIPs are preserved, not deleted. `simulate.py` regenerates the local occupancy grid; rendering scripts regenerate frame sequences. No generated map or PCD dataset is committed.

Each module's CHANGED_FILES and SHA256SUMS now describe its Git publication subset, excluding the checksum file itself. They do not describe the earlier standalone ZIP packages. Validation JSON records may refer to locally generated/excluded files as historical evidence, not a claim that those files are shipped. Historical authoring-stage "no Git publication" statements are superseded only by this publication note.

## Revalidation
Publication checks are recorded in VALIDATION_PUBLICATION.json. New VM tests: avoidance 30, traffic 67, integration 16, robot simulation 7 (120 total). JavaScript unit suite and arena GLB validation were also rerun. Final combined snapshot: 656 JavaScript tests pass; full Python suite runs 2,664 tests with 25 Unix-socket permission errors and 1 skip. Full repository Python suite is attempted separately; environment socket restrictions must not be mistaken for a clean suite pass. Native ROS, real sensors, live robot, full-course qualification and physical measurement remain NOT_RUN/BLOCKED.

Module README files contain reproduction commands. Read the safety limitations and handoff before integrating; publishing these artifacts grants no authority to enable live motion.
