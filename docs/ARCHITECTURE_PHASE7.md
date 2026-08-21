# Phase 7 — Frontend Feature Modularization

## Scope

Phase 7 changes the dashboard entrypoint from a classic script to a native ES module and performs an incremental, behavior-preserving extraction. It does not change HTTP routes, request bodies, robot control policy, mapping/navigation orchestration, filesystem behavior, or deployment configuration.

## Extracted ownership

- `static/core/api.js` owns the shared same-origin JSON request helpers and no-store policy.
- `static/core/dom.js` owns DOM lookup and the existing status-pill rendering contract.
- `static/core/format.js` owns shared numeric and frequency formatting.
- `static/core/log_scroll.js` owns the user-scroll-wins sticky terminal behavior and its per-element generation fence.
- `static/features/sensors/lidar_identity.js` owns exact-topic and backend-metadata LiDAR identity normalization.
- `static/features/navigation/log_controller.js` owns Navigation log entries, cursors, stream identity, request/render generations, polling, page lifecycle invalidation, and local-only clear/auto-scroll controls.
- `static/features/control/bridge_service.js` owns control-bridge systemd snapshot state, transition expectations, mutation generation fences, fixed API calls, confirmation UI, page lifecycle invalidation, and polling.
- `static/features/settings/service_lifecycle.js` owns dashboard service snapshot state, transition expectations, fixed restart/stop API calls, confirmation UI, and polling.

`app.js` remains the composition entrypoint. It injects only narrow callbacks needed by the extracted features, such as the active page, toast rendering, and adjacent status refreshes. No feature receives an arbitrary URL, service name, command, credential, or robot-motion primitive.

## Preserved safety contracts

- Service mutations still require the local acknowledgement, browser confirmation, server `can_*` permission, fixed same-origin endpoint, and exact `{confirmed:true}` body.
- `RUNNING` systemd state remains distinct from authenticated control bridge readiness.
- Navigation logs remain read-only, bounded to 300 browser lines, server-sanitized, rendered with `textContent`, and generation-fenced across visibility and BFCache transitions.
- Manual log scrolling remains authoritative over scheduled auto-scroll.
- LiDAR identity still prefers backend metadata and otherwise uses only the exact topic allowlist.
- Existing classic visualization/input modules remain loaded before the ES-module entrypoint; their behavior and public contracts are unchanged in this phase.

## Incremental boundary

The remaining overview, camera media, mapping, saved-map editor, dataset gallery, and primary control/navigation page orchestration stay in `app.js`. Moving them together would be the wholesale rewrite forbidden by the Master Spec. Future frontend changes should continue the same vertical-slice pattern: move one feature's state, network requests, render lifecycle, and tests together, then keep `app.js` as composition only.

## Explicit exclusions

- No framework or bundler was introduced.
- No backend, ROS, process manager, systemd unit, sudoers, profile, script, or runtime-data path changed.
- No Phase 8 API/security hardening or Phase 9 performance work was started.
- No robot, mapping, navigation, service, or remote deployment action is part of this phase.
