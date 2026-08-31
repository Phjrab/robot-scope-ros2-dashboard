# Fixed authenticated wireless IMU protocol

## Scope and ownership

This Gate 4 transport sends only the minimum Go2 body IMU sample. It does not
replicate ROS 2 DDS, serialize `LowState`, publish external `/lowstate`, forward
control data, start Mapping or grant a control lease.

| Host | Fixed address | Runtime ownership |
| --- | --- | --- |
| Go2-mounted Jetson | `192.168.50.30:46020` | subscribe to robot-local `/lowstate`, extract fixed IMU fields, authenticate and send |
| External Orin | `192.168.50.10:46020` | authenticate, validate freshness/order and publish `/imu/body` |

Both endpoints use a connected IPv4 UDP socket. The kernel therefore admits
only the configured peer address and port; there is no runtime network option,
wildcard listener, JSON field extension, route, NAT, bridge or generic proxy.
The full datagram is exactly 184 bytes.

## Canonical wire representation

All integer and IEEE-754 double fields use network byte order. The HMAC covers
every preceding byte.

| Offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 4 | magic `RSIM` |
| 4 | 1 | protocol version `1` |
| 5 | 1 | message type `1` (IMU) |
| 6 | 2 | flags; bit 0 means source tick is present |
| 8 | 16 | zero-padded sender ID `go2-body-imu` |
| 24 | 16 | Linux sender boot UUID |
| 40 | 8 | transport sequence |
| 48 | 8 | source realtime nanoseconds |
| 56 | 8 | source monotonic nanoseconds |
| 64 | 8 | optional source tick, otherwise canonical zero |
| 72 | 32 | quaternion W, X, Y, Z as four doubles |
| 104 | 24 | gyroscope X, Y, Z as three doubles |
| 128 | 24 | accelerometer X, Y, Z as three doubles |
| 152 | 32 | HMAC-SHA256 |

Unknown versions, message types, flags or sender IDs fail closed. Datagram
length is exact, so truncation and extension are rejected. HMAC comparison is
constant-time. Values must be finite; the quaternion norm must be within
`0.5..1.5` and is normalized before transmission and after validation.

The transport sequence starts from the sender's current monotonic nanoseconds,
then increments. This remains increasing across a process restart within one
Linux boot. A Linux reboot changes the boot UUID and allows the receiver to
reset sequence history. Up to four retired boot UUIDs are remembered; switching
back to one is rejected as replay.

## Authentication key

The sender and receiver each read the same 32-byte binary key from:

```text
/etc/robot-scope/wireless-imu.key
```

The file must be a regular non-symlink, owned by the runtime user, exactly mode
`0600` and exactly 32 bytes. It is a separate credential from the Control
Bridge key. It never appears in Git, environment variables, command lines,
health output, diagnostics or raw packet logs. Each host needs its own private
copy owned respectively by `unitree` or `jetson_orin_nano`.

## Clock, freshness and recovery contract

Source realtime is the ROS header timestamp and is never rebased to receive
time. Source monotonic is used only to prove forward progression within the
same sender boot; it is never compared numerically with the receiver's
monotonic clock.

Both runtimes fail closed unless the regular marker
`/run/systemd/timesync/synchronized` exists. Deployment must therefore verify
that the host's NTP implementation maintains that marker and must record actual
clock offset separately. A packet is rejected when it is older than 500 ms or
more than 100 ms in the future relative to synchronized receiver realtime.

Authentication, sequence, clock or transport failure immediately clears
readiness. After startup or recovery, five consecutive authenticated samples
with no receive gap over 250 ms are required. Health freshness expires after
250 ms. Wi-Fi or socket failure does not make the process invent samples,
reuse cached data, rebase timestamps or start Mapping/Nav; the same bounded
process can receive again, but readiness must be earned again.

## ROS contracts

Robot-side input is exactly one publisher on `/lowstate` with:

```text
BEST_EFFORT, VOLATILE, KEEP_LAST depth 1
```

Only quaternion, gyroscope, accelerometer and an integer source tick when
available are extracted. The sender does not publish any ROS topic.

External output is exactly `/imu/body`, message type `sensor_msgs/Imu`, frame
`body_imu`, with:

```text
RELIABLE, VOLATILE, KEEP_LAST depth 5
```

The external runtime has no `/lowstate` subscription or publisher. It publishes
only while it is the sole `/imu/body` publisher. A conflict clears the usable
publisher state rather than competing with a legacy IMU path.

Every five seconds the runtimes emit bounded aggregate health only. Receiver
health includes authenticated/ready state, sender boot UUID, sequence, packet
age, receive jitter, loss/duplicate/reorder, receive and authentication errors,
finite/quaternion failures, local clock synchronization and publisher state.
Payload values and credentials are never logged.

## Service and deployment boundary

The repository supplies disabled service examples and fixed runners:

- `robot-scope-wireless-imu-sender.service.example` runs as `unitree` on Foxy;
- `robot-scope-wireless-imu-receiver.service.example` runs as
  `jetson_orin_nano` on Humble.

They grant no Linux capability, apply a finite restart limit and restrict
address families. Gate 4 does not install, enable or start either service.
Installation remains gated by the separate exact approval phrase
`APPROVE_WIRELESS_XT16_DEPLOY`. Hardware status remains `NOT_RUN`; repository
tests do not claim `IMU_PASS`.
