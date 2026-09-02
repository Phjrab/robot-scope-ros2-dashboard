# Wireless dashboard gateway connection

Status date: 2026-09-02

## Fixed topology

The wireless Go2 dashboard does not pretend that the external Orin has a
direct route to the Go2 body or XT16 sensor LAN.

```text
operator browser
  -> external Orin 192.168.50.10 (Robot Scope dashboard)
  -> onboard Jetson 192.168.50.30 (management gateway)
  -> onboard eth0 192.168.123.18/24
  -> Go2 192.168.123.161 and XT16 192.168.123.20
```

For `go2-xt16-wireless` and
`go2-xt16-wireless-competition-fastlio`, the dashboard target is the onboard
Jetson management address. The external Orin binds its ROS 2 participant to
the management interface and no longer reports the missing direct Go2 NIC as
the primary connection failure. The wired and `competition-pdf-direct`
profiles retain their existing direct-interface contract.

## Connect operation

The Settings connection button performs two bounded actions for the matching
wireless startup target:

1. select and validate the onboard Jetson address on a directly attached
   private LAN;
2. request the existing restricted Control Bridge lifecycle start.

The second action retains all existing server preflight checks. It starts only
the fixed service and must settle in authenticated `DISARMED`, exact-zero,
deadman-released and no-lease state. The connect operation does not ARM, issue
a robot action, acquire a lease, publish a navigation goal or start mapping.
If the lifecycle preflight blocks the service, the mounted Jetson selection is
still visible and Go2 Bridge remains explicitly blocked/offline.

## Operator-driven mapping

Mapping remains an explicit action on the Mapping page. `새 맵 시작` invokes
the already allowlisted wireless mapping launcher. That launcher starts the
restricted onboard XT16 relay and IMU sender, then the external Hesai driver,
cloud bridge and FAST-LIO in transactional order. Stop performs reverse
cleanup. Map save remains a separate explicit action and no map is deleted by
connection or dashboard startup.

For clean release directories, the Git-ignored C++ bridge may be read from the
fixed absolute `ROBOT_SCOPE_DEPENDENCY_WORKSPACE_ROOT`. The path cannot be `/`
or relative. It does not change the generated-map directory or permit a
request-provided executable.

## Deferred work

Track C3 initial-pose publication and localized NG1 remain deferred until the
operator creates, saves and identifies the replacement map. No prior map is
selected automatically.
