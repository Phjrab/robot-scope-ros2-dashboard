# C4 asynchronous ROS owner handoff

This opt-in candidate connects the existing `ReviewRosPort.handoff/offer_raw`
protocol to actual `CanonicalCorePorts` through the existing `TrafficWorker`.
It creates no subscription or device. Never call `ReviewRosPort.start` alongside
an existing subscription owner. The exact handoff is after that owner's
`PointCloudHub.process` observation acceptance, including viewport-throttled
samples, using `raw_context_snapshot()` and the original message/receipt.
Production PointCloudHub, worker, navigation/heading and command owners are
unchanged. The native probe has exactly one generated review input subscriber.

```python
adapter = AsyncRuntimeAdapter(
    runtime,  # CanonicalCorePorts; Runtime mode ADVISORY_ONLY only
    capture_provider=lookup_exact_capture,  # Capture keyed by original identity
    scene_factory=make_exclusive_empty_c1_v02_service,
    config=RuntimeConfig(mode="isolated_ros", domain_id=194),
    source_id="lidar",
)
adapter.start()  # owning asyncio loop
port = ReviewRosPort(runtime=adapter, identity_provider=None, owner_loop=loop)
# Existing ROS owner calls from_owner(...) with its accepted observation, then:
port.handoff(original_message, original_identity, pointcloud2)
# C1 router reads adapter.scene; it returns actual C1 snapshots.
```

Constructors perform no ROS I/O. Normalization/D2/D3/C4 run serially in the
worker thread; C1 whole-bundle commit occurs on the owner loop. Both captured
metadata and input transport are bounded. The owner transfers message ownership
without later mutation. Raw data is never reconstructed from a fused box.

`rebind(context,mapping)` must run on the owner loop and increase both runtime
and map generation for every map/source/TF/clock reset. C1 scene/source reset is
immediate; Runtime.rebind is serialized before the next worker call. Queued old
work is removed and running old results cannot commit or publish. `close()`
retires running work without permitting later scene/publication callbacks.

C1 service instances are exclusively adapter-owned with two written slots.
The adapter trials the complete candidate bundle against the actual same-limit
C1 service, including the previous bundle, before either live slot changes.
Rejected/oversized D2 or C1 output is never a partial successful new frame.
Snapshots retain original decimal ns and expiry; inactivity expires naturally.

`MarkingRosPublisher` creates a raw PointCloud2 publisher only on
`/robot_scope_review_x/c4/marking`, inside the checked network-none/domain-194
review node. It publishes accepted original sensor layout/stamp/frame. Its
configuration is marking=true, clearing=false. A native context stays bound to
the initial runtime key; a C1 generation change blocks native publication until
the host recreates the native session after independent reset evidence.

## Reproduce

```sh
export C4_ROS_DEP_ROOT=/tmp/c4-ros-deps
# First fetch exactly the four SHAs in dependencies.py (no branch checkout).
python -m experiments.expansion_20261029.c4_runtime.ros_bridge.dependencies
C4_ROS_REQUIRED=1 PYTHONPATH=tests:. python -m unittest expansion_runtime.async_cases -v
```

Use Node 24 (or set C4_NODE) for the current C3 check. The test starts actual
authenticated loopback uvicorn TCP HTTP and gives unchanged response bytes to
the actual current C3 parser/consumer. Missing pose/joints remain unavailable.
The 0.2 failure recorded for older C3 pins is historical, not waived here.

Local ROS and Docker are absent. The new C4-only
`.github/workflows/c4-ros-isolated.yml` provides the requested hosted execution;
the existing CI and D3 workflow are unchanged. It calls D3's exact read-only
image builder, checks Nav2 1.1.20, adds only C4 Python test dependencies in a new
image layer, then inspects a network-none container with no devices/secrets,
read-only sources, dropped capabilities, and a writable result directory.

`native_probe.py` launches the real NavFn planner/global costmap with a C4
transport overlay derived from D3's public config generator. Original D3 files
are read-only. Footprint, resolution, inflation, planner parameters and the
0.3 s expected update rate remain unchanged. The overlay changes ROS clock mode
to host time, review map/topic routing, and LaserScan to raw marking-only
PointCloud2; footprint clearing is explicitly off. Actual parameters are read
back before results count. Empty-route static map is a generated finite fixture;
it is not inferred sensor free-space or D3 CLEAR.

Evidence separately records ROS acceptance, actual cores, actual TCP HTTP,
occupied costmap cells, real ComputePathToPose path changes, sensor loss,
generation invalidation and rejected late original ROS inputs. Obstacle-return
removal and empty returns must retain cells: without original ray evidence,
clearing is NOT_PROVEN. New-generation publication is blocked until native reset.
No motion/navigation goal, controller or actuator is launched by this probe.

At D3 `356d0a...`, the existing five-case native controller/plant runner has no
public C4 owner-ingress injection hook. Its historical actuator PASS is not
relabelled C4 end-to-end PASS. C4 simulated actuator remains NOT_RUN; the next
D3 integration needs that explicit hook and independently observed native reset.
The C4 port supplies accepted original samples and rejects unsafe generation
reuse; it never implements a replacement plant, planner or controller.

Results, first failures and exact tested source SHA are recorded in C4's
`ROS_ADAPTER.md` after real hosted execution. DEVICE_NOT_RUN throughout.
