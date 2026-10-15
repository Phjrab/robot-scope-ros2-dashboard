# Localization startup follow-up — 2026-10-15

> Current scope through40: the user explicitly extended the completed stage36 snapshot. Candidate863682e was deployed; initialpose1 and180s stationary observation were completed and owned resources cleaned. Live acceptance remains partial/false. See [STAGE40_VALIDATION.json](STAGE40_VALIDATION.json), [DEPLOYMENT_ACCEPTANCE.md](DEPLOYMENT_ACCEPTANCE.md) and [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md). Earlier stop-after36/no-deployment statements below describe the historical software snapshot.41–43 remain NOT_RUN.

**Historical operational startup cause: UNCONFIRMED. Diagnostics: SOFTWARE_READY. Reproduced software regressions: SOFTWARE_FIXED. Latest device reproduction: BLOCKED.** The two failures in [04_new_map_followup](../hardware-validation/04_new_map_followup.md) remain failures. The localization subtask made no device changes. The integration owner separately performed the read-only device inspection recorded in BASELINE.md. No localization, initial pose, goal, deployment, service restart or ROS subscription was performed.

The inspected local source baseline is `2555f3763996c7b331389924bb5df48d62094736` on `main`, followed by the changes in this integration commit. The device source recorded by the inherited evidence is `416d25c`; local source and fixtures are not a deployment claim. The initial local checkout was clean. Other integration owners change the gateway, planner, and Multi-SLAM files separately.

## Production route and fixed profile differences

| Layer | Onboard / wired | Wireless / competition FAST-LIO | Evidence boundary |
| --- | --- | --- | --- |
| Navigation launch/setup | `scripts/run_go2_navigation_humble.sh` → `setup_go2_ros2_humble.sh`; onboard adds `apply_go2_onboard_contract.sh`, Humble/CycloneDDS/direct DDS/local lifecycle | Same navigation launcher → `setup_wireless_mapping_ros2_humble.sh`; `ROS_LOCALHOST_ONLY=1`, local participant limit 32 | Source inspection; current child-process environment on device unmeasured |
| Converter | `run_xt16_bridge_humble.sh` → installed C++ `robot_scope_xt16_bridge_node` | `run_xt16_cloud_bridge_humble.sh` → installed C++ `robot_scope_xt16_cloud_bridge_node` | Installed executable path/hash must be captured in the approved live window; Python `xt16_fastlio_bridge.py` is a contract/reference, not proof of the running executable |
| Clock conversion | C++ `CloudContract`/`ClockOffsetTracker` converts raw XT16 timestamps into host ROS cloud stamps; IMU is host stamped | Same clock contract after bounded transport | Runtime performs no second source-clock offset conversion; device epoch difference alone is not latency |
| FAST-LIO | `run_hesai_fastlio_humble.sh` sanitizes overlay variables, loads Humble + installed Livox/FAST-LIO overlays, selects direct DDS | Wireless wrapper selects local DDS and the optional D2 config | Current installed ROS/FAST-LIO versions and environment remain live evidence requirements |
| FAST-LIO config | `config/fastlio_xt16.yaml`: `/velodyne_points`, `/imu/body`, time sync false, offset 0, scan rate 10, dense false | Same, or explicit D2 `fastlio_xt16_d2_relocalization.yaml` with dense true | Both retain the source-clock contract; D2 opt-in is not enabled here |
| Runtime input | `navigation_runtime.NavigationRuntimeNode`; PointCloud2 `/velodyne_points`, Odometry `/Odometry`, sensor QoS BEST_EFFORT / VOLATILE / KEEP_LAST / depth 5 | Identical input subscription and frames | Cloud `hesai_lidar`; odom `camera_init` → `body`; leading single slash is supported |
| Controller odometry | `strict_onboard` consumes the separate fixed `/utlidar/robot_odom` authority in the gateway | Only explicit `competition_fastlio` runtime projects `/Odometry` to `/robot_scope/nav/controller_odom_fastlio` via its existing gate | No profile/topic substitution; output source stamp is preserved |
| Readiness/startup/API | Runtime emits `/robot_scope/nav/runtime_health`; gateway validates source cardinality, source freshness, validated receipts, startup boundary, sequence warmup, and localization health | Existing server-owned competition rate readiness policy remains in force | `navigation localization inputs are stale` is emitted before initial-pose readiness when cloud or odom freshness is false; a planner success does not satisfy this gate |

