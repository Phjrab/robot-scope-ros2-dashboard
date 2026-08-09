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
- JPEG, CompressedImage, raw Image와 Go2 직접 RTP/H.264 카메라 표시
- 표시 중인 카메라 화면 PNG/JPEG 캡처와 브라우저 WebM/MP4 녹화
- RViz처럼 회전·이동·확대할 수 있는 3D PointCloud 장면
- Settings에서 Go2, TurtleBot, SO-101 유형 선택과 제한된 로컬 네트워크 자동 검색
- 발견 후보의 IP, hostname, 인터페이스와 응답 지연을 확인한 뒤 연결 대상 선택
- 유형별 3D 모델 자동 전환: 공식 기반 Go2와 포함된 TurtleBot/SO-101 URDF 근사 모델
- Go2 12축 다리 관절, 몸통 자세와 이동 궤적 표시
- 실시간 점군 포인트 수를 10K~250K, 사용자 지정 또는 ALL SESSION으로 선택
- 저장 PCD를 미리보기 포인트 수 또는 ALL로 표시
- Hesai + XT16 bridge + FAST-LIO 매핑 시작·중지
- 현재 Laser_map을 PCD 또는 PCD + 2D 지도 묶음으로 안전하게 저장
- 저장 지도 선택, 이름 변경, 삭제와 2D/3D 보기
- 버튼으로 여는 단일 제어 세션과 별도 ROS 2 명령 워치독
- 키보드, 화면 패드 또는 표준 Gamepad를 선택하는 Go2 주행 제어
- 서버 allowlist에 등록된 Go2 자세·제스처·보행 모드 실행
- Overview, Live Mapping, Saved Maps, Sensors, ROS Graph, Controls, Settings 메뉴
- Go2 전용 프로필과 범용 ROS 2 프로필

저수준 모터 제어(`/lowcmd`), 임의 ROS 토픽/API와 shell 명령은 노출하지 않습니다.
덤핑, 플립, 점프, 핸드스탠드와 댄스처럼 넘어짐 위험이 큰 동작도 기본 허용 목록에서
제외합니다.

## 구성

~~~text
Web browser  <-- HTTP + WebSocket -->  Robot Scope agent on Jetson
                                           |
Robot sensors / ROS 2 DDS  ----------------+
Go2 camera / RTP multicast 230.1.1.1:1720 -+
                                           |
                                           | signed allowlisted commands
                                           v
                                  Standalone Go2 watchdog bridge
                                  - exact single-robot graph gating
                                  - 200 ms age + 50 ms watchdog cycle
                                  - /api/sport/request publisher
~~~

ROS 2 DDS는 일반 TCP 서비스처럼 로봇 IP 하나에 접속하는 방식이 아닙니다.
센서가 연결된 Jetson에서 Robot Scope를 실행하고 브라우저로 Jetson의 8088
포트에 접속합니다. Settings에서 고른 IP는 네트워크 생존 확인과 대시보드의 현재
대상·모델 선택에 사용됩니다. 실행 중인 DDS 인터페이스, domain, ROS workspace와
토픽 규칙을 자동으로 바꾸지는 않습니다. 다른 네트워크나 ROS 프로필로 전환했다면
알맞은 실행 스크립트와 설정으로 대시보드를 다시 시작해야 합니다.

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
git clone https://github.com/Phjrab/robot-scope-ros2-dashboard.git robot-scope
cd robot-scope
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
상단의 `ROS/DDS 오프라인 뷰어` 표시는 이 시작 상태를 뜻하며, Overview의 Robot
Link는 별도의 IP ping 결과입니다. 따라서 Link가 ONLINE이어도 이 표시가 남아 있으면
센서 토픽을 받을 수 없으므로 케이블을 확인한 뒤 대시보드를 다시 시작합니다.

브라우저에서 다음 주소를 엽니다.

~~~text
http://JETSON_IP:8088
~~~

현재 포트는 ROBOT_SCOPE_PORT 환경 변수로, 로봇 생존 확인 주소는
ROBOT_SCOPE_ROBOT_IP 환경 변수로 바꿀 수 있습니다.

#### Go2 제어 기능 활성화

