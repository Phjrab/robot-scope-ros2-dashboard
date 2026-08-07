# Troubleshooting log

## 1. `192.168.123.20` ping이 간헐적이거나 끊김

Jetson의 실제 연결 포트를 먼저 확인한다.

```bash
ip -br link
ip -br addr
```

이번 구성에서는 USB 이더넷이 아니라 Jetson 내장 포트 `eno1`이 Go2/XT16에 연결돼 있었다.
임시 명령 `ip addr add`는 NetworkManager가 제거할 수 있으므로 `eno1`의 연결 프로필을 manual로 고정했다.

```bash
sudo nmcli connection modify "Wired connection 1" \
  ipv4.method manual \
  ipv4.addresses 192.168.123.99/24 \
  ipv4.gateway "" \
  ipv4.dns "" \
  ipv4.never-default yes \
  connection.autoconnect yes
sudo nmcli connection up "Wired connection 1"
```

검증:

```bash
ping -c 4 192.168.123.20
ip -br addr show eno1
nmcli -g GENERAL.STATE device show eno1
```

## 2. Hesai 드라이버가 `invalid delimiter`를 반복

이 오류만 보고 드라이버 포맷 문제로 판단하면 안 된다. 우선 실제 UDP 2368 패킷이 도착하는지 확인한다.

```bash
sudo tcpdump -nn -i eno1 -c 5 -q 'src host 192.168.123.20 and udp port 2368'
```

정상 패킷 예시:

```text
192.168.123.20.10000 > 192.168.123.99.2368: UDP, length 568
```

문제 상태에서는 2368 패킷이 0개이고, Go2 DDS multicast(`239.255.0.1:7401`)만 보였다. XT16의 point cloud destination이 Jetson이 아닌 다른 장치로 설정된 상태였다.

## 3. XT16 웹 UI가 빈 화면이거나 로딩 실패

공식 경로는 `http://192.168.123.20/index.html`이다. 그래도 HTTP 서비스가 응답하지 않으면 PTC 포트 9347을 사용해 목적지를 직접 설정할 수 있다.

공식 Hesai SDK의 `tool_ptc/ptc_tool.cc`에서 다음을 설정해 빌드한다.

```cpp
#define SET_DES_IP_AND_PORT
// #define DEFINE_YOURSELF
std::string destination_ip = "192.168.123.99";
uint16_t udp_port = 2368;
```

그 다음 실행한다.

```bash
./ptc_tool 192.168.123.20 9347
```

성공 기준:

```text
SetDesIpandPort succeeded
```

## 4. Livox-SDK2가 필요한가?

필요하지만 XT16 수신 문제의 원인은 아니다.

- Hesai driver: XT16 UDP를 `/lidar_points`로 변환
- Livox-SDK2 + livox_ros_driver2: FAST-LIO가 참조하는 메시지 타입의 빌드 의존성

## 5. Bridge에서 IMU가 4 Hz로 떨어짐

원본 `/lowstate`는 약 500 Hz였다. 병목은 64,000점 PointCloud2를 Python callback 하나에서 매 프레임 재패킹하면서 IMU callback이 기다린 것이었다.

해결:

1. `MultiThreadedExecutor(num_threads=2)` 사용
2. cloud callback은 `MutuallyExclusiveCallbackGroup`으로 한 프레임만 처리
3. IMU callback은 별도 `ReentrantCallbackGroup`
4. XT16 점구름을 bridge에서 1/4 샘플링하고 FAST-LIO의 `point_filter_num`은 `1`로 변경

수정 patch는 [xt16_fastlio_bridge.patch](../patches/xt16_fastlio_bridge.patch)에 있다.

## 6. FAST-LIO 시작 직후 `No point, skip this scan!`

초기 IMU/point-cloud 버퍼가 차기 전에는 일시적으로 발생한다. 이후 다음 로그가 나오고 `/Odometry`가 발행되면 정상이다.

```text
IMU Initial Done
Initialize the map kdtree
```

```bash
ros2 topic hz /Odometry
```

## 체크리스트

```bash
# XT16 raw input
ros2 topic hz /lidar_points
ros2 topic echo /lidar_points --field width --once

# FAST-LIO bridge output
ros2 topic hz /velodyne_points
ros2 topic hz /imu/body

# FAST-LIO output
ros2 topic hz /Odometry
ros2 topic list | grep -E 'Laser_map|Odometry'
```
