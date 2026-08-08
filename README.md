# Go2 + XT16 + FAST-LIO on ROS 2 Humble

Jetson Orin Nano에서 Unitree Go2, Hesai PandarXT-16(XT16), FAST-LIO를 연결해
실시간 3D 맵을 만들고 PCD로 저장한 실습 기록입니다.

## 검증된 결과

- XT16 raw cloud: `/lidar_points`, 약 10 Hz, 프레임당 64,000점
- Bridge output: `/velodyne_points`, 약 8-9 Hz, 프레임당 16,000점
- Go2 body IMU: `/imu/body`, 약 60-70 Hz
- FAST-LIO: `/Odometry`, 약 9 Hz; `/Laser_map` 및 RViz `CloudMap` 표시
- Saved map: binary PCD

## 구성

```text
XT16 (192.168.123.20)
  └─ UDP 2368 → Jetson eno1 (192.168.123.99)
       └─ hesai_ros_driver → /lidar_points
Go2 /lowstate
  └─ xt16_fastlio_bridge.py → /velodyne_points + /imu/body
       └─ FAST-LIO → /Laser_map + /Odometry
```

## 워크스페이스

```text
~/ws/hesai_ws       HesaiLidar_ROS_2.0
~/ws/livox          Livox-SDK2 + livox_ros_driver2 (FAST-LIO 빌드 의존성)
~/ws/fastlio_ws     FAST_LIO (ros2 branch)
~/ws/go2_3d         bridge, launch helper, map saver
```

## 빠른 시작

1. XT16 이더넷이 Jetson `eno1`에 연결됐는지 확인합니다.
2. 영구 IP 설정을 한 번 적용합니다.

```bash
sudo ./scripts/setup_eno1_static_ip.sh
```

3. XT16이 아직 점구름을 보내지 않는 경우 PTC로 목적지를 설정합니다.

```bash
./scripts/set_xt16_destination.sh
```

4. 별도 터미널에서 아래 순서로 실행합니다.

```bash
# 1) Hesai driver
source /opt/ros/humble/setup.bash
source ~/ws/hesai_ws/install/setup.bash
ros2 run hesai_ros_driver hesai_ros_driver_node

# 2) Go2 + XT16 bridge
source ~/setup_go2_ros2_humble.sh
python3 ~/ws/go2_3d/xt16_fastlio_bridge.py

# 3) FAST-LIO + RViz
~/ws/go2_3d/run_slam_humble.sh
```

5. 맵핑 중 새 터미널에서 저장합니다.

```bash
source /opt/ros/humble/setup.bash
source ~/ws/livox/ws_livox/install/setup.bash
source ~/ws/fastlio_ws/install/setup.bash
python3 ~/ws/go2_3d/save_map.py
```

생성물은 `~/ws/go2_3d/maps/map_YYYYMMDD_HHMMSS.pcd`입니다.

## 핵심 트러블슈팅

- `eno1`의 IP가 사라지면 NetworkManager 프로필을 manual IP로 고정해야 합니다.
- ping은 되지만 `/lidar_points`가 없으면 XT16이 다른 destination IP로 송출 중일 수 있습니다.
- PTC 설정 도구의 `SetDesIpandPort`로 `192.168.123.99:2368`을 지정합니다.
- `Livox-SDK2`는 Hesai 수신 드라이버가 아니라 FAST-LIO의 메시지 빌드 의존성입니다.
- 브리지에서 64,000점을 매 프레임 Python으로 재패킹하면 IMU가 굶습니다. 이 저장소의 patch처럼 점구름과 IMU callback을 분리하고 1/4 선행 샘플링합니다.

자세한 원인과 검증 명령은 [troubleshooting.md](docs/troubleshooting.md)를 참고하세요.

## Robot Scope 웹 대시보드

이번 실습에서 만든 범용 ROS 2 관측 대시보드는
[`robot-scope/`](robot-scope/)에 있습니다. Jetson에서 에이전트를 실행하면
브라우저에서 센서·카메라·odometry·2D 지도와 RViz형 3D LiDAR/Go2 장면을
확인할 수 있습니다. 로봇 전원이 꺼진 환경에서는 저장된 로컬 PCD 또는 공개용
데모 점군으로 3D UI를 계속 테스트할 수 있습니다.

`Live Mapping` 메뉴에서는 허용된 Hesai+FAST-LIO 세션을 새로 시작하고, 최신
`/Laser_map`을 검증된 binary PCD와 선택적 2D PGM+YAML로 저장할 수 있습니다.
공식 Go2 모델은 `/joint_states` 또는 `/lowstate`의 12축 관절과 몸통 기울기를
WebSocket으로 받아 실제 로봇 움직임을 반영합니다. 로봇 구동 명령과 임의 shell
명령은 대시보드에서 실행할 수 없습니다.

## 안전

- 제자리 급회전과 빠른 주행은 맵을 왜곡할 수 있습니다. 큰 원을 그리듯 천천히 움직입니다.
- `/Laser_map` 저장은 FAST-LIO를 끄기 전에 수행합니다.
- 이 저장소에는 비밀번호, SSH 키, 개인 토큰을 포함하지 않습니다.