제어는 기본적으로 비활성화됩니다. 대시보드와 독립 워치독 브리지 두 프로세스가 같은
서버 전용 환경 파일을 읽어야 활성화됩니다. 로컬 프로세스 사이에서만 쓰는 무작위
브리지 키를 만들고 실제 값은 Git에 커밋하지 않습니다.

~~~bash
mkdir -p "$HOME/.config/robot-scope"
chmod 700 "$HOME/.config/robot-scope"

openssl rand -hex 32
~~~

출력된 값을 사용해 `~/.config/robot-scope/control.env`를 만들고 권한을 제한합니다.

~~~dotenv
ROBOT_SCOPE_CONTROL_ENABLED=1
ROBOT_SCOPE_CONTROL_BRIDGE_KEY=64자리_무작위_브리지_키
~~~

~~~bash
chmod 600 "$HOME/.config/robot-scope/control.env"
~~~

수동 실행은 터미널 두 개를 사용합니다. 환경 파일을 export한 뒤 브리지를 먼저,
대시보드를 다음에 실행합니다.

~~~bash
set -a
source "$HOME/.config/robot-scope/control.env"
set +a
./scripts/run_go2_control_bridge_humble.sh
~~~

~~~bash
set -a
source "$HOME/.config/robot-scope/control.env"
set +a
./scripts/run_go2_humble.sh
~~~

Go2 전용 이더넷과 config/go2.json의 `control.lowstate_topic`(기본 `/lowstate`)이
없으면 브리지는 제어 준비 상태가 되지 않으며 ARM을 거부합니다. 선택한 LowState
publisher와 `/api/sport/request` subscriber도 각각 정확히 하나만 허용합니다. 전역
Unitree 토픽은 IP로 로봇 한 대를 식별하지 못하므로 제어할 Go2만 있는 포인트투포인트
이더넷과 전용 DDS domain/interface를 사용해야 합니다. 대시보드의 지도·센서 조회
기능은 계속 사용할 수 있습니다.

### 다른 ROS 2 로봇

~~~bash
export ROS_DISTRO=humble
export ROBOT_SCOPE_ROBOT_IP=192.168.1.20
export ROBOT_SCOPE_OVERLAY=$HOME/ros2_ws/install/setup.bash
export ROBOT_SCOPE_PROFILE=turtlebot  # generic | turtlebot | so-101
./scripts/run_generic.sh
~~~

Generic 프로필은 표준 sensor_msgs와 nav_msgs 타입을 기준으로 카메라, 점군,
IMU, 배터리, 관절, GPS, 거리 센서, odometry와 OccupancyGrid를 분류합니다.
표시할 토픽은 Settings의 Data Sources에서 변경할 수 있습니다.
`ROBOT_SCOPE_PROFILE`은 위 세 값만 허용합니다. TurtleBot과 SO-101은 각각
`config/turtlebot.json`, `config/so101.json`을 시작 프로필로 사용하며 Go2 제어는
활성화하지 않습니다.

Settings의 Connection에서 다음 표시 유형을 선택할 수 있습니다.

| 유형 | 검색 대상 | 3D 모델 | 현재 제어 범위 |
|---|---|---|---|
| Unitree Go2 | Go2 본체와 전용 유선망 | Unitree 공식 URDF 기반 경량 모델 | 안전 설정을 마친 경우 주행·허용 모션 |
| TurtleBot | 같은 LAN의 TurtleBot ROS 2 컴퓨터 | 저장소에 포함된 범용 URDF 근사 모델 | 관측·센서·지도 표시 |
| SO-101 | 팔이 USB/serial로 연결된 ROS 2 컨트롤러 호스트 | 저장소에 포함된 범용 URDF 근사 모델 | 관측·센서·지도 표시 |

TurtleBot과 SO-101 모델은 제조사 공식 치수·충돌 모델이 아니며 대시보드에서 유형을
구분하기 위한 primitive-only 시각화입니다. 현재 기본 URDF 자세로 표시되고, 각 로봇의
실시간 joint topic 매핑은 포함하지 않습니다. 시뮬레이션, 충돌 검사, 제어 또는 제작
치수로 사용하지 마세요.

