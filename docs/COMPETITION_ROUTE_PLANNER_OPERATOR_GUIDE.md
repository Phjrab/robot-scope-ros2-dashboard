# Competition Route Planner Operator Guide

This guide covers software-only planning. It does not authorize robot motion.

## Setup

1. Open the Cockpit and launch **Route Planner** from the existing panel launcher.
2. Confirm the displayed map and graph revision. A production graph must reference annotations from that exact saved 2D map revision.
3. If no graph is configured, a trusted setup operator must create point annotations and upload a bounded graph through `PUT /api/v1/route-planner/graph`. Do not guess competition coordinates.
4. Keep Competition Lock unlocked only for the intended edit. The existing lock blocks every planner mutation.

## Enter the order

Choose one destination and enter two to five ordered lines. The UI displays total items, restaurant count, 20-second production timing and capacity. The server independently checks every rule and derives difficulty. Lock the order after review if it should no longer change.

Example acceptance order:

- Destination: COEX
- 1: HANSOT / CHICKEN_MAYO ×2 (ready estimate 40 s)
- 2: EDIYA / AMERICANO ×1 (ready estimate 60 s)
- Result: LOW, three items, two restaurants

## Recommend and select

Select a start annotation node and calculate. Up to three cards show BALANCED, FASTEST and SAFEST badges plus distance, ETA, food wait, signal wait, risk, crosswalks, UNDERPASS use, turns and special requirements. If profiles choose the same node path, one card carries multiple badges.

Select exactly one server recommendation. The yellow 3D line is the selected graph route; translucent lines are alternatives; red is the current guidance segment; blue dashed is an actual Nav2 path when one is independently available. These overlays are not a Nav2 plan.

## Manual guidance

Start guidance only after a route is selected. It reads the server Navigation localization pose and displays direction, segment progress, distance, ETA, cross-track error, signal, pedestrian, alignment, UNDERPASS and docking readiness.

UNKNOWN or stale perception means wait/warn. Guidance never drives the robot. Continue to use the existing controller/control workflow and its safety procedures. Explicitly end guidance when done. Closing the panel only releases its UI polling; server guidance remains active until stopped or restarted.

## Mission draft and preview

`NAV2 PREVIEW` returns an exact 2D Route Graph preview. Live Nav2 planner-only preview currently reports `BLOCKED / SAFE_PLAN_ONLY_NAV2_INTERFACE_NOT_AVAILABLE` because the installed gateway does not expose a proven plan-only call separated from goal execution.

`MISSION DRAFT EXPORT` resolves selected route nodes to annotation IDs and calls the existing Mission draft creator. Special-edge requirements remain linked by route and segment revision. No Mission is started and no goal is sent. Review the resulting ready Mission in the existing Mission panel; Track G acceptance must not press START.

## Stale and recovery

If the order, graph, map, annotations, planner config, start node or operation mode changes, the state becomes `STALE` and selection clears. Reopen the exact revisions and calculate again. After a server restart, a selection may remain but guidance is always inactive.

## Forbidden in this track

Do not deploy to Jetson, restart robot services, publish `/initialpose`, send a Nav2 goal, start a Mission, acquire a control lease, ARM/deadman, publish `/cmd_vel`, call `/api/sport/request`, sit/stand, or move the robot.