Runtime freshness remains cloud **0.75 s**, odometry **0.50 s**, allowed future source skew **0.25 s**. No source timestamp rebasing, future clamp, startup timeout extension, freshness/rate relaxation, stationary inference, or forced initial pose was added. Nav2 YAML snapshots and map files were not changed.

Local inspected source/config SHA-256 (these are not deployed executable hashes):

| File | SHA-256 |
| --- | --- |
| `robot_dashboard/navigation_runtime.py` | `66e4fbe4fb57113cde459cc45fb3306569bbf41dba00d7f0c1abf710963ac519` |
| `robot_dashboard/localization_diagnostics.py` | `90a010d966573f83aa35515e0da4af475e51196dc01de1eda2ddce76c93fc029` |
| `config/fastlio_xt16.yaml` | `3d3fd83fe14c21d07d0b7108f4818d74c0557d67006aa00bc24295e8d30dd4bd` |
| `config/fastlio_xt16_d2_relocalization.yaml` | `776ed3e1ecba65629bbc47b422287a66f105dfcfdafcde1d2d6a1668397ad4df` |
| `config/nav2_params_go2_humble.yaml` | `b69ad567f6ab2a6cc8b8a651191676ae69b02e8d9fca162f1afdce5f8007b6c0` |
| `scripts/run_go2_navigation_humble.sh` | `07c7dbc05ffdd2a92319d3398b465d7d51723e36c66478c9d24e958b94aab92a` |
| `scripts/run_hesai_fastlio_humble.sh` | `fc210a72c88211394ea15331e811fae7491462aef872d6c872c509a7fcfd7542` |

## Findings, exclusions, and corrections

1. **Startup count cache is temporarily empty, but no permanent first-sample rejection was reproduced.** The production node starts with publisher counts zero, then its health timer refreshes them. A ROS-shaped fixture delivers a valid first odometry callback before the timer, observes `publisher_not_unique`, then delivers the same still-fresh source sample after graph discovery. It is accepted without rebasing its stamp. This rules out a permanent latch in that precise fixture; it does not prove the device timer/executor received CPU time in the historical run.
2. **Rejected odometry could silently revive old map alignment. SOFTWARE_FIXED.** Previously a stale/invalid/frame/cardinality rejection set `_last_odom_monotonic=0` but retained `_map_to_odom`. The next valid sample skipped the outage branch because the previous receipt was zero and could reactivate the old alignment. `_reject_odometry` now invalidates map alignment immediately. A valid resumed sample restores input freshness while map alignment remains absent until the existing approved initial-pose path runs. This defect is separate from the historical pre-initialpose startup failure.
3. **Source progress and publisher restarts were not explicit in strict runtime health. SOFTWARE_FIXED.** Strict runtime now rejects duplicate/backward stamps relative to its last accepted odometry sample. A discovered endpoint GID change clears accepted rate windows, transform receipt evidence, old alignment, source-order state, and the existing competition controller gate. The first legal sample from the new source may warm up naturally. Generation is derived from endpoint GIDs, never from matching node names alone. No GID support is represented as unavailable evidence.
4. **Process PID is insufficient to identify one runtime invocation.** Runtime health now includes an invocation token `runtime_instance_generation` (PID plus process monotonic start token) and advancing `health_sequence`, in addition to the existing numeric `process_generation`. The gateway integration resets its warmup sequence state when this identity changes. An unchanged PID with a new invocation token is covered by the production-node fixture; gateway acceptance and projection tests are owned by the integration change.
5. **Historical null odometry age/rate had several indistinguishable explanations. DIAGNOSTICS_READY.** New bounded input telemetry distinguishes `no_callbacks`, `all_received_rejected`, `rewarming_after_source_change`, and `insufficient_accepted_samples`. Older or missing diagnostic producers remain unobservable; an absent field must not be interpreted as zero callbacks or success. A discovered endpoint without a delivered callback, including unknown offered QoS in the fixture, stays unavailable. Actual QoS incompatibility requires RMW evidence and is not asserted by this fixture.

No current evidence proves converter/consumer double correction, a wrong child ROS environment, DDS QoS incompatibility, starvation, or a FAST-LIO defect caused both historical failures. Existing source shows conversion only in the bridge and explicit profile setup in the launchers, but deployed executable hashes and the actual environment may differ. The historical stage04 observation of recovered source stamps followed by null accepted odometry still motivates a callback-level probe.

