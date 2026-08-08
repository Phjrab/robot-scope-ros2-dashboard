# Robot Scope

Robot Scope는 ROS 2 로봇의 연결 상태, 센서 값, 카메라 스트림, 위치 추정과
LiDAR 맵을 브라우저에서 확인하는 읽기 전용 대시보드입니다.

현재 버전은 Unitree Go2 + ROS 2 Humble + Jetson Orin Nano 환경을 기본
프로필로 제공하지만, 표준 ROS 2 메시지 타입을 기준으로 토픽을 자동 분류하므로
다른 로봇에도 같은 에이전트를 설치해 사용할 수 있습니다.

## 구조

```text
Robot sensors / ROS 2 DDS
          │
          ▼
Robot Scope agent (각 로봇의 Jetson)
  ├─ ROS graph 및 publisher 자동 탐색
  ├─ 센서 메시지 요약
  ├─ H.264/JPEG/raw 카메라 게이트웨이
  ├─ PointCloud2 다운샘플링
  └─ OccupancyGrid / Odometry 상태
          │ HTTP + WebSocket
          ▼
       Web browser
```

중요: ROS 2 DDS는 일반적인 TCP 서버처럼 로봇 IP 하나만 입력해 접속하는 방식이
아닙니다. 범용 사용 시에는 센서가 연결된 각 Jetson에서 이 에이전트를 실행하고,
브라우저가 `http://JETSON_IP:8088`에 접속합니다. 화면의 `로봇 IP`는 로봇
제어기의 네트워크 생존 여부를 확인하는 대상입니다.

## 현재 지원

- ROS graph와 토픽 타입, publisher 수 자동 탐색
- 토픽 수신률, 지터, 마지막 수신 시간, stale 상태
- `sensor_msgs`: Image, CompressedImage, PointCloud2, LaserScan, Imu,
  BatteryState, JointState, NavSatFix, Range
- `nav_msgs`: Odometry, OccupancyGrid
- Unitree Go2: LowState, SportModeState, LidarState, Go2FrontVideoData
- Go2 H.264 전면 영상의 GStreamer→JPEG 변환과 브라우저 WebCodecs 대체 경로
- RViz처럼 회전·이동·확대할 수 있는 3D PointCloud 장면
- URDF 비율을 반영한 경량 Go2 3D 모델, yaw 방향과 최근 이동 궤적 표시
- 실시간 LiDAR와 저장된 PCD 스냅샷, 2D OccupancyGrid 레이어 전환
- Hesai `/lidar_points` publisher를 `XT16 ONLINE`으로 표시
- 로봇 IP ping, ROS 배포판·Domain·RMW 표시
- 토픽별 소스 변경

대시보드는 의도적으로 읽기 전용입니다. 로봇 제어, 임의 명령 실행, launch 시작·
종료 기능은 포함하지 않습니다.

## Jetson 설치

```bash
cd ~/robot-scope
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
chmod +x scripts/run_go2_humble.sh
./scripts/run_go2_humble.sh
```

브라우저에서 다음 주소를 엽니다.

```text
http://JETSON_IP:8088
```

현재 실습 Jetson에서는 `http://10.100.0.89:8088`입니다.

Go2 H.264 영상 변환에는 Jetson 호스트의 GStreamer가 필요합니다.

```bash
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-libav
```

## Go2 기본 연결

`scripts/run_go2_humble.sh`는 다음을 자동으로 적용합니다.

1. `/opt/ros/humble/setup.bash`
2. Unitree 메시지 workspace overlay
3. `~/setup_go2_ros2_humble.sh`의 Cyclone DDS 및 `eno1` 설정
4. Go2 제어기 `192.168.123.161` 연결 확인

기본 자동 선택 우선순위는 `config/go2.json`에서 변경할 수 있습니다.

| 역할 | 기본 선택 |
|---|---|
| 카메라 | 자동 구독 끔; 필요 시 `/frontvideostream` 선택 |
| 3D 점군 | `/velodyne_points` (XT16 브리지 출력) |
| 누적 3D 지도 | 필요 시 `/Laser_map` 선택 |
| 위치 추정 | `/Odometry` |
| 2D 맵 | `/map` |

FAST-LIO와 XT16을 실행하면 `/lidar_points`, `/Odometry`, `/Laser_map`, `/map`도
소스 선택 목록에 자동으로 나타납니다.

현재 실습 장비의 Hesai→FAST-LIO→지도 파이프라인은 한 번에 시작할 수 있습니다.

```bash
cd ~/robot-scope
./scripts/start_hesai_mapping_humble.sh
```

