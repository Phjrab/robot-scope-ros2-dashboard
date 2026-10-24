# Synthetic fallback results

Not Nav2/RPP/MPPI. Three seeds per scenario. All dimensions/speeds are DESIGN_INITIAL.

| Case | Outcome | Passed | Sim time range s | Contacts |
|---|---|---:|---:|---:|
|empty|GOAL_REACHED|3/3|17.6–17.6|0|
|new_obstacle|GOAL_REACHED|3/3|22.2–22.2|0|
|one_branch_blocked|GOAL_REACHED|3/3|21.1–21.1|0|
|blocked_then_clear|GOAL_REACHED|3/3|27.6–27.6|0|
|sensor_dropout|SAFE_WAIT|3/3|6.0–6.0|0|
|narrow_feasible|GOAL_REACHED|3/3|17.6–17.6|0|
|narrow_infeasible|SAFE_REJECT|3/3|5.0–5.0|0|
|obstacle_variant|GOAL_REACHED|3/3|22.2–22.2|0|
|terrain_handoff|SAFE_REJECT|3/3|0.0–0.0|0|
|red_and_removed|GOAL_REACHED|3/3|35.6–35.6|0|
|stale_tf|SAFE_WAIT|3/3|6.0–6.0|0|
|map_revision|SAFE_REJECT|3/3|3.0–3.0|0|
|cancel|SAFE_REJECT|3/3|3.0–3.0|0|
|restart|SAFE_REJECT|3/3|3.0–3.0|0|
|leg_corridor|GOAL_REACHED|3/3|17.6–17.6|0|
|map_misalignment|GOAL_REACHED|3/3|21.5–21.5|0|
