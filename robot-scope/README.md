# Robot Scope

Robot Scope는 ROS 2 로봇의 연결 상태, 센서 값, 카메라 스트림, 위치 추정과
LiDAR 맵을 브라우저에서 확인하고, 허용된 매핑 세션을 시작·저장하는 대시보드입니다.

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
  ├─ Go2 관절 상태 WebSocket
  ├─ 선택된 Odometry 고주기 pose WebSocket
  └─ 허용된 FAST-LIO 시작·PCD/2D 지도 저장
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
- Unitree 공식 `unitree_ros/robots/go2_description`에서 변환한 경량 Go2 3D 모델과 최근 이동 궤적 표시
- `/joint_states` 우선, `/lowstate` 대체 경로를 이용한 12축 다리 관절 실시간 반영
- Odometry quaternion 전체 자세와 IMU yaw delta를 이용한 30 FPS 최단각 보간
- Overview / Live Mapping / Saved Maps / Sensors / ROS Graph 메뉴 분리
- 실시간 LiDAR와 저장된 PCD·map_server 2D 지도를 서로 독립적으로 표시
- 대시보드에서 Hesai+FAST-LIO 새 세션 시작, 3D PCD 저장, 선택적 2D PGM+YAML 변환
- Hesai `/lidar_points` publisher를 `XT16 ONLINE`으로 표시
- 로봇 IP ping, ROS 배포판·Domain·RMW 표시
- 토픽별 소스 변경

로봇 보행·자세 제어와 임의 명령 실행은 포함하지 않습니다. 매핑 작업은 서버에
고정된 Humble 스크립트만 실행하며 브라우저 입력은 지도 이름과 2D 변환 여부로
제한합니다.

## Jetson 설치

```bash
cd ~/robot-scope
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
chmod +x scripts/run_go2_humble.sh scripts/start_hesai_mapping_humble.sh \
  scripts/save_hesai_map_humble.sh scripts/check_pcd_bounds.py
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
| 실시간 3D 매핑 | FAST-LIO 실행 시 `/cloud_registered`; 브라우저에서 최대 30,000점 누적 |
| Go2 내장 LiDAR 대체 | `/utlidar/cloud_deskewed` (`odom` frame) |
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
| 누적 3D 지도/저장 원본 | `/Laser_map` | scan 주기에 맞춰 발행되며 계속 커짐 |
| 지도 기준 자세 | `/Odometry` | 약 10 Hz, frame `camera_init` |
| 저장된 2D 지도 | `/map` | 971×677, 0.05 m/cell |

FAST-LIO가 켜지면 화면은 같은 `camera_init` 좌표계인 `/cloud_registered`와
`/Odometry`로 자동 전환합니다. 등록된 스캔은 브라우저에서 제한된 크기로 누적하고,
실제 저장은 전체 `/Laser_map`을 사용합니다. `Live Mapping`의 `VIEW`는
`LIVE 3D`, `LIVE 2D`, `AUTO` 중에서 고릅니다. 3D 장면은 드래그로 회전,
Shift/오른쪽 드래그로 이동, 휠로 확대하며 `ISO`, `TOP`, `FRONT` 버튼으로
시점을 즉시 바꿀 수 있습니다. `WORLD`가 기본 지도 고정 시점이며, 누르면 카메라
방향을 고정한 채 위치만 따라가는 `FOLLOW`로 바뀝니다. `ROBOT`을 끄면 로봇
모델과 궤적을 숨깁니다.

### 대시보드에서 새 지도 만들기

1. `Live Mapping`의 `새 맵 시작`을 누르고 기존 누적 지도 초기화 확인창에 동의합니다.
2. `ROS DATA`가 `LASER_MAP READY`가 될 때까지 기다립니다.
3. ASCII 지도 이름을 입력하고, 필요하면 `2D 지도도 함께 생성`을 켭니다.
4. `현재 맵 저장`을 누릅니다. PCD와 선택한 PGM·YAML 검증이 끝나면 `Saved Maps`가 자동 갱신됩니다.

새 세션은 같은 사용자로 실행 중인 기존 Hesai driver, XT16 bridge, FAST-LIO만
`SIGINT`와 `SIGTERM` 순으로 정리합니다. 그래도 남은 정확한 동일 사용자·명령행
프로세스만 다시 검증한 뒤 최후 수단으로 `SIGKILL`합니다. 지도 저장은 비공개 임시 폴더에서
완료되며 PCD 헤더·point 수, YAML 이미지 참조, PGM magic과 파일 크기를 검증한
결과만 `~/ws/go2_3d/maps`에 공개합니다. 2D 변환은 기존 정적 `/map`과 충돌하지
않는 작업별 토픽을 사용하며 최대 1,600만 cell로 제한합니다.

`Live Mapping`은 현재 들어오는 데이터만 표시하며, 로봇이나 LiDAR가 꺼져 있으면
`LIVE DATA WAITING`을 표시합니다. 과거 지도는 `Saved Maps`에서 별도로 선택합니다.
에이전트는 `config/go2.json`에 지정된 디렉터리를 읽기 전용으로 탐색해 binary PCD,
Robot Scope JSON, map_server YAML+PGM을 목록으로 제공합니다. 공개 저장소처럼 지도
파일이 없는 환경에서는 실제 공간 정보가 없는 데모 점군을 브라우저에서 생성합니다.
새 PCD 스냅샷은 다음처럼 정적 JSON으로 만들 수도 있습니다.

```bash
python3 scripts/pcd_to_scene.py /path/to/map.pcd \
  robot_dashboard/static/data/go2_saved_map.json --max-points 10000