## 대시보드 사용 방법

### Settings: 로봇 찾기와 모델 선택

1. Connection에서 Go2, TurtleBot 또는 SO-101을 선택합니다.
2. 대시보드가 Jetson의 활성 사설 IPv4 인터페이스를 기준으로 자동 검색합니다.
3. 후보의 IP와 hostname을 확인하고 원하는 항목을 선택합니다. 찾지 못하면 IP를 직접
   입력할 수 있습니다.
4. 연결을 누르면 현재 대상과 실시간·저장 지도 화면의 3D 모델이 함께 바뀝니다.

검색은 브라우저가 임의 subnet이나 probe 대상을 지정하지 못하게 제한되어 있습니다.
Jetson에 직접 연결된 RFC1918 또는 link-local IPv4 중 한 인터페이스의 최대 /24만
검색하며, 최대 256개 주소·32개 worker로 제한합니다. 능동 ping 단계는 최대 12초,
hostname 해석 단계는 최대 4초이며 결과를 잠시 캐시합니다.
낮은 신뢰도의 후보는 선택한 유형으로 확인된 장비가 아니라 같은 LAN에서 ping에
응답한 호스트일 수 있으므로 hostname과 실제 장비를 함께 확인하세요.

연결 버튼은 DDS 재초기화 버튼이 아닙니다. 유형 또는 네트워크가 바뀌어 ROS 2 토픽이
보이지 않으면 해당 로봇 workspace, ROS_DOMAIN_ID와 DDS 인터페이스를 설정한 뒤
대시보드를 다시 시작하세요. Go2가 아닌 유형을 선택하면 Go2 제어 lease와 명령은
서버에서도 차단됩니다.

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

### Robot Controls

Controls는 Go2 프로필에서만 사용할 수 있으며, 서버 시작 설정, 독립 제어
브리지, 최신 `/lowstate`, `/api/sport/request` 구독자가 모두 확인되어야 ARM할 수
있습니다. 한 번에 브라우저 하나만 제어 권한을 가집니다.

1. 로봇 주변을 비우고 평평한 바닥인지 확인합니다. 물리 리모컨을 손에 듭니다.
2. Controls에서 Keyboard 또는 Gamepad를 선택하고 ARM 버튼을 누릅니다.
3. 데드맨을 누르는 동안에만 주행 입력을 보냅니다.
4. 데드맨 해제, 창 전환, 페이지 이탈, 장치 연결 해제 또는 통신 중단 시 제로 명령과
   StopMove를 보내고 자동 DISARM합니다. 다시 움직이려면 재ARM해야 합니다.

키보드에서는 Shift를 유지한 채 W/A/S/D/Q/E만 놓으면 즉시 정지하되 ARM은 유지됩니다.
마지막 Shift 키를 놓을 때만 안전 해제되어 다시 ARM해야 합니다.

| 입력 | 이동 | 회전 | 데드맨 | 대시보드 정지 |
|---|---|---|---|---|
| 키보드 | W/S 전후, A/D 좌우 | Q/E | Shift | 화면의 빨간 버튼 |
| 표준 Gamepad | 왼쪽 스틱 | 오른쪽 스틱 X | LB | B |
| 화면 패드 | 방향 버튼 | 회전 버튼 | HOLD | 화면의 빨간 버튼 |

기본 서버 상한은 전후 0.30 m/s, 좌우 0.20 m/s, 회전 0.50 rad/s입니다. 화면 속도
슬라이더는 이 상한 안에서만 비율을 낮추거나 올립니다. 브라우저 입력은 200 ms가 지나면
만료되며, 별도 ROS 2 브리지의 다음 50 ms 주기에 StopMove를 보내도록 설계했습니다.
WebSocket에 송신 backlog가 생기거나 200 ms 넘게 지연된 프레임이 도착해도 세션을
폐기하여 예전 데드맨 명령을 재생하지 않습니다. ARM 직후 아직 명령을 낼 수 없는
미바인딩 lease에는 WebSocket 연결용 4초 제한을 적용하고, 바인딩이 끝난 시점부터 기존
2초 heartbeat 제한을 새로 계산합니다.

