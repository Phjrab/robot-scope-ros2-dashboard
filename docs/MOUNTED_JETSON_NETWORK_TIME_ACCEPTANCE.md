# Mounted Jetson network and time acceptance

Date: 2026-09-02

## Scope

This record covers only the persistent route and time prerequisite identified
after the blocked Track C4 attempt. No initial pose, navigation goal, manual
command, lease, ARM, deadman, mapping, FAST-LIO or Nav2 operation was executed.
No Wi-Fi credential is recorded in the repository.

The mounted Jetson must use its Wi-Fi interface for the default route while
retaining the directly attached Go2/XT16 sensor subnet on Ethernet. Existing
source-clock limits, including the 500 ms age and 100 ms future-skew guards,
were not changed.

## Change

The active NetworkManager connection with UUID
`58ed3933-c8a7-3c0c-9781-48eb09f33d6f` (`Wired connection 1`) was changed from
`ipv4.never-default=no` to `ipv4.never-default=yes`. Its manual address remains
`192.168.123.18/24`. The profile's obsolete gateway value is no longer
installed as a default route because the connection is explicitly
`never-default`.

Before reboot, the route table contained only:

- default via `192.168.50.1` on `wlan0`;
- `192.168.50.0/24` on `wlan0`;
- `192.168.123.0/24` on `eth0`, source `192.168.123.18`.

The XT16 endpoint at `192.168.123.20` responded on `eth0` with 0% packet loss.
The signed Go2 Control Bridge was independently observed with fresh LowState
and battery/joint telemetry; one guessed Go2 ICMP endpoint did not answer and
was not used as an acceptance criterion.

## Reboot proof

The mounted Jetson was rebooted after the Control Bridge, XT16 relay, wireless
IMU sender and wireless odometry sender were stopped. The boot ID changed from
`b8af13f6-417f-427b-a3a1-dd1172c46da0` to
`c5ba7507-83f1-4890-ba5c-52f96af3f56a`.

After reboot:

- Wi-Fi management SSH at `192.168.50.30` recovered through the external
  Jetson;
- the NetworkManager profile still reported `ipv4.never-default=yes`;
- the only default route was via `192.168.50.1` on `wlan0`;
- the direct `192.168.123.0/24` route on `eth0` remained present;
- the XT16 endpoint again responded on `eth0` with 0% packet loss;
- `systemd-timesyncd` was active and enabled, and `NTPSynchronized=yes`;
- the selected NTP peer was `1.pool.ntp.org`, with observed offset
  `+2.811 ms`, delay `8.946 ms` and jitter `2.676 ms`.

## Safety restoration

After verification, only the pre-existing production observation/control
baseline was restored: the signed Control Bridge and XT16 preview relay are
active; the wireless IMU sender and wireless odometry sender remain inactive.
The dashboard reports the Bridge authenticated and ready, fresh LowState,
publisher cardinality `1/0/10/11`, no active lease, deadman released, and exact
zero linear/angular command. Navigation, localization and goal state remain
idle.

## Acceptance table

| Gate | Result | Evidence |
| --- | --- | --- |
| Persistent Ethernet `never-default` | `PASS` | profile reports `ipv4.never-default=yes` after reboot |
| Wi-Fi management path | `PASS` | SSH at `192.168.50.30` recovered after reboot |
| Single default route | `PASS` | default is only via `192.168.50.1` on `wlan0` |
| Direct sensor subnet | `PASS` | `192.168.123.0/24` remains on `eth0` |
| XT16 direct reachability | `PASS` | `192.168.123.20`, 2/2 replies after reboot |
| NTP persistence | `PASS` | `systemd-timesyncd` active/enabled and synchronized after reboot |
| No robot motion authority | `PASS` | no lease, deadman false, exact zero; no goal or motion issued |
| Production safety restoration | `PASS` | Bridge/preview restored; IMU, odometry and Nav2 remain inactive |

## Repository verification

- dependency-complete project Python suite: 993/993 passed;
- required host-Python suite: 989 tests ran with the existing single import
  error because the macOS host interpreter lacks declared `fastapi`;
- JavaScript unit suite: 270/270 passed;
- frontend syntax: 53/53 modules passed;
- tracked-source secret scan and `git diff --check`: passed.

An initial parallel host/project Python run also exposed a shared temporary
path collision in `test_saved_maps`; the required host suite was rerun alone
and that collision did not reproduce. Its sole remaining error was the known
missing-`fastapi` baseline above.

## Remaining boundary

This closes only the persistent network/NTP prerequisite. It does not resolve
the separate Track C4 controller-odometry frequency margin that oscillated
around the strict 10.0 Hz readiness threshold. That investigation requires a
separate task and must not weaken the existing threshold or synthesize
odometry. A fresh exact C4 route approval is still required before any future
goal attempt.