| 역할 | 토픽 | 이번 검증값 |
|---|---|---|
| Hesai XT16 원본 | `/lidar_points` | 약 10 Hz, 64,000 points/frame |
| FAST-LIO 입력 | `/velodyne_points`, `/imu/body` | 약 8–10 Hz / 60 Hz 이상 |
| 누적 3D 지도 | `/Laser_map` | 약 1 Hz |
| 지도 기준 자세 | `/Odometry` | 약 10 Hz, frame `camera_init` |
| 저장된 2D 지도 | `/map` | 971×677, 0.05 m/cell |

화면에서 `LiDAR / 3D 맵`을 `/lidar_points`로 선택하면 XT16 원본 스캔을,
`/Laser_map`으로 선택하면 누적 지도를 볼 수 있습니다. 지도 패널의 `LAYER`는
`3D SCENE`, `2D MAP`, `AUTO` 중에서 고릅니다. 3D 장면은 드래그로 회전,
Shift/오른쪽 드래그로 이동, 휠로 확대하며 `ISO`, `TOP`, `FRONT` 버튼으로
시점을 즉시 바꿀 수 있습니다. `ROBOT`을 끄면 로봇 모델과 궤적을 숨깁니다.

로봇이나 LiDAR 전원이 꺼져 있으면 로컬의
`robot_dashboard/static/data/go2_saved_map.json`에 저장한 마지막 PCD를 자동으로
표시합니다. 이 파일이 없는 공개 저장소 환경에서는 실제 공간 정보가 없는 데모 맵을
브라우저에서 생성합니다. 따라서 장비가 꺼진 상태에서도 모델과 LiDAR 지도를 조작하고
UI를 점검할 수 있습니다. 로봇이 다시 연결되고 정상 점군이 들어오면 실시간 장면으로
자동 전환합니다. 새 PCD 스냅샷은 다음처럼 만들 수 있습니다.

```bash
python3 scripts/pcd_to_scene.py /path/to/map.pcd \
  robot_dashboard/static/data/go2_saved_map.json --max-points 10000
```

좌표계가 같은 `/Laser_map`(`camera_init`)과 `/Odometry`는 로봇을 지도 절대
좌표에 표시합니다. 저장된 `/map`의 `map` frame과 현재 odometry frame 사이에
TF가 없으면 잘못된 좌표를 쓰지 않고 `FRAME RELATIVE`로 중앙에 표시합니다.

현재 Go2 기본 선택인 `/velodyne_points`는 XT16 브리지가 재발행한 안정적인 순간
점군입니다. 누적된 SLAM 지도를 보려면 SLAM 노드를 먼저 실행한 뒤 `/Laser_map`
또는 `/map`을 선택해야 합니다. 점군과 odometry가 모두 살아 있을 때 표시되는
`MAPPING` 배지는 두 입력의 수신 상태를 뜻하며, SLAM 품질을 판정한다는 뜻은
아닙니다.

Go2 프로필은 지도 처리 성능을 보호하기 위해 카메라를 자동 구독하지 않고,
`observed_topics`에 지정된 IMU·LiDAR 상태만 상시 요약합니다. `/lowstate`는 약
350–500 Hz라 Python 대시보드가 한 CPU 코어를 사용할 수 있습니다. 배터리와
모터 값을 계속 표시해야 할 때만 `config/go2.json`의 `observed_topics`에
`/lowstate`를 추가하세요.

### 이번 장비에서 확인한 트러블슈팅

- Hesai 원본 `/lidar_points`를 여러 Python 구독자가 직접 받으면 CycloneDDS가
  간헐적으로 `sequence size exceeds remaining buffer`를 기록했습니다. 대시보드
  기본값은 FAST-LIO가 실제로 사용하는 안정적인 브리지 출력
  `/velodyne_points`입니다.
- `/frontvideostream`을 고대역폭 지도 토픽과 함께 상시 디코딩하면 대시보드의
  CPU·메모리가 급증했습니다. Go2 프로필에서는 카메라 자동 구독을 끄고 지도와
  센서를 우선합니다.
- `/Laser_map`은 계속 커지는 누적 지도입니다. 에이전트는 전체 배열을 복사하지
  않고 원본 버퍼에서 먼저 샘플링해 브라우저 전송을 10,000점 이하로 제한합니다.
- 로봇 전원을 끄는 순간 FAST-LIO 점군에 비정상적으로 큰 좌표가 섞일 수 있습니다.
  에이전트와 3D 렌더러가 각각 중앙값 기준 공간 이상치를 제거하므로 장면 전체가
  한 점처럼 축소되는 현상을 막습니다.
- Nav2 정적 `/map`은 `TRANSIENT_LOCAL`로 한 번만 발행될 수 있습니다. 수신 뒤
  Hz가 없어도 `2D MAP READY`이면 정상입니다.

