# Wireless XT16 mapping profile

## Scope and selection

`go2-xt16-wireless` is an explicit Robot Scope mapping mode for the measured
robot-side `192.168.50.30` to external `192.168.50.10` topology. The default
remains `go2-xt16-wired`. Selecting the wireless mode never modifies an
interface, route, firewall, service enablement, map, navigation state or
control state:

```text
ROBOT_SCOPE_MAPPING_PROFILE=go2-xt16-wireless
```

The existing wired launcher, preview owner, `.123.99/24` preflight and Hesai
profile remain separate. The wireless launcher never sources or bypasses that
wired network setup.

Navigation is a separate consumer of this profile. Its fixed launcher sources
the same external wireless ROS environment and additionally owns the
purpose-specific authenticated controller-odometry transport documented in
`ADR_WIRELESS_CONTROLLER_ODOMETRY_TRANSPORT.md`. Mapping alone does not start
or require that transport, and the wired Navigation profile still uses the
dedicated Go2 helper unchanged.

## Fixed preview and mapping ownership

The dashboard starts one observation-only preview after its ROS agent is ready:

1. robot-side `robot-scope-xt16-wireless-relay.service`;
2. external Hesai driver using `config/hesai_xt16_wireless.yaml`;
3. external C++ cloud-only bridge publishing `/velodyne_points`.

For the two fixed wireless Mapping profiles this preview relies on its own
management-interface, firewall, relay and cloud readiness gates; it does not
require the external host to own the direct `192.168.123.99/24` Go2 DDS
interface. Wired profiles retain that direct-interface startup requirement.

That preview contains no IMU receiver, FAST-LIO, map accumulation, save, Nav2,
control lease or motion authority. It lets Cockpit display fresh XT16 points
before Mapping starts and remains running after Mapping stops. Dashboard
shutdown stops only the preview-owned processes and a relay service that the
preview itself started; service enablement is never changed.

Preview readiness therefore checks only fresh converted `/velodyne_points`.
The Mapping transaction rechecks that cloud, then starts and verifies the
authenticated `/imu/body` path before FAST-LIO starts. Both inputs remain
mandatory, so the preview-only gate cannot make an IMU-less Mapping session
ready.

One explicit Mapping start reuses the ready preview and adds this order:

1. robot-side `robot-scope-wireless-imu-sender.service`;
2. external authenticated IMU receiver;
3. external FAST-LIO through the fixed `eno1=192.168.50.10/24` wrapper;
4. the existing Mapping job state, after every readiness gate passes.

The relay service identity is verified immediately after start. Its advancing
counter and non-increasing send-error health gate is evaluated only after the
fixed Hesai UDP 2368 consumer has bound and produced fresh raw clouds. This
preserves the startup order while preventing expected pre-bind ICMP
port-unreachable errors from making the profile permanently fail closed. No
cloud or FAST-LIO readiness can pass before the post-bind relay health gate.

Mapping stop or failure cleans up FAST-LIO and the mapping-owned IMU path in
reverse order without stopping the point-cloud preview. Preview failure while
Mapping is active fails the Mapping group closed. A robot-side service that was
already active before either transaction is observed but not claimed and is
not stopped. Local children are tracked by PID plus Linux process start
identity; each runner is placed in its own session and only that owned process
group is signalled. This includes a `ros2 run` wrapper and the native ROS node
it starts, so cleanup cannot leave an orphaned child. There is no automatic
retry after a terminal failure and no Mapping, Nav2 or Mission restoration.

The launcher cannot create a control lease, ARM, publish a goal, start Nav2,
save a map or run Dataset Capture. The application coordinator also refuses a
Mapping start while a control lease or Dataset Capture is active. Physical
stationarity remains an operator-supervised hardware precondition and is not
inferred from stale ROS/DDS data.

## Preflight contract

The preview preflight requires the fixed host, relay, raw-cloud and converted-
cloud gates. The explicit Mapping preflight rechecks those live inputs, then
requires the IMU and FAST-LIO gates. Across both transactions the following
remain mandatory:

- the fixed root-owned wireless firewall unit is active/exited with a
  successful main result; the dashboard receives no firewall authority;
- `eno1` owns exactly `192.168.50.10/24` and `192.168.50.30` responds;
- both hosts report synchronized clocks;
- `net.core.rmem_max` is at least 8 MiB;
- no same-user Hesai, wireless IMU, cloud bridge, FAST-LIO, Nav2 or bag-record
  process conflicts with the transaction;
- the restricted robot-side relay lifecycle reports active/running;
- two bounded relay health reports show both accepted and forwarded counters
  advancing without send-error growth;
- the restricted IMU sender lifecycle reports active/running;
- five fresh, increasing, reliable/volatile `/imu/body` samples from exactly
  one publisher pass the existing absolute timestamp and frame checks;
- the fixed private PandarXT CSV correction manifest passes owner/group, mode,
  revision, model, path, bounded measured length, strict 16-channel structure
  and SHA-256 validation before the Hesai driver is invoked; the proven
  baseline leaves its optional firetime path empty;
- five fresh raw clouds, then five converted clouds, pass their existing frame,
  layout, point-count, publisher, rate, timestamp and QoS gates;
- fresh FAST-LIO odometry and a non-empty laser map pass readiness.

The SSH identity and known-hosts files are absolute, regular, owned by the
dashboard user and mode `0600`. Their environment names are
`ROBOT_SCOPE_WIRELESS_MAPPING_SSH_IDENTITY` and
`ROBOT_SCOPE_WIRELESS_MAPPING_SSH_KNOWN_HOSTS`. Strict host-key checking and a
forced command are mandatory. The forced command accepts only fixed relay/IMU
start, stop, status, relay journal health and clock-status operations. Its
sudoers entry
contains only the four exact service start/stop commands; restart, enable,
disable, arbitrary unit names and shell execution are absent.

## Bounded dashboard reasons

Exit status is translated through a fixed server allowlist, so child output,
paths and commands never become the Mapping error message:

- `WIRELESS XT16 RELAY OFFLINE`
- `XT16 PACKETS STALE`
- `HESAI DRIVER WAITING`
- `WIRELESS IMU UNAUTHENTICATED`
- `IMU STALE`
- `CLOCK NOT SYNCHRONIZED`
- `CLOUD BRIDGE STALE`
- `FAST-LIO NOT READY`
- `WIRELESS MAPPING PREFLIGHT BLOCKED`

## Deployment boundary

Gate 6 adds repository artifacts only. Nothing in this gate installs the
forced command, sudoers rule, SSH key, services, sysctl, ROS executable or
profile on either Jetson. Nothing starts Mapping or touches a map. Deployment
remains blocked until Gate 7 creates the reviewed deployment plan and the
operator supplies the exact approval phrase `APPROVE_WIRELESS_XT16_DEPLOY`.
Stationary FAST-LIO remains separately blocked on
`APPROVE_STATIONARY_MAPPING_TEST` and physical remote/E-stop readiness.
