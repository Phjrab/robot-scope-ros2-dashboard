# Phase 8 — API Contract and Web Security Hardening

## Scope and security model

Phase 8 inventories the existing HTTP and WebSocket surface, makes the browser
origin policy consistent, bounds request and response projections, and makes
backend metadata authoritative for product capabilities and physical LiDAR
identity. It does not add accounts, sessions, bearer authentication, a remote
trust proxy, or a new network exposure model.

The dashboard remains a direct-LAN operator application. Same-origin checking
is a browser CSRF/WebSocket boundary, not user authentication. A mutation or
browser WebSocket must provide an explicit `http` or `https` `Origin` whose
authority exactly matches `Host`. Missing origins, credentials, paths, query or
fragment components, whitespace/control bytes, oversized values, malformed or
out-of-range ports, scheme-relative values, and non-HTTP schemes fail closed.
Forwarded host headers are not trusted.

All `/api/v1/*` HTTP responses carry `Cache-Control: no-store`,
`X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer`.

## HTTP inventory

The application declares 56 HTTP routes: `GET /` plus 55 `/api/v1/*` routes.
The API methods are 26 GET, 25 POST, 2 PATCH, and 2 DELETE; including `GET /`,
the repository-wide totals are 27 GET, 25 POST, 2 PATCH, and 2 DELETE.

| Domain | Existing routes |
| --- | --- |
| System lifecycle | `GET /system/service`; `POST /system/service/restart`; `POST /system/service/stop` |
| Control bridge lifecycle | `GET /control/bridge-service`; `POST /control/bridge-service/start`; `POST /control/bridge-service/stop` |
| Telemetry and sources | `GET /health`, `/state`, `/topics`, `/sources`, `/pointcloud`, `/pointcloud.bin`, `/pointcloud/settings`, `/map`, `/joints`, `/pose`; `POST /sources`, `/pointcloud/settings` |
| Camera catalog | `GET /cameras` |
| Robot discovery/target | `GET /robots/types`; `POST /robots/discover`; `POST /robot`; `DELETE /robot` |
| Dataset capture | `GET /datasets/capture`, `/datasets`, `/datasets/{session_id}`, fixed sample JPEG; `POST /datasets/capture/start`, `/datasets/capture/stop` |
| Manual control | `GET /control`; `POST /control/arm`, `/control/disarm`, `/control/stop`, `/control/estop/clear` |
| Navigation | `GET /navigation`, `/navigation/logs`, `/navigation/parameters`; `PATCH /navigation/parameters`; `POST /navigation/start`, `/navigation/stop`, `/navigation/initial-pose`, `/navigation/goal`, `/navigation/cancel`, `/navigation/clear-costmaps` |
| Mapping | `GET /mapping/control`; `POST /mapping/start`, `/mapping/stop`, `/mapping/save` |
| Saved maps | `GET /saved-maps`, `/saved-maps/{map_id}`, `/saved-maps/{map_id}/data`; `POST /saved-maps/{map_id}/convert-2d`, `/saved-maps/{map_id}/edited-copy`; `PATCH /saved-maps/{map_id}`; `DELETE /saved-maps/{map_id}` |

Every one of the 29 POST/PATCH/DELETE routes calls the shared
`require_same_origin` dependency. Request bodies inherit the existing strict
extra-field rejection. Safety confirmations use strict JSON booleans, and
source names are bounded to 255 characters before graph/profile validation.
No request body accepts an executable, argv, shell fragment, arbitrary ROS
service/node, filesystem path, YAML document, or arbitrary dataset root.

## WebSocket inventory

The six browser WebSockets are:

| Route | Producer and boundary |
| --- | --- |
| `/api/v1/ws/control` | Fixed signed control transport; exclusive lease, sequence/age/deadman checks and bridge watchdog remain unchanged |
| `/api/v1/ws/pointcloud` | Bounded binary point-cloud frames; producer is the selected backend source |
| `/api/v1/ws/camera` | Compatibility endpoint: defaults to Go2 and accepts only an allowlisted camera `source_id` query |
| `/api/v1/ws/cameras/{source_id}` | Only fixed allowlisted camera IDs; source-bound demand tokens are released on disconnect |
| `/api/v1/ws/joints` | Bounded joint snapshot stream |
| `/api/v1/ws/pose` | Bounded selected-pose snapshot stream |

All six now apply the same explicit-origin policy before runtime lookup or
`accept()`. Rejected sockets close with code 4403 and a fixed reason. Existing
dashboard browsers remain compatible because they construct sockets from
`location.host`. Non-browser clients must now provide a matching Origin for
joints and pose, as they already had to do for control, camera, and pointcloud.

## Backend metadata authority

The backend is the primary authority for both product capabilities and LiDAR
identity:

- `capabilities.py` owns the fixed capability vocabulary and product grants;
  `/robots/types`, runtime health, and selected-profile responses project it.
- Browser fallback robot entries retain only model-preview metadata. If the
  backend catalog is unavailable or incomplete, every declared operation
  capability is false, so fallback data cannot enable capability-gated manual
  control. Mapping and navigation remain governed by their existing backend
  runtime safety/readiness responses rather than the profile fallback.
