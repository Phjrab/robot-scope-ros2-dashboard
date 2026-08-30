# WP06 Competition Cockpit and operation modes

## Scope and authority boundary

WP06 adds one server-authoritative operation-mode and configuration-lock state to the
existing Cockpit. It does not add a perception-to-motion path. Perception remains
`SHADOW`, and the public motion authority is always `NONE`. The existing control,
mapping, navigation, camera and dataset owners remain unchanged.

The initial persisted requested mode is `MANUAL` to preserve the existing workflows.
`SHADOW` can be selected only while idle and unlocked. `ASSISTED` and `AUTO` are
represented in the API and UI but rejected by the server and disabled in the browser
until separate hardware acceptance and competition-rule review. `SAFE_STOP` is
derived when authoritative control state is unknown or the dashboard software stop is
latched; it cannot be selected as a source of authority.

## Persistent state and transitions

State is stored in `ROBOT_SCOPE_COMPETITION_STATE_DIR` (default
`runtime/competition`) as atomic mode-0600 JSON inside a mode-0700,
service-user-owned, non-symlink directory. Invalid schema, permissive file mode,
symlink or unreadable state fails startup closed instead of silently resetting Lock.

```text
MANUAL --explicit SHADOW confirmation, idle, unlocked--> SHADOW
SHADOW --explicit MANUAL confirmation, idle, unlocked--> MANUAL
any requested mode --software STOP or unknown control state--> displayed SAFE_STOP
UNLOCKED --explicit LOCK--> LOCKED
LOCKED --explicit UNLOCK + stationary confirmation + blockers clear--> UNLOCKED
```

Unlock blockers are active control lease, navigation, mission ownership, dataset
capture or mapping activity. The stationary checkbox is explicit operator
confirmation; it is not inferred from stale odometry. Lock persistence never restores
ARM, a control lease, navigation or AUTO after restart/reload.

## Competition Lock gate

When locked, the server blocks model activation/rollback, robot network target and
source selection changes, PointCloud diagnostic settings, dashboard service
restart/stop, control-bridge start, navigation parameter changes, map revision
creation/conversion/edit/annotation/rename/delete and mission revision creation.

Safety cleanup remains available: software STOP, DISARM, control-bridge stop, mapping
stop, navigation stop/cancel, mission abort and dataset capture stop are not gated.
Competition Lock is configuration freeze, not a physical E-stop.

The local model tool reads the same competition state before `activate` or `rollback`.
For split-host operation, `ROBOT_SCOPE_COMPETITION_STATE_DIR` must identify the state
belonging to the activation host. Model artifacts remain local-only and are never
activated through a browser API. A missing competition state blocks activation instead
of creating an implicitly unlocked state.

## Cockpit display and performance

The fixed HUD displays Robot Link, LowState age, control bridge/source, ARM/DISARM,
deadman, software STOP, physical-stop reminder, operation mode, Lock, perception
authority and dataset state. Missing/stale competition state displays
`SAFE_STOP · UNKNOWN`, `UNKNOWN · BLOCKED`, and authority `NONE`.

The Competition Status surface reuses existing camera catalog and perception
subscriptions. It does not acquire a camera viewer or create PointCloud/WebSocket
sources. It displays Wi-Fi/RSSI/link, camera and transport status, decode/reconnect,
clock domain, lane/object/depth state, model ID/hash, sequence, age, FPS/p95,
confidence, depth/PointCloud summary mode, active/previous/transition model state, and
dataset capture. RTT p50/p95/p99, loss and measurement time explicitly show
`UNAVAILABLE` until a bounded measurement owner exists.

Stale camera frames are cleared by the existing panel and stale perception overlays
are gray with `STALE` and age. Status polling/subscriptions stop when Cockpit is
inactive. Perception polling runs only on visible Sensors or Cockpit pages.

## Operator API

- `GET /api/v1/competition`
- `POST /api/v1/competition/lock` with `{"confirmation":"LOCK"}`
- `POST /api/v1/competition/unlock` with
  `{"confirmation":"UNLOCK","stationary_confirmed":true}`
- `POST /api/v1/competition/mode` with exact mode and matching confirmation

Mutations are same-origin, use the shared coordination lock, and enter the bounded
operator-event timeline.

## Hardware acceptance remaining

WP06 software tests use a bounded fake backend. A supervised stationary session must
still confirm real Wi-Fi RSSI/link, RealSense receive/decode/reconnect, perception
model/hash/sequence, competition-display layout and physical-stop reminder placement.
RTT/loss stay `UNAVAILABLE` by design. `ASSISTED` and `AUTO` remain disabled.

## Rollback

Rollback the WP06 commit through the normal repository procedure and restart only in
a supervised maintenance window. Preserve `runtime/competition/state.json` as
evidence. Older code ignores the new directory. Do not delete model, dataset, map or
mission artifacts and do not manually edit the state JSON.

If state is invalid, leave the dashboard fail-closed, capture the file and permissions
for diagnostics, then restore a known valid file or perform an explicitly reviewed
migration while the robot is stationary, DISARMED and services are stopped.