## 다른 ROS 2 로봇에서 사용

표준 ROS 2 로봇은 `config/generic.json`과 `scripts/run_generic.sh`를 사용합니다.

```bash
export ROS_DISTRO=humble
export ROBOT_SCOPE_ROBOT_IP=192.168.1.20
# 사용자 workspace가 있으면 선택 사항
export ROBOT_SCOPE_OVERLAY="$HOME/ros2_ws/install/setup.bash"
./scripts/run_generic.sh
```

에이전트는 `sensor_msgs`와 `nav_msgs` 타입을 기준으로 카메라, 점군, IMU,
배터리, 관절, GPS, 거리 센서, odometry와 occupancy grid를 자동 분류합니다.
표시할 토픽은 대시보드의 `DATA SOURCES`에서 바꿀 수 있습니다.

재부팅 뒤에도 자동 실행하려면 `deploy/robot-scope.service.example`의 사용자명과
경로를 확인한 다음 systemd 서비스로 등록할 수 있습니다.

```bash
sudo cp deploy/robot-scope.service.example /etc/systemd/system/robot-scope.service
sudo systemctl daemon-reload
sudo systemctl enable --now robot-scope
```

## RealSense가 로봇 탑재 Jetson에 있는 경우

RealSense가 외부 Jetson이 아닌 로봇 탑재 Jetson USB에 연결되어 있다면, 탑재
Jetson에서 `realsense2_camera`와 Robot Scope 에이전트를 실행해야 합니다.

표준 토픽 예시는 다음과 같습니다.

```text
/camera/camera/color/image_raw
/camera/camera/aligned_depth_to_color/image_raw
/camera/camera/depth/color/points
```

이 토픽이 나타나면 카메라 및 PointCloud 소스 목록에서 선택할 수 있습니다.

## API

- `GET /api/v1/health`: 에이전트·로봇 연결 상태
- `GET /api/v1/state`: 현재 센서, 카메라, 맵핑 요약
- `GET /api/v1/topics`: 발견한 ROS 토픽
- `GET/POST /api/v1/sources`: 표시 소스 조회·변경
- `GET /api/v1/pointcloud`: 다운샘플된 최신 점군
- `GET /api/v1/map`: 최신 OccupancyGrid
- `WS /api/v1/ws/camera`: 카메라 바이너리 스트림
- `/docs`: FastAPI OpenAPI 문서

## 운영 원칙과 다음 단계

- Uvicorn worker는 반드시 하나만 사용합니다. 여러 worker는 ROS 구독을 중복시킵니다.
- Go2 실행 스크립트는 웹 표시용 PointCloud를 최대 10,000점, 약 3 Hz로 제한합니다. 원본 SLAM 토픽은
  변경하지 않습니다.
- 인터넷이나 공용망에 노출하기 전에는 토큰 인증과 TLS를 추가해야 합니다.
- 2차 버전 후보: TF 트리, rosbag 녹화, 다중 로봇 목록,
  RealSense depth 컬러맵, 허용된 매핑 launch의 시작·저장 제어.

## 라이선스

Robot Scope 자체 코드는 [MIT License](LICENSE)로 배포합니다. 향후 Unitree의
공식 URDF/DAE 또는 변환된 GLB를 포함할 경우 해당 자산의 BSD 3-Clause 저작권·
면책문과 원본 출처를 별도로 보존해야 합니다.

## 2026-08-08 실습 환경 검증 결과

| 항목 | 확인 결과 |
|---|---|
| Dashboard agent | `jetson-orin-nano`, ROS 2 Humble, Cyclone DDS |
| Go2 연결 | `192.168.123.161`, 약 5–8 ms |
| ROS graph | 122 topics 발견 |
| 전면 카메라 | `/frontvideostream` 28 Hz 확인; 지도 실습 기본 프로필은 자동 구독 끔 |
| LiDAR | `/velodyne_points` 8–9 Hz, 16,000점/프레임 확인 |
| Hesai XT16 | `192.168.123.20`, `/lidar_points` 64,000점/프레임 확인 |
| FAST-LIO 지도 | `/Laser_map`과 `/Odometry` 수신 및 로봇 모델 오버레이 확인 |
| 2D 지도 | `/map` 971×677 OccupancyGrid 및 레이어 전환 확인 |
| 위치 | `/Odometry`, `camera_init` frame, 약 8–10 Hz |
| 상태 센서 | `/imu/body`, `/lidar_imu`, `/utlidar/lidar_state` 정상 수신 |
| 안전 모드 | 읽기 전용, 제어 명령 미전송 |
