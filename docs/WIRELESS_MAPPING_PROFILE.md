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

## Fixed ownership transaction

One explicit Mapping start owns this order:

1. robot-side `robot-scope-xt16-wireless-relay.service`
2. robot-side `robot-scope-wireless-imu-sender.service`
3. external authenticated IMU receiver
4. external Hesai driver using `config/hesai_xt16_wireless.yaml`
5. external C++ cloud-only bridge
6. external FAST-LIO through a separate `eno1=192.168.50.10/24` wrapper
7. the existing Mapping job state, after every readiness gate passes

Stop or failure cleans up in reverse order. A robot-side service that was
already active before this transaction is observed but not claimed and is not
stopped. Local children are tracked by PID plus Linux process start identity;
only this process group is signalled. There is no automatic retry after a
terminal failure and no Mapping, Nav2 or Mission restoration.

The launcher cannot create a control lease, ARM, publish a goal, start Nav2,
save a map or run Dataset Capture. The application coordinator also refuses a
Mapping start while a control lease or Dataset Capture is active. Physical
stationarity remains an operator-supervised hardware precondition and is not
inferred from stale ROS/DDS data.

## Preflight contract

The read-only preflight requires all of the following before FAST-LIO:

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
