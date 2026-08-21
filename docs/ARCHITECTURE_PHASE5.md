# Phase 5 RosAgent Control/Navigation-Plane Decomposition

This document records the Phase 5 ownership change. It supplements the Phase 0
baseline, the Phase 3 application-container boundary, and the Phase 4
observability-plane decomposition. Application-level mapping/navigation
coordination remains explicitly outside this phase.

## Compatibility facade

`robot_dashboard.ros_agent.RosAgent` remains the application-facing ROS facade.
Its constructor, public control/navigation methods, response projections, fixed
topic constants, and bounded public navigation-reason helper remain compatible.
The facade now constructs exactly one control transport and one navigation
gateway:

| Component | Owned responsibility |
| --- | --- |
| `ros/control_transport.py` | The single `ControlManager` instance, shared control-operation lock, signed command/status ROS endpoints, bridge key/epoch/sequence, authenticated status/cardinality validation, output publication/draining, target-change stop, and idempotent final-stop shutdown. |
| `ros/navigation_gateway.py` | Fixed Nav2 ROS endpoints, validated navigation-only freshness receipts, odometry stamp fences, runtime-health projection, pinned map session, autonomous lease state, goal/costmap generations, and stop-before-cancel behavior. |

Temporary compatibility properties on `RosAgent` forward legacy private probes
to those component owners. They do not create duplicate managers, locks, keys,
leases, ROS handles, freshness receipts, or navigation state.

## Dependency and lock boundary

`ControlTransport` depends on the ROS-independent `ControlManager`, but it does
not import navigation or the web application. `NavigationRosGateway` receives a
narrow control port; it never publishes Unitree requests directly and does not
import FastAPI, application coordinators, mapping jobs, or navigation process
jobs. The transport does not depend back on the navigation gateway.

Both components share the exact same re-entrant control-operation lock. That
lock remains the outer serialization boundary for every manual/autonomous
control mutation and output publication. The navigation gateway retains its own
separate re-entrant state lock. The preserved nesting order is control operation
lock before navigation/transport/manager-internal locks; no component introduces
the inverse order.

## Preserved control safety

- `ControlManager` remains implemented in `robot_dashboard/control.py` and
  continues to own double opt-in, exclusive manual/autonomous lease semantics,
  binding and sequence checks, deadman/heartbeat timeouts, motion clamps and
  slew limits, action allowlists, and the latched software E-stop.
- Browser control still crosses only the HMAC-signed fixed topics
  `/robot_scope/control/command` and `/robot_scope/control/status`.
- Signed status still requires a valid signed bridge epoch, LowState freshness,
  exact graph cardinality, one owned sport publisher, no foreign named
  publisher, and the configured bare Unitree publisher baseline.
- A bridge epoch change revokes readiness and flushes a StopMove using the new
  epoch before the transport can become ready again.
- Missing or invalid keys/status, stale status, publication failure, unavailable
  ROS handles, and shutdown all fail closed.
- `robot_dashboard/go2_control_bridge.py` remains a separate watchdog process.
  Its replay/epoch checks, graph checks, 200 ms watchdog, and startup/periodic/
  shutdown StopMove behavior are not moved into the dashboard process.

## Preserved navigation safety

- Nav2 velocity enters only through `/robot_scope/nav/cmd_vel_raw` and then uses
  the same `ControlManager` lease and signed transport as manual control.
- Scan, FAST-LIO odometry, controller odometry, localization, and runtime-health
  callbacks retain fixed topics/QoS, structural validation, exact-one publisher
  checks, strict stamp progression, and bounded freshness.
- Safety receipts remain separate from graph/UI rate meters. Observability
  callbacks cannot open the motion gate.
- Controller odometry retains its robot-clock progression contract; FAST-LIO
  odometry retains host-age/future bounds.
- Map ID/revision pinning, goal-generation fencing, late callback rejection, and
  costmap clear-generation fencing are unchanged.
- Deactivation and goal cancellation still publish/flush zero motion before an
  asynchronous Nav2 cancellation request.
- Manual and navigation control remain mutually exclusive through one manager.

## Cross-plane timer and shutdown order

The 50 ms control timer is created by `ControlTransport`, but its callback stays
on the `RosAgent` facade so it cannot bypass navigation safety. Under the shared
operation lock, the exact order is:

1. reconcile validated navigation inputs and lease state;
2. refresh the navigation heartbeat or deactivate;
3. fail closed on stale signed bridge status;
4. tick the single `ControlManager` and publish signed outputs;
5. reconcile navigation again after publication.

The pre-check prevents one final non-zero output after sensor freshness or graph
cardinality is lost. The post-check closes a lease that changed during the tick.

Shutdown order also remains fail closed: deactivate navigation and flush its
signed stop while the ROS node is alive, close/drain the control manager and
publish its final signed stop, then stop the runtime/executor. Repeated shutdown
calls are idempotent.

## Deliberately retained for Phase 6

The FastAPI routes and application-level navigation transaction remain outside
the extracted ROS components. In particular, this phase does not move or
redesign:

- `ApplicationRuntime` navigation startup task/state/fences;
- mapping ownership and exact mapping job compare-and-stop cleanup;
- `NavigationJobManager` process groups, logs, map/parameter revisions, and
  known-free/robot-radius pose validation;
- lifecycle blockers, request confirmation, cancellation settlement, and
  terminal cleanup coordination;
- saved-map filesystem ownership or mapping/navigation command allowlists.

Those concerns belong to Phase 6. Starting that phase automatically would mix
the ROS safety boundary with application transaction ownership, so it is not
part of this change.

## Side-effect policy

This refactor is verified with local unit, architecture, compile, and static
tests only. It does not initialize a live robot ROS graph, start or stop a
service, publish a robot motion command, launch mapping/navigation, send a goal,
or mutate map/runtime data.