## Bounded evidence contract

`robot_dashboard/localization_diagnostics.py` supplies a ROS-independent recorder and `sanitize_localization_diagnostics` API whitelist. Runtime health carries optional `localization_diagnostics` schema `robot-scope.localization-input-diagnostics.v1` at most **once per second**; intervening 10 Hz health messages omit it. The gateway may retain the last snapshot only within the same runtime invocation; the snapshot's own wall/monotonic observation time and health sequence remain explicit.

Each fixed input reports subscriber topic/type/requested QoS, at most four publisher endpoint identities with offered reliability/durability, publisher count, source generation, callback/accepted/rejected counters, fixed rejection reason counters, last callback source stamp + wall receipt + monotonic receipt + frame/child frame/cardinality/generation, last accepted receipt, accepted age/rate, and an eight-event receipt/reason ring. Counters saturate at `2**53-1`. No cloud payload, bag, map, arbitrary error string, high-rate log, or unbounded list is captured. Graph identity lookup is limited to once per second.

Existing callback duration, health timer gap/duration, graph-count duration, and optional RMW-receipt/executor-queue windows remain diagnostic-only. Unsupported RMW receive timestamps stay null; source time and callback time are never substituted for DDS receipt. Application lock wait is explicitly null because the single executor has no instrumented application lock. The current health callback's own duration becomes visible on the next health sample. Diagnostic values never grant readiness or rewrite a source timestamp.

## Local validation

Executed with `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`, CPython **3.13.2**, without installing or changing packages:

| Command | Result / validation type |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_localization_startup_diagnostics.py' -v` | 13 passed; production ROS node class instantiated against ROS-shaped fixture modules/messages/graph, actual callback/timer paths |
| `python3 -m unittest discover -s tests -p 'test_navigation_runtime.py' -v` | 18 passed; projection/transform math, fixed launcher safety, real Humble executor-shape metadata path, RMW unavailable/queue contracts |
| `python3 -m unittest discover -s tests -p 'test_track_c2_fastlio_controller_odom.py' -v` | 17 passed; existing controller frame/stamp/cardinality/discontinuity/silence contracts and fixed profiles/no-goal checks |

The new fixture covers no input, valid warmup after initial rejection, stale/future/missing source time, wrong frames, invalid pose, duplicate publisher, duplicate source stamp, a source outage and resume, source endpoint generation change, competition projection stamp preservation, same-PID runtime invocation restart, snapshot progression, bounded rings, diagnostic publication rate, and API whitelist rejection of oversized/nonfinite/bool-counter data. Source-clock boundary tests preserve acceptance at exactly 0.50 s past and 0.25 s future. A Python package-style test invocation failed because `tests` is not an importable package; the discovery commands above were then used successfully.

These are software fixtures and existing unit/launcher checks. They are not native ROS/DDS replay, native device execution, a live startup retry, a stationarity/alignment measurement, or live acceptance. Full repository regression and publication are performed by the integration owner.

## Remaining live row and next minimum probe

**BLOCKED — current stage40 deployment/localization approval and field conditions have not been established; read-only device access was confirmed by the integration owner in this software work.** The inherited map/catalogue and operator pose evidence must be reused and revalidated under the current revision fence; this document does not request them again or publish private coordinates.

In a separately authorized stage40 window, first capture source/runtime/config hashes, actual cwd/interpreter, inherited ROS environment/domain/RMW/interface, node graph identities, active owner/job state, and passive input freshness. After permission and current safety/ownership conditions hold, deploy the reviewed source and collect a short pre/during/post trace for one localization-only startup with the same process invocation token. Read the explicit runtime input snapshot before adding any passive subscribers; measure subscriber overhead if a new observer is needed. Compare source stamps, callback counts/reasons, accepted stamps/ages/rates, timer/queue windows, publisher GIDs, runtime identity, and gateway/startup projection at matching health sequence boundaries.

If callbacks are zero with one publisher, inspect exact subscription type/QoS/domain/environment and executor scheduling. If callbacks arrive but all reject, use the fixed reason plus source/frame/cardinality evidence to choose the next probe. If accepted input is fresh but the gateway reports stale, compare the same runtime instance and producer health sequence before touching any thresholds. If a source or process restarted, collect the new warmup rather than mixing generations. Do not repeat the same failed startup without changed evidence. Initial pose remains gated until localization input readiness; no goal or motion is part of this investigation.
