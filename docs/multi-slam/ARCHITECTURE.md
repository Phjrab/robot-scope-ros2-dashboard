# Architecture and MR context

`slam_wiring` assembles the additive managers. `slam_sessions` serializes
ownership under the existing pipeline lock. `FastLioAdapter` delegates to the
existing mapping manager/coordinator. `IsaacStereoAdapter` uses fixed managed
launch, actual ROS subscriptions/GetParameters/FilePath/LocalizeInMap. Its
optional `slam_broker` proxy keeps operational dashboard DDS separate from the
observer in the preserved Isaac environment. The dashboard has no Docker/sudo
or arbitrary-command interface. Direct runtime is allowed only in an explicitly
isolated process. No package installation/image replacement is performed.

PREFLIGHT/STARTING readiness, WAITING_INPUT, TRACKING/MAPPING/LOST, SAVING,
LOCALIZING, STOPPING, IDLE and cleanup ERROR are explicit. Session IDs/generations
fence commands; bounded request IDs are idempotent for the last256 requests.
Session ownership outlives viewer subscriptions. Source loss never restarts an
engine. Shutdown first stops control, then settles this session's resources.

The camera broker owns the shared flock throughout capture, independently of
dashboard client lifetime. A fresh private handoff, cooperating relay lock and
current OS owner check are all required. Idle RGB viewers do not imply ownership
permission. Existing relay capture uses the same configured lock before opening
the device. Failed cleanup retains ownership for operator inspection. Existing
services are never implicitly stopped/restored. Native runtime lifetime is not
a control lease, ARM or movement authority.

`MappingCoordinator.configure_external_guards` makes existing mapping changes
reject mission activity and MS ownership; Nav's existing mapping activity check
also sees MS ownership. Dataset/profile/RGB acquisition paths reject conflicting
MS sessions. MS starts/save/load/package mutations check Nav, mission paused/
cancel settlement, lease, dataset and lifecycle. MR start/resume/retry must call
`runtime.slam.require_context_idle()` under the same pipeline lock and reserve
mission ownership before releasing it. Read-only planning can use an immutable
context; no MS selection changes operational authority.

Read-only `navigation_context()` schema:

```json
{"schema_version":1,"navigation_map":{"id":null,"revision":null,"frame":null},
 "operational_pose":{"source":null,"odometry_source":null,"frame":null,"generation":null,"readiness":{},"state":"unknown"},
 "alignment":{"verified":false,"transform":null,"reason":"NO_VERIFIED_VSLAM_NAV_ALIGNMENT"},
 "context_revision":"sha256 of canonical projected context"}
```

`source` is the actual map-localization pose binding (normally /amcl_pose);
`odometry_source` is the separate continuous input (normally /Odometry).
Values project actual navigation owner/runtime. Unknown generation/frame stays
null. The observation engine is not a pose source. Readiness is included in the
revision so a previously ready context cannot be silently reused after failure.
VSLAM-to-navigation alignment stays unverified pending separate stage17 evidence.
