# Robot Scope ROS 2 Dashboard

Robot Scope는 ROS 2 로봇의 연결 상태, 센서, 카메라, 위치 추정, 3D LiDAR 점군과
저장 지도를 한 브라우저에서 확인하는 웹 대시보드입니다. 대시보드에서 허용된
Hesai + FAST-LIO 매핑 파이프라인을 시작하고, 현재 지도를 3D PCD와 선택적 2D
PGM/YAML 형식으로 저장할 수도 있습니다.

Unitree Go2 + Jetson Orin Nano + ROS 2 Humble 환경을 기본 지원하며, 표준
sensor_msgs와 nav_msgs를 사용하는 다른 ROS 2 로봇에는 Generic 프로필을
사용할 수 있습니다.

## 주요 기능

- ROS graph, 토픽 타입, publisher 수와 데이터 수신 상태 자동 탐색
- IMU, 배터리, 관절, GPS, 거리 센서와 odometry 요약
- JPEG, CompressedImage, raw Image와 Go2 H.264 카메라 표시
- RViz처럼 회전·이동·확대할 수 있는 3D PointCloud 장면
- Unitree 공식 Go2 모델과 12축 다리 관절, 몸통 자세, 이동 궤적 표시
- 실시간 점군 포인트 수를 10K~250K, 사용자 지정 또는 ALL SESSION으로 선택
- 저장 PCD를 미리보기 포인트 수 또는 ALL로 표시
- Hesai + XT16 bridge + FAST-LIO 매핑 시작·중지
- 현재 Laser_map을 PCD 또는 PCD + 2D 지도 묶음으로 안전하게 저장
- 저장 지도 선택, 이름 변경, 삭제와 2D/3D 보기
- Overview, Live Mapping, Saved Maps, Sensors, ROS Graph, Settings 메뉴
- Go2 전용 프로필과 범용 ROS 2 프로필

로봇 보행·자세 제어와 임의 shell 명령 실행은 포함하지 않습니다.

## 구성

~~~text
Robot sensors / ROS 2 DDS
          |
          v
Robot Scope agent on Jetson
  - ROS graph and sensor subscribers
  - camera gateway
  - PointCloud sampling and map catalog
  - allowlisted mapping and save jobs
          |
          | HTTP + WebSocket
          v
      Web browser
~~~

ROS 2 DDS는 일반 TCP 서비스처럼 로봇 IP 하나에 접속하는 방식이 아닙니다.
센서가 연결된 Jetson에서 Robot Scope를 실행하고 브라우저로 Jetson의 8088
포트에 접속합니다. 화면의 로봇 IP는 로봇 제어기의 네트워크 생존 여부를
확인하는 대상입니다.

## 검증 환경

| 항목 | 환경 |
|---|---|
| 컴퓨터 | Jetson Orin Nano |
| 운영체제 | Ubuntu 22.04 |
| ROS | ROS 2 Humble |
| DDS | Cyclone DDS |
| 로봇 | Unitree Go2 |
| 외장 LiDAR | Hesai PandarXT-16 |
| SLAM | FAST-LIO ROS 2 |
| 브라우저 주소 | http://JETSON_IP:8088 |

자료가 ROS 2 Jazzy 기준이어도 이 프로젝트의 실행 스크립트와 검증 절차는
ROS 2 Humble에 맞춰져 있습니다.

## 빠른 설치

Jetson에서 저장소를 clone하고 ROS 패키지를 볼 수 있도록 system site packages를
포함한 가상환경을 만듭니다.

