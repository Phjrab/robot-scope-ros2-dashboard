# Independent articulated visualization review

Reviewed 2026-10-24 UTC, offline only. Source `gait.py` SHA256
`794fb1d72fa31794deac809fed67e86a0093e68fb117d0355e3f20ed9ef6578a`.

## Findings and resolution

The first implementation normalized gait phase over the whole trace. An intermediate
pause at phase 1.875 left FL/RR feet suspended. Reproduced with a synthetic move,
2-second pause, and resume trace. The implementer changed phase scheduling to
contiguous moving segments ending at integer cycles. The independent regression
now passes; all feet remain in stance and joint positions freeze during the pause.
This regression is a unit fixture, not a newly simulated robot mission.

## Executed checks

`python3 -m unittest discover -s experiments/competition_vm/arena_robot_sim/revisions/articulated-20261024/review -v`

8 tests PASS: official-derived joint bounds, independently recomputed rigid FK and
all visible mesh vertices above floor, exact preservation of every original trace
pose sample, fully stationary blocked case, zero consecutive-stance horizontal foot
slip, actual moving-joint variation, mid-route stationary stance, and bounded sampled
joint velocities. Tests use the official-derived repository asset, not hardware.

`python3 experiments/competition_vm/arena_robot_sim/revisions/articulated-20261024/review/audit_projected_hull.py`

3692 poses (2791 detour + 901 blocked), including terminal poses, were checked at
10 interpolation substeps per 15-Hz animation interval. The audit independently
recomputes all visual mesh world vertices and a conservative XY convex hull.
Wall/cone crossings, cone containment and floor-edge violations: all zero.
Floor edges are sampled at no more than 5mm spacing. Minimum mesh ground clearance
is approximately 0.899mm. At 15Hz the minimum projected-hull boundary clearance is
0.15666m for detour and 0.28932m for blocked; these are NOT the original static
rectangle/grid-clearance metrics. See `projected_hull_audit.json`.

Visual inspection of rendered frame 0100 confirms articulated legs and feet are
visible, with cone and executed-path context. The display-only shortened fence
must remain disclosed; it is not the sensor/collision height.

## Limits

- This is offline kinematic animation of saved SIM_GT planar poses, not dynamics,
  locomotion policy, contact force, balance, self-collision or hardware validation.
- The geometric sweep is sampled, not a continuous formal collision certificate.
- Original provisional floor permission includes parking extension. The check is
  not strict parking exclusion and not competition compliance.
- Actual public source trace timestamps/metrics remain unchanged. Animation uses
  interpolated poses and newly synthesized joints, not recorded joint telemetry.
- The new corridor revision and full terrain course were not used in these clips.
- The enlarged articulated envelope cannot inherit the original planner footprint
  qualification; this separate bounded geometric audit is evidence only for these
  two recorded visualizations and the specified interpolation.