Go2 모션과 모드는 데드맨을 놓은 정지 상태에서만 실행할 수 있으며 모든 항목은 버튼을
두 번 눌러 확인합니다. 한 번이라도 주행에 사용한 ARM 세션에서는 안전 해제 후 다시
ARM해야 모션을 실행할 수 있습니다. 대시보드가 모션 명령을 접수하는 즉시 그 ARM 세션도
폐기되므로 다음 조작에는 다시 ARM해야 합니다. 화면의 접수 알림은 로봇의 동작 완료
응답이 아닙니다. 동작 종류에 따라 3~8초의 보수적인 안전 창 동안 재ARM과 주기적
idle StopMove를 막지만, SOFTWARE STOP·LowState 손실·브리지 종료는 즉시 StopMove를
보냅니다.

DASHBOARD SOFTWARE STOP은 네트워크와 소프트웨어가 살아 있을 때 이 대시보드의 lease를
폐기하고 StopMove를 보내는 기능입니다. 다른 ROS publisher를 차단하거나 로봇 전체를
전기적으로 비활성화하지 않으며 물리 비상정지 장치를 대체하지 않습니다.

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

Go2 전면 카메라는 ROS 2 `/frontvideostream`을 거치지 않습니다. 로봇이 공장 설정으로
`230.1.1.1:1720`에 송출하는 RTP/H.264 멀티캐스트를 Jetson이 전용 Go2 이더넷에서
직접 받고, GStreamer로 JPEG 프레임을 만든 뒤 기존 FastAPI WebSocket으로 같은 출처의
대시보드에 전달합니다. 별도 Flask 개발 서버나 OpenCV Python 패키지는 필요하지
않습니다.

~~~text
Go2 camera -- RTP/H.264 multicast --> GStreamer on Jetson
           230.1.1.1:1720             |
                                      +-- JPEG --> FastAPI WS --> browser canvas
~~~

필요한 GStreamer 도구와 플러그인은 다음과 같이 설치합니다.

~~~bash
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-libav
~~~

`config/go2.json`의 `direct_camera`가 직접 수신을 활성화하고, 기본 인터페이스는
`eno1`, 출력은 1280×720, 최대 15fps, JPEG 품질 80입니다. 실행 스크립트가 확인한
`ROBOT_SCOPE_DDS_INTERFACE`를 우선 사용하며, 다른 유선 어댑터를 쓸 때는 그 이름을
allowlist에도 추가한 뒤 다음 환경 변수로 지정할 수 있습니다.

~~~bash
export ROBOT_SCOPE_CAMERA_INTERFACE=enx0123456789ab
./scripts/run_go2_humble.sh
~~~

Go2 프로필의 ROS 카메라 자동 구독은 계속 꺼져 있습니다. 직접 카메라가 설정된 동안
`/frontvideostream`은 영상 소스로 사용되지 않으므로, 대용량 Unitree 영상 메시지로
인한 DDS 병목이 센서·제어 경로에 영향을 주지 않습니다. Sensors 화면에는 직접 수신
상태, FPS, 해상도와 인터페이스가 표시됩니다.

영상이 표시되면 Sensors 화면에서 PNG/JPEG `화면 캡처` 또는 `녹화 시작`을 누릅니다.
파일은 Jetson에 쌓이지 않고 현재 브라우저의 다운로드 폴더에 저장됩니다. 녹화 형식은
브라우저가 지원하는 WebM 또는 MP4 중 자동 선택되며, 카메라 소스를 바꾸거나 Sensors
메뉴를 떠나면 현재 녹화를 마무리해 저장합니다. 브라우저 탭 자체를 닫는 경우에는
완성되지 않은 임시 녹화를 안전하게 폐기할 수 있습니다.

직접 영상이 보이지 않으면 다음을 확인합니다.

1. Jetson의 Go2 전용 인터페이스에 `192.168.123.99/24`가 있는지 확인합니다.
2. `direct_camera.interface`와 실제 인터페이스 이름이 같은지 확인합니다.
3. `gstreamer1.0-plugins-good`, `-bad`, `-libav`가 설치되어 있는지 확인합니다.
4. `/api/v1/health`의 `direct_camera.last_error`, `state`, `age_s`를 확인합니다.

