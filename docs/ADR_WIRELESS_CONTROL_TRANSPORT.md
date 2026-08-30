# ADR — Authenticated wireless Control Bridge transport

- Status: accepted for implementation; hardware acceptance pending
- Date: 2026-08-30
- Scope: Go2 manual/autonomous command boundary and Control Bridge lifecycle

## Context

The competition topology places Robot Scope on the external Orin at
`192.168.50.10` and the moving robot-side Jetson at `192.168.50.30`. The
robot-side Jetson alone owns the dedicated Go2 Ethernet address
`192.168.123.18`; the Go2 body remains `192.168.123.161`. The external Orin no
longer has the previously accepted `192.168.123.99` interface.

CycloneDDS discovery on the Go2 LAN and live LowState were verified on the
robot-side Jetson. They do not cross the management Wi-Fi, and routing or NAT
does not safely reproduce multicast discovery or the existing graph
cardinality contract. Moving arbitrary DDS to the management LAN would also
expose unrelated robot topics and couple large sensor traffic to control.

## Decision

Run the existing standalone `Go2ControlBridge` on the robot-side Jetson under
ROS 2 Foxy, bound only to `eth0`. Keep the dashboard `ControlManager` on the
external Orin. Carry only the existing HMAC-signed control command and bridge
status envelopes across one connected UDP socket:

~~~text
External Orin 192.168.50.10:46010
  signed command  ------------------------------>
  <------------------------------- signed status
Robot-side Jetson 192.168.50.30:46010
  Go2ControlBridge -- CycloneDDS eth0 --> Go2 192.168.123.161
~~~

Both endpoints bind an explicit RFC1918 or link-local IPv4 address and connect
the UDP socket to the exact peer on repository-owned port `46010`. A connected
socket lets the kernel discard packets from other source addresses or ports.
The datagram layer accepts only non-empty UTF-8 payloads up to the existing
8,192-byte signed-protocol limit. It does not decode, alter, discover, or relay
ROS topics.

The payload retains all existing safety checks:

- minimum 32-byte shared key and SHA-256 HMAC
- issued timestamp and bounded transport age
- bridge epoch and strictly increasing command sequence
- fixed command/action schema and action allowlist
- independent 200 ms Bridge command watchdog
- fresh LowState requirement
- exact LowState and sport graph cardinality
- one lease, deadman, server-side velocity clamps, and latched software stop
- three StopMove requests during Bridge shutdown

The Foxy compatibility branch changes only `rclpy` signal initialization. It
still overrides the installed signal handlers before spinning so the ROS
context remains valid for the shutdown StopMove sequence.

## Lifecycle decision

The Controls-page lifecycle continues to expose only the fixed
`robot-scope-control-bridge.service` identity and `start`/`stop` actions. In
wireless mode its backend reads and mutates the robot-side unit through one
dedicated SSH key with strict host-key checking.

The corresponding robot-side `authorized_keys` entry must use `restrict` and a
root-owned forced-command helper. The helper accepts only the literal words
`status`, `start`, and `stop`. `status` reads five fixed public systemd fields;
the two mutations use a sudoers rule that permits only:

~~~text
/usr/bin/systemctl --no-block start robot-scope-control-bridge.service
/usr/bin/systemctl --no-block stop robot-scope-control-bridge.service
~~~

The browser cannot provide a host, user, key path, service name, command,
argument, shell fragment, URL, or force flag. All host and key paths are
private service environment values validated at process startup.

## Failure behavior

| Failure | Required behavior |
|---|---|
| Wi-Fi or UDP loss | command stream expires; Bridge publishes StopMove and status becomes stale |
| forged/tampered packet | HMAC rejection; readiness revoked or Bridge forced to stop |
| replay/old packet | timestamp, epoch, or sequence rejection; Bridge forced to stop |
| LowState loss | Bridge readiness false and StopMove |
| dashboard exit | final signed stop before its UDP socket closes |
| robot-side Bridge exit | three StopMove publishes before ROS shutdown |
| lifecycle SSH loss | status unknown; no new mutation; stop remains retryable after link recovery |
| wrong/missing key or host path | transport/lifecycle remains unconfigured |
| unexpected sport publisher/subscriber | Bridge readiness false and no Move request |

No reconnect path automatically creates a lease, arms control, holds deadman,
replays an action, or resumes navigation.

## Rejected alternatives

- Layer-2 Wi-Fi bridge, NAT, multicast forwarder, or generic DDS Router: too
  broad and does not preserve the reviewed topic/cardinality boundary.
- Arbitrary ROS topic relay: exposes an extensible command surface.
- Move the full dashboard/Nav2 stack to the Ubuntu 20.04 relay host: duplicates
  product ownership and resource load on the moving robot.
- Unauthenticated HTTP lifecycle endpoint: adds a public mutation surface.
- Reimplement the Go2 safety core: unnecessary divergence from the previously
  accepted watchdog and signed protocol.

## Configuration

External dashboard private environment:

~~~text
ROBOT_SCOPE_CONTROL_TRANSPORT=udp
ROBOT_SCOPE_CONTROL_DATAGRAM_BIND_HOST=192.168.50.10
ROBOT_SCOPE_CONTROL_DATAGRAM_PEER_HOST=192.168.50.30
ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_TRANSPORT=ssh
ROBOT_SCOPE_CONTROL_BRIDGE_REMOTE_USER=unitree
ROBOT_SCOPE_CONTROL_BRIDGE_SSH_IDENTITY=/absolute/private/key/path
ROBOT_SCOPE_CONTROL_BRIDGE_SSH_KNOWN_HOSTS=/absolute/private/known_hosts/path
~~~

Robot-side private environment is based on
`deploy/robot-scope-control-bridge-robot-side.env.example` and receives the
same Bridge shared key without logging or committing it.

## Hardware acceptance gate

Software tests do not authorize motion. With the robot stationary and the
operator present, acceptance must confirm:

1. remote unit initially disabled and inactive;
2. dashboard transport configured, DISARMED, no lease, released deadman, and
   zero command;
3. dashboard START reaches the robot-side unit and authenticated status;
4. Bridge reports fresh LowState and exact graph cardinality;
5. no Move or action is emitted during the no-motion test;
6. dashboard STOP reaches `inactive/dead` and signed status disappears;
7. later supervised fault tests cover UDP interruption and process loss;
8. any later motion test starts with the lowest limits and physical stop means.

Until steps 1–6 pass, the wireless Control Bridge remains hardware BLOCKED.
