# Phase 12 — Frontend Extraction and Browser E2E

Phase 12 continues the browser ownership cleanup without changing any backend
safety gate, ROS contract, service policy or robot behavior. Hardware and ROS
are deliberately absent from this phase.

## Dataset feature ownership

The server-side dataset UI moved from the `app.js` global state into
`static/features/datasets/capture.js`. The module exposes a factory and the
full lifecycle expected by the roadmap:

```text
createDatasetFeature(dependencies)
  -> start()
  -> activate()
  -> deactivate()
  -> destroy()
```

The feature now owns:

- capture, catalog and detail response generations;
- the 1.5-second capture poll and one-second elapsed-time renderer;
- the Sensors-page-only 10-second catalog poll;
- all dataset buttons, selectors and gallery listeners through one
  `AbortController`;
- selected-session pagination and the bounded gallery render cache.

Leaving Sensors calls `deactivate()`, cancels the catalog/detail generations
and removes the page-only poll. It intentionally does **not** call the dataset
stop endpoint: capture is server-owned and continues across page navigation or
browser lifecycle events. `destroy()` additionally clears every remaining
feature timer, aborts listeners, invalidates responses and drops feature-owned
cache/state. The existing fixed API paths, opaque session IDs, maximum
24-sample page, same-origin mutation enforcement and recovery STOP behavior are
unchanged.

`app.js` fell from the frozen Phase 12 baseline of 7,435 lines to 6,739 lines.
The module itself is not counted as deletion; the result is a smaller
composition root with one unambiguous data owner.

## Hardware-free browser runner

Playwright Chromium now loads the real dashboard HTML, JavaScript modules and
CSS from a loopback-only static server. HTTP and allowed WebSocket streams are
provided by an in-memory fake backend. The fixture accepts only fixed API
contracts and records mutation requests for exact-count and body assertions.
It never imports or starts ROS, systemd, mapping/Nav2 launchers, dataset writers
or robot control.

The E2E suite covers the roadmap scenarios:

| Roadmap scenario | Browser assertion |
| --- | --- |
| Offline viewer | Live telemetry fails closed while saved-map browsing remains available. |
| Camera reconnect | A forced first socket close creates a replacement connection. |
| Pointcloud reconnect/cleanup | A forced first close creates a replacement stream; page leave closes it and the socket alone never enables map save. |
| Mapping start/save/stop | Confirmed UI actions emit one fixed mutation each. |
| Navigation start/active/cancel | Exact map and parameter revisions are sent; active progress and one cancel are observed. |
| Map revision conflict | An active-map/catalog revision mismatch disables pose and goal controls. |
| Dataset start/finalize | Double clicks still emit one start and one finalize mutation. |
| E-stop latch/clear | Clear stays disabled until local confirmation and sends literal `{confirmed:true}` once. |
| Service lifecycle blocker | Server blockers disable confirmation and lifecycle actions. |
| WebSocket Origin rejection | A cross-origin browser handshake is rejected using the production `is_same_origin` policy. |
| Page-switch cleanup | Camera, pointcloud and dataset page resources are observed closing/deactivating. |
| Duplicate mutation prevention | Mapping, navigation, dataset and E-stop assertions count requests exactly. |

Tests use state and request contracts rather than screenshots. Playwright
disables screenshot/video capture and retains a trace only for a failed run.

## CI contract

CI installs JavaScript dependencies from `package-lock.json`, audits them,
installs Chromium plus its runner dependencies and executes the E2E suite after
the existing Python and Node contract suites. Browser results are therefore
hardware-free and distinct from the deferred Phase 11 supervised hardware
acceptance.

Local commands:

```text
npm ci --ignore-scripts
npx playwright install chromium
npm run test:e2e
```

Final local verification on the Phase 12 tree:

| Check | Result |
| --- | --- |
| Full Python unit/contract suite | PASS — 610 tests |
| Full JavaScript unit/contract suite | PASS — 152 tests |
| Playwright Chromium E2E | PASS — 9 tests covering all 12 roadmap scenarios |
| Dashboard module syntax | PASS — 18 modules |
| Python compileall | PASS |
| Tracked-source credential scan | PASS |
| npm high-severity dependency audit | PASS — 0 vulnerabilities |
| `git diff --check` | PASS |

## Preserved safety boundary

- The backend remains authoritative for capability, mapping, navigation,
  control, E-stop and service lifecycle enablement.
- No browser fallback grants manual-control or navigation readiness.
- No timeout, speed, acceleration, watchdog, lease or publisher-cardinality
  rule changed.
- Reconnect tests do not synthesize a control lease or motion-ready state.
- The fake backend is test-only and cannot be selected by production code.
- No robot, service, mapping, Nav2, map or dataset side effect was executed.

## Deferred work

Camera, saved-map, mapping, overview, navigation-main and manual-control-main
extraction remain later vertical slices. Their resource behavior is covered by
the new browser runner before ownership moves; they must be migrated one at a
time without duplicating backend safety logic.