RealSense가 로봇 탑재 Jetson USB에 연결되어 있다면 같은 Jetson에서
realsense2_camera를 실행합니다. 표준 color, depth, points 토픽이 발견되면
카메라와 PointCloud 소스 목록에서 선택할 수 있습니다.

## 자동 시작

deploy의 두 서비스 예제는 기본적으로 `jetson_orin_nano` 사용자의
`/home/jetson_orin_nano/robot-scope` 설치를 가리킵니다. 다른 사용자명이나 경로를
사용하면 두 값을 먼저 수정한 뒤 systemd에 등록합니다. 제어를 사용하지 않으면
대시보드 서비스만 등록합니다.

~~~bash
sudo cp deploy/robot-scope.service.example /etc/systemd/system/robot-scope.service
sudo cp deploy/robot-scope-control-bridge.service.example \
  /etc/systemd/system/robot-scope-control-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now robot-scope-control-bridge robot-scope
~~~

Uvicorn worker는 반드시 하나만 사용합니다. 여러 worker는 ROS 구독과 매핑 상태
관리뿐 아니라 단일 제어 lease를 중복시킵니다. 실제 제어 환경 파일은 0600 권한으로
유지하며 두 서비스가 동일한 파일을 읽게 합니다.

## 설정

- config/go2.json: Go2 토픽 우선순위, 장착 오프셋, 저장 지도 폴더와 포인트 상한
- config/generic.json: 범용 ROS 2 토픽 우선순위와 저장 지도 설정
- config/turtlebot.json, config/so101.json: 해당 유형의 관측 전용 시작 프로필
- ROBOT_SCOPE_DIR: 프로젝트 루트 강제 지정
- ROBOT_SCOPE_PORT: HTTP 포트, 기본 8088
- ROBOT_SCOPE_ROBOT_IP: 네트워크 생존 확인 대상
- ROBOT_SCOPE_CAMERA_INTERFACE: Go2 영상 멀티캐스트를 받을 allowlist 유선 인터페이스
- ROBOT_SCOPE_OVERLAY: Generic 프로필에서 불러올 ROS workspace setup 파일
- ROBOT_SCOPE_PROFILE: run_generic.sh의 허용 프로필, generic | turtlebot | so-101
- ROBOT_SCOPE_MAPS_DIR: Go2 지도 저장 폴더
- ROBOT_SCOPE_CONTROL_ENABLED: `1`일 때만 서버 측 Go2 제어 활성화
- ROBOT_SCOPE_CONTROL_BRIDGE_KEY: 두 로컬 프로세스 사이 서명용 32바이트 이상 비밀키

## 주요 API

| 경로 | 용도 |
|---|---|
| GET /api/v1/health | 에이전트와 로봇 연결 상태 |
| GET /api/v1/state | 센서, 카메라, 매핑 요약 |
| GET /api/v1/topics | 발견한 ROS 토픽 |
| GET/POST /api/v1/sources | 표시 소스 조회와 변경 |
| GET /api/v1/robots/types | 지원 로봇 유형과 3D 모델 catalog |
| POST /api/v1/robots/discover | 선택 유형의 제한된 로컬 네트워크 검색 |
| POST /api/v1/robot | 현재 로봇 유형, IP와 hostname 선택 |
| GET /api/v1/pointcloud | 최신 실시간 점군 |
| GET/POST /api/v1/pointcloud/settings | 실시간 포인트 예산 |
| GET /api/v1/map | 최신 OccupancyGrid |
| GET /api/v1/saved-maps | 저장 지도 목록 |
| GET /api/v1/saved-maps/{id}/data | 저장 지도 렌더링 데이터 |
| PATCH/DELETE /api/v1/saved-maps/{id} | 지도 이름 변경과 삭제 |
| POST /api/v1/mapping/start | 새 매핑 세션 시작 |
| POST /api/v1/mapping/stop | 매핑 세션 중지 |
| POST /api/v1/mapping/save | 현재 지도 저장 |
| GET /api/v1/control | 제어 준비, lease, 브리지와 허용 모션 상태 |
| POST /api/v1/control/arm | 버튼 요청으로 단일 제어 lease 발급 |
| POST /api/v1/control/disarm | 제로 명령과 제어 lease 반납 |
| POST /api/v1/control/stop | lease와 무관한 대시보드 SOFTWARE STOP 래치 |
| POST /api/v1/control/estop/clear | 명시적 확인으로 대시보드 정지 해제 |
| WS /api/v1/ws/camera | 카메라 스트림 |
| WS /api/v1/ws/joints | Go2 관절 스트림 |
| WS /api/v1/ws/pose | 로봇 자세 스트림 |
| WS /api/v1/ws/control | 순서 보장된 주행·heartbeat·허용 모션 명령 |
| /docs | FastAPI OpenAPI 문서 |