- `ros/sources.py` owns the exact physical-sensor and processing-stage mapping.
  `/sources`, `/topics`, `/state`, pointcloud JSON, and pointcloud binary/WS
  metadata carry that identity.
- The browser no longer classifies a physical sensor from a topic substring or
  a duplicate topic allowlist. Without backend identity metadata it renders a
  generic pointcloud with unknown stage. Backend display labels take precedence
  over presentation fallbacks.

Freshness and availability remain backend observations. Presentation code may
format the labels and states but does not grant capabilities or infer a sensor
make/model.

## Public response exposure

Intentional operator-visible data is preserved:

- ROS topic/type/rate/freshness and selected-source metadata;
- configured robot IP/hostname and local ROS/runtime diagnostics;
- fixed camera URI/transport metadata;
- bounded job, goal, map, revision, lifecycle, and dataset session identifiers;
- safe map filenames;
- the one-time control `lease_id` returned by ARM, required for its same-origin
  WebSocket bind;
- dataset `output_path`, an existing documented operator contract for local or
  SSH access to the server-owned fixed dataset root. It is not a browser-input
  path or arbitrary filesystem browsing API.

Browser responses do not expose:

- the control bridge shared key, MAC, bridge epoch, process ID, signed issued
  timestamp, camera demand tokens, or navigation private token/binding;
- process argv/environment, raw child stdout/stderr, or arbitrary exception
  details;
- saved-map/navigation private absolute paths or staging transaction paths.

Control bridge status uses an explicit public field allowlist. Mapping and
navigation child output use one bounded 320-character diagnostic sanitizer:
only standard ROS envelopes and the fixed launcher prefix retain a redacted
payload; commands, credentials, URLs, paths, control bytes, and long opaque
identifiers are withheld. Health and camera error strings use the same
redaction at serialization. Dataset storage/startup/write errors and source
selection persistence errors return stable public messages while detailed
exceptions remain server-side logs. Known mapping and saved-map 500 responses
also use stable generic details.

## Preserved safety invariants

- Control still flows Browser -> `ControlManager` -> signed fixed-topic
  transport -> standalone Go2 watchdog -> fixed sport request path.
- The exclusive lease, 200 ms command deadman, heartbeat/bind expiry, E-stop,
  action guard, speed clamps, bridge epoch fencing, and final signed stops are
  unchanged.
- Mapping/navigation coordinators retain their single shared coordination lock,
  exact job/token ownership, second pre-motion readiness check, cancellation,
  compare-and-stop, and shutdown ordering.
- Filesystem roots, opaque IDs, symlink/containment checks, atomic map/dataset
  publication, quotas, and cleanup behavior are unchanged.
- No service start/stop/restart, robot motion, mapping/navigation launch, map
  mutation, dataset capture, deployment, or remote network action was used to
  validate this phase.

## Compatibility and remaining risk

- Existing API paths, methods, core operator state fields, and fixed source IDs
  are retained. Phase 8 deliberately narrows a small set of unsafe response and
  validation contracts:
  - mapping clients must use stable `job_id` and `state` fields instead of the
    removed process-local `preview.pid` and `pipeline.pid` fields;
  - control clients must use the public bridge readiness, cardinality, age, and
    bounded `message` fields instead of private epoch/PID/issued-time or unknown
    signed-payload fields;
  - diagnostic consumers must treat mapping/navigation log and error text as a
    bounded operator message, not raw child output or a machine-readable
    exception; state, phase, cursor, and job identifiers remain the authority;
  - `POST /control/estop/clear` now accepts only a literal JSON boolean for
    `confirmed`; strings and integers that were previously coerced are rejected.
  The bundled dashboard did not consume the removed PID/private bridge fields
  and already sends a literal boolean. Coordinator, API-contract, and browser
  regression tests fix these migration boundaries.
- One deliberate fail-closed UI change is that a temporary `/robots/types`
  catalog failure leaves fallback manual-control capability disabled until the
  page is reloaded and the catalog succeeds.
- Native clients that omitted Origin for joints/pose must add the same matching
  Origin already required by the other WebSockets.
- This phase intentionally does not solve LAN host-header/DNS rebinding, add
  user authentication, or authorize internet exposure. Operators must keep the
  dashboard on the intended trusted network and preserve the external Host when
  using a reverse proxy.
- Dataset paths and operational ROS/robot metadata remain visible to anyone who
  can reach the dashboard by explicit product contract.
- Live Jetson/ROS/hardware acceptance remains deferred; repository tests cover
  the web and projection contracts without side effects.

## Phase 8 acceptance

- PASS — HTTP and WebSocket routes are inventoried and locked by regression
  tests (55 API HTTP routes, 29 mutations, 6 WebSockets).
- PASS — all browser WebSockets share the same fail-closed origin policy.
- PASS — every HTTP mutation retains same-origin enforcement.
- PASS — raw process/exception/control-bridge internals are removed or redacted
  from browser projections while intentional operational fields are documented.
- PASS — backend capability and sensor metadata are the primary browser
  authority; local fallbacks fail closed.
- PASS — no authentication product or Phase 9 tooling work was introduced.