```

좌표계가 같은 `/cloud_registered`(`camera_init`)와 `/Odometry`는 로봇을 지도 절대
좌표에 표시합니다. 원시 `hesai_lidar` 화면에서는 설정된 `body <- hesai_lidar`
장착 오프셋을 적용합니다. 그 밖의 서로 다른 frame에 유효한 변환이 없으면 잘못된
좌표를 임의로 중앙에 놓지 않고 로봇 오버레이를 숨깁니다.

점군과 odometry가 모두 살아 있을 때 표시되는
`MAPPING` 배지는 두 입력의 수신 상태를 뜻하며, SLAM 품질을 판정한다는 뜻은
아닙니다.

Go2 프로필은 지도 처리 성능을 보호하기 위해 카메라를 자동 구독하지 않습니다.
`/lowstate`는 약 350–500 Hz지만 관절 렌더링용 최신값만 최대 50 Hz로 처리하고,
센서 카드 요약은 더 낮은 주기로 제한합니다. 정상 관절 메시지가 1초 이상 끊기면
마지막 값을 고정하지 않고 공식 모델의 기본 대기 자세로 되돌립니다.

### 이번 장비에서 확인한 트러블슈팅

- Hesai 원본 `/lidar_points`를 여러 Python 구독자가 직접 받으면 CycloneDDS가
  간헐적으로 `sequence size exceeds remaining buffer`를 기록했습니다. 대시보드
  기본값은 FAST-LIO가 실제로 사용하는 안정적인 브리지 출력
  `/velodyne_points`입니다.
- `/frontvideostream`을 고대역폭 지도 토픽과 함께 상시 디코딩하면 대시보드의
  CPU·메모리가 급증했습니다. Go2 프로필에서는 카메라 자동 구독을 끄고 지도와
  센서를 우선합니다.
- `/Laser_map`은 계속 커지는 누적 지도입니다. 에이전트는 전체 배열을 복사하지
  않고 실시간 표시는 더 작은 `/cloud_registered`를 샘플링합니다. 브라우저는
  등록 스캔을 최대 30,000점까지 누적하고 장면 렌더링은 10,000점으로 제한합니다.
- 원시 `/velodyne_points`(`hesai_lidar`)와 `/Odometry`(`camera_init`)를 직접
  겹치면 로봇과 점군 위치가 어긋납니다. 자동 소스 선택은 publisher가 사라진
  stale 선택을 버리고 `/cloud_registered + /Odometry` world-frame pair로 승격합니다.
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
- `GET /api/v1/joints`: 정규화된 Go2 12축 관절과 몸통 RPY
- `GET /api/v1/pose`: 선택된 Odometry의 freshness-aware pose
- `GET /api/v1/mapping/control`: 매핑 프로세스·저장 작업·제한된 로그
- `POST /api/v1/mapping/start|stop|save`: 허용된 매핑 작업
- `GET /api/v1/saved-maps`: 허용된 디렉터리의 저장 지도 목록
- `GET /api/v1/saved-maps/{id}/data`: 선택한 PCD 또는 2D 지도의 렌더링 데이터
- `WS /api/v1/ws/camera`: 카메라 바이너리 스트림
- `WS /api/v1/ws/joints`: 최대 50 Hz 관절 상태 스트림
- `WS /api/v1/ws/pose`: 최대 50 Hz compact pose 스트림
- `/docs`: FastAPI OpenAPI 문서

## 운영 원칙과 다음 단계

- Uvicorn worker는 반드시 하나만 사용합니다. 여러 worker는 ROS 구독을 중복시킵니다.
- Go2 실행 스크립트는 웹 표시용 PointCloud를 최대 10,000점, 약 3 Hz로 제한합니다. 원본 SLAM 토픽은
  변경하지 않습니다.
- 인터넷이나 공용망에 노출하기 전에는 토큰 인증과 TLS를 추가해야 합니다.
- 다음 후보: TF 트리, rosbag 녹화, 다중 로봇 목록, RealSense depth 컬러맵.

## 라이선스

Robot Scope 자체 코드는 [MIT License](LICENSE)로 배포합니다. 포함된 Go2 경량
모델은 Unitree Robotics의 `unitree_ros` 내 `robots/go2_description` 커밋
`f3772ce54c56ef2d34c6aee8100bc768896c7d19`에서 변환했으며 BSD 3-Clause 원문과
변환 내역은 `robot_dashboard/static/assets/go2/`에 보존합니다.

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
| 상태 센서 | `/lowstate` 12축 관절·몸통 RPY 및 IMU·LiDAR 상태 수신 |
| 안전 모드 | 지도 작업만 허용, 로봇 구동·임의 명령 비활성 |