## 테스트

ROS가 없는 개발 PC에서도 핵심 로직 테스트를 실행할 수 있습니다.

~~~bash
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node --check robot_dashboard/static/app.js
node --check robot_dashboard/static/control_input.js
node --check robot_dashboard/static/robot_profiles.js
node --check robot_dashboard/static/scene3d.js
~~~

## 프로젝트 구조

~~~text
config/             Go2, Generic, TurtleBot, SO-101 시작 프로필
deploy/             systemd 서비스 예제
robot_dashboard/    FastAPI 에이전트, 로컬 검색, 제어 워치독, 모델 asset과 웹 UI
scripts/            실행, 제어 브리지, 매핑, 저장과 모델 생성 도구
tests/              지도, 안전 제어, 작업, 직렬화와 asset 테스트
requirements.txt    Python 웹 의존성
~~~

## 보안과 데이터 주의사항

- 제어 ARM과 대시보드 정지 해제는 PIN 없이 버튼으로 동작하며 전체 HTTP API에도
  로그인·TLS가 없습니다. 반드시 접근이 통제된 신뢰 LAN에서만 실행하고 8088 포트를
  인터넷이나 불특정 공용망에 노출하지 않습니다.
- 제어 변경 요청과 WebSocket은 same-origin으로 제한되고, 명령은 단일 lease, 증가
  sequence, HMAC 서명, 브리지별 epoch, 200 ms 프레임 age, 단일 로봇 graph,
  LowState freshness와 이중 watchdog을 통과해야 합니다.
- DASHBOARD SOFTWARE STOP은 다른 명령 publisher를 억제하지 않으며 물리 비상정지
  수단이 아닙니다. 실제 주행 때 리모컨과 충분한 안전 공간을 확보합니다.
- 첫 실기 검증은 다리를 안전하게 띄우거나 제조사 권장 시험 자세에서 수행하고,
  브리지 강제 종료·네트워크 단절 때 Go2 펌웨어가 Move를 자체 만료시키는지 확인합니다.
- 같은 네트워크의 사용자는 관리 허용 지도 이름 변경·삭제 API를 호출할 수 있습니다.
- 네트워크 검색 API도 same-origin으로 제한하고, 서버가 직접 확인한 로컬 인터페이스의
  최대 /24만 검색합니다. 검색 결과는 장비 유형을 보증하지 않으므로 선택 전에 확인합니다.
- 인터넷이나 공용망에 노출하기 전 토큰 인증, TLS와 접근 제어를 추가해야 합니다.
- 비밀번호, SSH 키, 토큰, .env, rosbag, PCD와 생성 지도는 Git에 올리지 않습니다.
- 지도 삭제는 되돌릴 수 없으므로 대상 이름과 파일 묶음을 확인한 뒤 실행합니다.

## 라이선스

Robot Scope 코드와 저장소에서 직접 작성한 TurtleBot/SO-101 primitive-only URDF는
MIT License로 배포합니다. 포함된 Go2 경량 모델은 Unitree Robotics의 unitree_ros
robots/go2_description에서 변환했으며, BSD 3-Clause 원문과 변환 내역은
robot_dashboard/static/assets/go2에 보존합니다. 각 모델의 출처·정확도 안내는
robot_dashboard/static/assets 아래 README와 catalog에 기록합니다.