~~~bash
git clone https://github.com/Phjrab/robot-scope-ros2-dashboard.git
cd robot-scope-ros2-dashboard
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
chmod +x scripts/*.sh scripts/check_pcd_bounds.py
~~~

### Go2 + ROS 2 Humble

~~~bash
./scripts/run_go2_humble.sh
~~~

스크립트는 다음 환경을 순서대로 불러옵니다.

1. /opt/ros/humble/setup.bash
2. 사용 가능한 Unitree Cyclone DDS workspace
3. ~/setup_go2_ros2_humble.sh
4. config/go2.json

전용 이더넷이 빠져 있으면 대시보드는 offline viewer 모드로 계속 실행됩니다.
케이블 연결 후 프로세스를 다시 시작하면 Go2 전용 DDS 설정이 복구됩니다.

브라우저에서 다음 주소를 엽니다.

~~~text
http://JETSON_IP:8088
~~~

현재 포트는 ROBOT_SCOPE_PORT 환경 변수로, 로봇 생존 확인 주소는
ROBOT_SCOPE_ROBOT_IP 환경 변수로 바꿀 수 있습니다.

### 다른 ROS 2 로봇

~~~bash
export ROS_DISTRO=humble
export ROBOT_SCOPE_ROBOT_IP=192.168.1.20
export ROBOT_SCOPE_OVERLAY=$HOME/ros2_ws/install/setup.bash
./scripts/run_generic.sh
~~~

Generic 프로필은 표준 sensor_msgs와 nav_msgs 타입을 기준으로 카메라, 점군,
IMU, 배터리, 관절, GPS, 거리 센서, odometry와 OccupancyGrid를 분류합니다.
표시할 토픽은 Settings의 Data Sources에서 변경할 수 있습니다.

## 대시보드 사용 방법

### Overview

Jetson과 로봇 연결 상태, ROS 배포판, RMW, Domain ID, 센서 요약과 현재 선택한
토픽을 확인합니다.

### Live Mapping

실시간 3D 점군, 2D OccupancyGrid, Go2 모델과 이동 궤적을 확인합니다.

- 마우스 드래그: 3D 장면 회전
- Shift 또는 오른쪽 드래그: 장면 이동
- 휠: 확대·축소
- ISO, TOP, FRONT: 카메라 시점 변경
- WORLD: 지도 고정 시점
- FOLLOW: 카메라 방향을 유지하면서 로봇 위치 추적
- ROBOT: 로봇 모델과 궤적 표시 전환
- POINTS: 실시간 표시 포인트 예산 선택

ALL SESSION은 현재 브라우저 세션에 들어온 모든 유효 점을 누적합니다. 긴 세션은
브라우저 메모리와 렌더링 부하가 커질 수 있습니다. 이 설정은 화면 표시만 바꾸며
SLAM 원본 토픽과 실제 저장 데이터는 줄이지 않습니다.

### 새 지도 만들기

1. Live Mapping에서 새 맵 시작을 누릅니다.
2. 기존 누적 지도를 초기화한다는 확인창에 동의합니다.
3. ROS DATA가 LASER_MAP READY가 될 때까지 기다립니다.
4. 영문, 숫자, 하이픈 또는 밑줄로 지도 이름을 입력합니다.
5. 필요하면 2D 지도도 함께 생성을 켭니다.
6. 현재 맵 저장을 누릅니다.
7. 검증이 끝나면 Saved Maps에서 결과를 확인합니다.

현재 Go2 실습 환경의 흐름은 다음과 같습니다.

~~~text
Hesai XT16 -> /lidar_points
XT16 bridge -> /velodyne_points + /imu/body
FAST-LIO -> /cloud_registered + /Laser_map + /Odometry
Robot Scope -> live view + PCD/PGM/YAML save
~~~

대시보드의 새 맵 시작 버튼은 저장소 안의 고정된 스크립트만 실행합니다.

~~~bash
./scripts/start_hesai_mapping_humble.sh
~~~

기본 작업공간은 다음과 같습니다.

| 역할 | 기본 경로 |
|---|---|
| Hesai driver | ~/ws/hesai_ws |
| Unitree ROS 2 | ~/unitree_ros2 |
| XT16 bridge와 map saver | ~/ws/go2_3d |
| FAST-LIO | ~/ws/fastlio_ws |
| 저장 지도 | ~/ws/go2_3d/maps |

장비 구성이 다르면 scripts 디렉터리의 allowlist 실행 스크립트와 config/go2.json을
환경에 맞게 수정해야 합니다.

### Saved Maps

저장된 PCD 3D 지도와 map_server YAML + PGM 2D 지도를 별도 화면에서 관리합니다.

- POINTS에서 빠른 미리보기 또는 ALL 선택
- 관리 허용 폴더의 지도 이름 변경
- PCD 단일 파일 또는 YAML + PGM 묶음 삭제
- 읽기 전용 경로와 번들 데모 데이터 보호

전체 PCD 보기는 기본 2,000,000점까지 허용됩니다. 사용자 지정 요청은 기본
1,000,000점까지이며 config/go2.json 또는 config/generic.json의 saved_maps에서
상한을 조정할 수 있습니다.

## 카메라

Go2 전면 H.264 영상 변환에는 Jetson의 GStreamer가 필요합니다.

~~~bash
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-libav
~~~

Go2 프로필은 고대역폭 지도 처리를 우선하기 위해 카메라 자동 구독을 끕니다.
필요할 때 Settings에서 /frontvideostream을 선택합니다.

RealSense가 로봇 탑재 Jetson USB에 연결되어 있다면 같은 Jetson에서
realsense2_camera를 실행합니다. 표준 color, depth, points 토픽이 발견되면
카메라와 PointCloud 소스 목록에서 선택할 수 있습니다.

## 자동 시작

deploy/robot-scope.service.example의 사용자명과 설치 경로를 실제 환경에 맞춘 뒤
systemd 서비스로 등록할 수 있습니다.

~~~bash
sudo cp deploy/robot-scope.service.example /etc/systemd/system/robot-scope.service
sudo systemctl daemon-reload
sudo systemctl enable --now robot-scope
~~~

Uvicorn worker는 반드시 하나만 사용합니다. 여러 worker는 ROS 구독과 매핑 상태
관리를 중복시킵니다.

## 설정

- config/go2.json: Go2 토픽 우선순위, 장착 오프셋, 저장 지도 폴더와 포인트 상한
- config/generic.json: 범용 ROS 2 토픽 우선순위와 저장 지도 설정
- ROBOT_SCOPE_DIR: 프로젝트 루트 강제 지정
- ROBOT_SCOPE_PORT: HTTP 포트, 기본 8088
- ROBOT_SCOPE_ROBOT_IP: 네트워크 생존 확인 대상
- ROBOT_SCOPE_OVERLAY: Generic 프로필에서 불러올 ROS workspace setup 파일
- ROBOT_SCOPE_MAPS_DIR: Go2 지도 저장 폴더

## 주요 API

| 경로 | 용도 |
|---|---|
| GET /api/v1/health | 에이전트와 로봇 연결 상태 |
| GET /api/v1/state | 센서, 카메라, 매핑 요약 |
| GET /api/v1/topics | 발견한 ROS 토픽 |
| GET/POST /api/v1/sources | 표시 소스 조회와 변경 |
| GET /api/v1/pointcloud | 최신 실시간 점군 |
| GET/POST /api/v1/pointcloud/settings | 실시간 포인트 예산 |
| GET /api/v1/map | 최신 OccupancyGrid |
| GET /api/v1/saved-maps | 저장 지도 목록 |
| GET /api/v1/saved-maps/{id}/data | 저장 지도 렌더링 데이터 |
| PATCH/DELETE /api/v1/saved-maps/{id} | 지도 이름 변경과 삭제 |
| POST /api/v1/mapping/start | 새 매핑 세션 시작 |
| POST /api/v1/mapping/stop | 매핑 세션 중지 |
| POST /api/v1/mapping/save | 현재 지도 저장 |
| WS /api/v1/ws/camera | 카메라 스트림 |
| WS /api/v1/ws/joints | Go2 관절 스트림 |
| WS /api/v1/ws/pose | 로봇 자세 스트림 |
| /docs | FastAPI OpenAPI 문서 |

## 테스트

ROS가 없는 개발 PC에서도 핵심 로직 테스트를 실행할 수 있습니다.

~~~bash
python3 -m unittest discover -s tests -v
node --check robot_dashboard/static/app.js
node --check robot_dashboard/static/scene3d.js
~~~

## 프로젝트 구조

~~~text
config/             Go2와 Generic 프로필
deploy/             systemd 서비스 예제
robot_dashboard/    FastAPI 에이전트와 웹 UI
scripts/            실행, 매핑, 저장과 모델 생성 도구
tests/              지도, 작업 제어, 직렬화와 asset 테스트
requirements.txt    Python 웹 의존성
~~~

## 보안과 데이터 주의사항

- 현재 HTTP API에는 인증과 TLS가 없습니다. 신뢰된 실습 LAN에서만 실행합니다.
- 같은 네트워크의 사용자는 관리 허용 지도 이름 변경·삭제 API를 호출할 수 있습니다.
- 인터넷이나 공용망에 노출하기 전 토큰 인증, TLS와 접근 제어를 추가해야 합니다.
- 비밀번호, SSH 키, 토큰, .env, rosbag, PCD와 생성 지도는 Git에 올리지 않습니다.
- 지도 삭제는 되돌릴 수 없으므로 대상 이름과 파일 묶음을 확인한 뒤 실행합니다.

## 라이선스

Robot Scope 코드는 MIT License로 배포합니다. 포함된 Go2 경량 모델은 Unitree
Robotics의 unitree_ros robots/go2_description에서 변환했으며, BSD 3-Clause
원문과 변환 내역은 robot_dashboard/static/assets/go2에 보존합니다.
