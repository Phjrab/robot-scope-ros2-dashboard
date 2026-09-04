# Route Planner Perception and Control Contracts

Track G consumes model-team snapshots. It does not train or run models and does not own control.

## Common envelope

```json
{
  "schema_version": 1,
  "source": "traffic-team",
  "frame_id": "base_link",
  "observed_at_ns": 0,
  "sequence": 1,
  "state": "READY",
  "confidence": 0.96,
  "traffic": [],
  "crosswalks": [],
  "people": [],
  "aruco": [],
  "underpass_blocked": null
}
```

The adapter enforces a fixed schema/source, monotonic non-negative sequence, finite confidence in `[0,1]`, bounded lists of at most 32, and a one-second freshness gate. Public HTTP callers cannot select a ROS topic, message type, action, filesystem path, peer or plugin.

## Typed payloads

Traffic entries identify `crosswalk_id` and `signal=RED|GREEN|UNKNOWN`, with confidence and consecutive frame metadata supplied by the traffic team.

Crosswalk/lane entries identify visibility, lateral offset, heading error and left/right boundary distance. The UI reports the competition rule that three or more feet outside the boundary is a violation; gait/FK enforcement belongs to the control track.

Person entries identify `occupancy=CLEAR|OCCUPIED|UNKNOWN`, nearest distance, collision-risk flag and confidence.

ArUco entries identify venue/zone, bounded visible marker IDs, a finite base-link target pose, confidence and `docking_ready`. Route Planner displays coarse approach and the docking requirement; it does not perform visual servo.

## Requirement projection

| Requirement | READY | Otherwise |
|---|---|---|
| TRAFFIC_GREEN | Fresh entries are all GREEN | BLOCKED on RED, otherwise UNKNOWN |
| PEDESTRIAN_CLEAR | Fresh entries are all CLEAR | BLOCKED on OCCUPIED, otherwise UNKNOWN |
| CROSSWALK_ALIGNMENT | Fresh visible observation inside fixed offset/heading advisory bounds | UNKNOWN |
| LANE_BOUNDARY_VALID | Fresh finite non-negative boundary distances | UNKNOWN |
| ARUCO_DOCKING | A fresh venue observation is docking-ready | UNKNOWN |
| SPECIAL_GAIT | Never decided by perception | OPERATOR |
| OPERATOR_CONFIRMATION | Never automated | OPERATOR |

Manual guidance turns non-READY values into explicit warnings. An autonomous draft retains the requirement but marks the route non-executable until another safety owner validates it. Route Planner never maps any snapshot directly to a command.

## Initial adapter

`MockRoutePerceptionProvider` provides deterministic software-only snapshots and validates monotonic sequence updates. A later ROS adapter must implement the same `snapshot()` protocol and keep topic/message configuration server-owned. It must not be added until each model team finalizes transport contracts.
