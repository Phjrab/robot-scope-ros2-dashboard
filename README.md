# Robot Scope ROS 2 Dashboard

Robot Scope는 ROS 2 로봇의 연결 상태, 센서, 카메라, 위치 추정, 3D LiDAR 점군과
저장 지도를 한 브라우저에서 확인하는 웹 대시보드입니다. 대시보드에서 허용된
Hesai + FAST-LIO 매핑 파이프라인을 시작하고, 현재 지도를 3D PCD와 선택적 2D
PGM/YAML 형식으로 저장할 수도 있습니다.

Ubuntu 22.04 ROS host + ROS 2 Humble 환경을 기본 지원합니다. Unitree Go2 + XT16
전체 경로의 검증 플랫폼은 Jetson Orin Nano이지만 Jetson 전용 애플리케이션은 아닙니다.
표준 sensor_msgs와 nav_msgs를 사용하는 다른 ROS 2 로봇에는 Generic 프로필을 사용할
수 있습니다.

전체 Go2 + XT16 경로는 Ubuntu 22.04, ROS 2 Humble, Jetson Orin Nano
(`arm64`)에서 검증했습니다. 웹/Generic 계층은 Ubuntu 22.04의 `x86_64`와 `arm64`를
지원하지만, 제조사 ROS driver와 SDK의 아키텍처 호환성은 별도로 확인해야 합니다.

## 설치 및 운영 문서

| 문서 | 내용 |
|---|---|
| [설치](docs/INSTALL.md) | `observer`, `go2`, `go2-control`, `go2-xt16`, `go2-nav` 모드와 스모크 테스트 |
| [의존성](docs/DEPENDENCIES.md) | 외부 ROS workspace, pin/라이선스 기록과 미포함 구성 요소 |
| [토폴로지](docs/TOPOLOGY.md) | 단일/두 호스트 배선, 서비스 역할과 관리망 분리 |
| [문제 해결](docs/TROUBLESHOOTING.md) | DDS, XT16, 저장, 카메라, 제어와 Nav 진단 순서 |
| [업데이트/롤백](docs/UPDATE_ROLLBACK.md) | 지도·상태 보존, fast-forward update와 안전 롤백 |
| [Third-party notices](THIRD_PARTY_NOTICES.md) | 포함된 공식 robot model의 출처와 라이선스 |

처음 설치하는 사용자는 가장 작은 `observer` 모드에서 시작해 필요한 하드웨어 기능만
단계적으로 추가하세요. XT16 bridge, Laser map saver와 PCD→2D converter는 저장소에
포함되지만 제조사 driver, Livox SDK2와 FAST-LIO workspace는 별도 설치가 필요합니다.
자세한 pinned revision은 [의존성 manifest](docs/DEPENDENCIES.md)를 확인하세요.

## 주요 기능

- ROS graph, 토픽 타입, publisher 수와 데이터 수신 상태 자동 탐색
- IMU, 배터리, 관절, GPS, 거리 센서와 odometry 요약
- JPEG, CompressedImage, raw Image와 Go2 직접 RTP/H.264 카메라 표시
- 표시 중인 카메라 화면 PNG/JPEG 캡처와 브라우저 WebM/MP4 녹화
- RViz처럼 회전·이동·확대할 수 있는 3D PointCloud 장면
- 같은 라이브 점군을 추가 전송 없이 위에서 투영하는 2D 매핑 화면
- Settings에서 Go2, TurtleBot, SO-101 유형 선택과 제한된 로컬 네트워크 자동 검색
- 발견 후보의 IP, hostname, 인터페이스와 응답 지연을 확인한 뒤 연결 대상 선택
- 유형별 3D 모델 자동 전환: 공식 기반 Go2, TurtleBot3 Burger, SO-101 경량 모델
- Go2 12축 다리 관절, 몸통 자세와 이동 궤적 표시
- 실시간 점군 포인트 수를 10K~250K, 사용자 지정 또는 ALL SESSION으로 선택
- 저장 PCD를 미리보기 포인트 수 또는 ALL로 표시
- Hesai + XT16 bridge + FAST-LIO 매핑 시작·중지
- 현재 Laser_map을 PCD 또는 PCD + 2D 지도 묶음으로 안전하게 저장
- 저장 PCD를 높이 범위·해상도·2D 투영 점 밀도로 새 PGM/YAML 지도에 변환
- 저장 2D 지도를 브러시로 정리하고 원본을 보존한 새 복사본으로 저장
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
Web browser  <-- HTTP + WebSocket -->  Robot Scope agent on Ubuntu ROS host
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
센서가 연결된 Ubuntu ROS host에서 Robot Scope를 실행하고 브라우저로 그 host의 8088
포트에 접속합니다. Settings에서 고른 IP는 네트워크 생존 확인과 대시보드의 현재
대상·모델 선택에 사용됩니다. 실행 중인 DDS 인터페이스, domain, ROS workspace와
토픽 규칙을 자동으로 바꾸지는 않습니다. 다른 네트워크나 ROS 프로필로 전환했다면
알맞은 실행 스크립트와 설정으로 대시보드를 다시 시작해야 합니다.

## 검증 환경

| 항목 | 환경 |
|---|---|
| 검증 컴퓨터 | Jetson Orin Nano (필수 장비 아님) |
| 운영체제 | Ubuntu 22.04 |
| 아키텍처 | Jetson Orin Nano arm64 전체 경로 검증; x86_64/arm64 웹·Generic 지원 |
| ROS | ROS 2 Humble |
| DDS | Cyclone DDS |
| 로봇 | Unitree Go2 |
| 외장 LiDAR | Hesai PandarXT-16 |
| SLAM | FAST-LIO ROS 2 |
| 브라우저 주소 | http://JETSON_IP:8088 |

자료가 ROS 2 Jazzy 기준이어도 이 프로젝트의 실행 스크립트와 검증 절차는
ROS 2 Humble에 맞춰져 있습니다.

## 빠른 설치

새 호스트에는 [설치 가이드](docs/INSTALL.md)의 mode별 절차를 권장합니다. 설치 helper와
하드웨어를 변경하지 않는 doctor는 다음 이름을 사용합니다.

~~~bash
./scripts/install_ubuntu.sh --mode observer \
  --install-system-packages --install-service          # read-only dry-run
./scripts/install_ubuntu.sh --mode observer --apply \
  --install-system-packages --install-service          # explicit install
python3 scripts/robot_scope_doctor.py --mode observer
~~~

Installer는 target 사용자로 실행하며 root로 직접 실행하지 않습니다. `--apply`와
`--install-system-packages` 또는 `--install-service` opt-in을 함께 지정한 경우에만 해당
APT/systemd 작업에 sudo를 사용합니다. 설치한 unit은 enable하되 즉시 시작하지 않습니다.
설치 중에는 분리된 로봇 NIC를 경고로 허용하지만, 서비스 시작 전 별도 `doctor` 명령은
NIC와 고정 주소를 다시 엄격하게 검사합니다.

아래 명령은 Python 웹 계층의 수동 최소 설치입니다. Go2, XT16, 제어와 Nav2 전체 기능은
외부 의존성과 호스트별 설정이 추가로 필요합니다.

Ubuntu ROS host에서 저장소를 clone하고 ROS 패키지를 볼 수 있도록 system site packages를
포함한 가상환경을 만듭니다.

~~~bash
git clone https://github.com/Phjrab/robot-scope-ros2-dashboard.git robot-scope
cd robot-scope
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
chmod +x scripts/*.sh scripts/check_pcd_bounds.py
~~~

Navigation 화면까지 사용할 Ubuntu ROS host에는 ROS 2 Humble Nav2가 설치되어 있어야 합니다.
별도의 `pointcloud_to_laserscan` 패키지는 사용하지 않으며, 저장소의 제한된 runtime이
XT16 `PointCloud2`를 `/scan`으로 변환합니다.

~~~bash
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup
~~~

### Go2 + ROS 2 Humble

~~~bash
./scripts/run_go2_humble.sh
~~~

스크립트는 다음 환경을 순서대로 불러옵니다.

1. /opt/ros/humble/setup.bash
2. 사용 가능한 Unitree Cyclone DDS workspace
3. 저장소의 `scripts/setup_go2_ros2_humble.sh`
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
publisher와 `/api/sport/request` subscriber는 각각 정확히 하나만 허용합니다.
`/api/sport/request` publisher는 브리지 소유 endpoint가 정확히 하나이고 다른 이름의
ROS publisher가 없어야 합니다. Go2 펌웨어의 bare-DDS request endpoint는 ROS node로
식별되지 않으므로 `control.expected_bare_sport_publishers`에 읽기 전용 점검으로 확인한
개수를 고정하고, 개수가 달라지면 fail-closed 합니다. 펌웨어 변경 후에는 이 값을
자동으로 완화하지 말고 ROS graph를 다시 점검해야 합니다. 전역 Unitree 토픽은 IP로
로봇 한 대를 식별하지 못하므로 제어할 Go2만 있는 포인트투포인트 이더넷과 전용 DDS
domain/interface를 사용해야 합니다. 대시보드의 지도·센서 조회 기능은 계속 사용할 수
있습니다.

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
| TurtleBot | 같은 LAN의 TurtleBot ROS 2 컴퓨터 | ROBOTIS 공식 TurtleBot3 Burger URDF/STL 기반 | 관측·센서·지도 표시 |
| SO-101 | 팔이 USB/serial로 연결된 ROS 2 컨트롤러 호스트 | LeRobot이 참조하는 TheRobotStudio 공식 SO-101 URDF/STL 기반 | 관측·센서·지도 표시 |

TurtleBot은 ROBOTIS `turtlebot3_description`의 Burger 모델, SO-101은 LeRobot 공식
문서가 안내하는 TheRobotStudio `Simulation/SO101` 모델을 고정된 upstream commit에서
가져옵니다. 원본 URDF와 visual STL은 바이트 그대로 포함하며, 브라우저는 그 표면을
결정론적으로 경량화한 JSON을 표시합니다. 현재 기본 URDF 자세로 표시되고 각 로봇의
실시간 joint topic 매핑은 포함하지 않습니다. 경량 파생물은 시뮬레이션, 충돌 검사,
제어 또는 제작 치수로 사용하지 마세요.

## 대시보드 사용 방법

### Settings: 로봇 찾기와 모델 선택

1. Connection에서 Go2, TurtleBot 또는 SO-101을 선택합니다.
2. 대시보드가 ROS host의 활성 사설 IPv4 인터페이스를 기준으로 자동 검색합니다.
3. 후보의 IP와 hostname을 확인하고 원하는 항목을 선택합니다. 찾지 못하면 IP를 직접
   입력할 수 있습니다.
4. 연결을 누르면 현재 대상과 실시간·저장 지도 화면의 3D 모델이 함께 바뀝니다.

검색은 브라우저가 임의 subnet이나 probe 대상을 지정하지 못하게 제한되어 있습니다.
ROS host에 직접 연결된 RFC1918 또는 link-local IPv4 중 한 인터페이스의 최대 /24만
검색하며, 최대 256개 주소·32개 worker로 제한합니다. 능동 ping 단계는 최대 12초,
hostname 해석 단계는 최대 4초이며 결과를 잠시 캐시합니다.
낮은 신뢰도의 후보는 선택한 유형으로 확인된 장비가 아니라 같은 LAN에서 ping에
응답한 호스트일 수 있으므로 hostname과 실제 장비를 함께 확인하세요.

연결 버튼은 DDS 재초기화 버튼이 아닙니다. 유형 또는 네트워크가 바뀌어 ROS 2 토픽이
보이지 않으면 해당 로봇 workspace, ROS_DOMAIN_ID와 DDS 인터페이스를 설정한 뒤
대시보드를 다시 시작하세요. Go2가 아닌 유형을 선택하면 Go2 제어 lease와 명령은
서버에서도 차단됩니다.

### Overview

ROS host와 로봇 연결 상태, ROS 배포판, RMW, Domain ID, 센서 요약과 현재 선택한
토픽을 확인합니다.

### Live Mapping

실시간 3D 점군, 같은 점군의 2D 상단 투영, ROS OccupancyGrid, Go2 모델과 이동
궤적을 확인합니다. VIEW에서 `LIVE 3D`, `LIVE 2D · POINTS`, `ROS 2D · GRID`,
`AUTO`를 선택할 수 있습니다. 포인트 투영은 별도 API를 호출하지 않고 현재 3D 프레임을
희소 XY 셀로 바꾸며, 실제 OccupancyGrid나 저장된 2D 지도는 아닙니다.

- 마우스 드래그: 3D 장면 회전
- Shift 또는 오른쪽 드래그: 장면 이동
- 휠: 확대·축소
- ISO, TOP, FRONT: 카메라 시점 변경
- WORLD: 지도 고정 시점
- FOLLOW: 카메라 방향을 유지하면서 로봇 위치 추적
- ROBOT: 로봇 모델과 궤적 표시 전환
- POINTS: 실시간 표시 포인트 예산 선택

ALL SESSION은 현재 브라우저 세션의 유효 점을 최대 1,000,000점 reservoir로 누적합니다.
긴 세션은 브라우저 메모리와 렌더링 부하가 커질 수 있습니다. 이 설정은 화면 표시만
바꾸며 SLAM 원본 토픽과 실제 저장 데이터는 줄이지 않습니다.

실시간 점군은 JSON 배열 대신 little-endian float32 XYZ 바이너리 WebSocket으로
전송합니다. 매핑 화면을 볼 때만 연결하고 최신 프레임 하나만 유지하므로 느린 클라이언트가
오래된 프레임을 쌓지 않습니다. 기본 10K는 가장 부드러운 표시, 30K는 화질과 지연의
균형값입니다. Go2 프로필의 10K/30K는 소스가 허용하면 최대 약 10fps를 목표로 하며,
서버는 프레임당 최대 1,000,000점과 클라이언트당 약 4 MB/s 목표로 큰 프레임의 전송
간격을 자동으로 늘려 Wi-Fi 포화를 막습니다. WebSocket을 사용할 수 없을 때만 binary HTTP,
그마저 지원하지 않는 구버전 서버에서는 기존 JSON API로 순차 fallback합니다.

현재 검증 host의 Wi-Fi는 신호 세기보다 RTT jitter와 절전 때문에 순간 지연이 생길 수
있습니다. 앱 최적화를 먼저 적용한 뒤에도 안정성이 더 필요하면 대시보드용 별도
USB-Ethernet NIC 또는 검증된 스위치를 사용하세요. `eno1`은 Go2·Hesai의
`192.168.123.0/24`와 카메라 multicast에 쓰이므로 Mac 접속용 LAN이 그 포트를 대체하면
안 됩니다. Wi-Fi 절전 해제는 호스트 전원 정책 변경이므로 현장 승인 후 별도로 적용합니다.

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

#### XT16 목적지를 유지하는 단방향 UDP 복제

XT16의 목적지를 로봇 탑재 Jetson `192.168.123.18`로 유지하면서 Robot Scope
Jetson `192.168.123.99`에서도 매핑해야 하는 현재 실습 배선에는
`scripts/xt16_udp_relay.py`를 `.18`에서 실행할 수 있습니다. 릴레이는 센서 설정을
변경하거나 UDP 2368을 bind하지 않습니다. `eth0`의 비promiscuous Linux packet
socket으로 기존 수신 패킷을 수동 관측하고, 아래 실측 계약을 모두 만족하는 payload만
일반 UDP `sendto()`로 `.99:2368`에 복제합니다.

| 항목 | 고정값 |
|---|---|
| 캡처 인터페이스 | `eth0` |
| 원본 경로 | `192.168.123.20:10000` → `192.168.123.18:2368` |
| 복제 목적지 | `192.168.123.99:2368` |
| XT16 UDP payload | 568 bytes, `eeff06010000100801040201` 헤더 |

IP 옵션·fragment, 다른 packet type/IP/port, 길이가 다른 UDP, 다른 XT16 헤더는 모두
거부됩니다. 허용값은 환경 변수나 실행 인자로 완화할 수 없습니다. 5초마다 전달 수,
고정 분류별 거부 수, UDP sequence 유실·중복·역순과 전송 오류를 한 줄로 기록합니다.
종료 시에도 최종 통계를 남깁니다.

일반 UDP 복제이므로 `.99`에서 보이는 패킷 source는 `.18`의 임시 UDP port입니다.
현재 Hesai driver는 `device_udp_src_port: 0`으로 이 경로가 검증되어 있습니다. driver에서
`device_ip_address: 192.168.123.20`처럼 원본 source IP만 강제하면 복제 패킷을 버리므로,
배포 전 해당 필터가 비어 있거나 `.18`을 허용하는지 확인해야 합니다. 성공 판정은 relay
counter만으로 하지 않고 `.99`에서 `/lidar_points`가 새 데이터 약 10 Hz를 유지하는지
확인합니다.

예제 unit은 `unitree` 사용자에게 packet capture에 필요한 `CAP_NET_RAW` 하나만 주며,
root 실행을 사용하지 않습니다. capability가 사용자가 교체할 수 있는 저장소 파일에
적용되지 않도록 실행본은 root 소유 전용 경로에 먼저 복사합니다.

~~~bash
sudo install -d -o root -g root -m 0755 /usr/local/libexec/robot-scope
sudo install -o root -g root -m 0755 scripts/xt16_udp_relay.py \
  /usr/local/libexec/robot-scope/xt16_udp_relay.py
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-xt16-relay.service.example \
  /etc/systemd/system/robot-scope-xt16-relay.service
sudo systemctl daemon-reload
sudo systemctl enable --now robot-scope-xt16-relay.service
~~~

부팅 시 `network-online.target`보다 `eth0`의 `.18` 주소 준비가 늦어도 service는 2초
간격으로 계속 재시도합니다. 유한 start limit으로 포기하지 않으므로 별도의 수동
`reset-failed` 없이 인터페이스가 준비되는 즉시 자동 시작됩니다.

롤백은 센서나 ROS 설정을 되돌릴 필요 없이 service만 중지·비활성화합니다.

~~~bash
sudo systemctl disable --now robot-scope-xt16-relay.service
sudo rm -f /etc/systemd/system/robot-scope-xt16-relay.service
sudo rm -f /usr/local/libexec/robot-scope/xt16_udp_relay.py
sudo rmdir --ignore-fail-on-non-empty /usr/local/libexec/robot-scope
sudo systemctl daemon-reload
sudo systemctl reset-failed robot-scope-xt16-relay.service
~~~

Settings의 `LiDAR / 3D 맵` 목록은 장치별로 `GO2 BUILT-IN LIDAR`와
`HESAI XT16`을 나눠 보여 줍니다. `/utlidar/*`의 허용된 토픽은 Go2 내장
LiDAR이고, `/lidar_points`는 XT16 원본, `/velodyne_points`는 변환 점군,
`/cloud_registered`와 `/Laser_map`은 XT16을 입력으로 쓰는 FAST-LIO 결과입니다.
Settings와 Live Mapping 헤더에는 현재 선택한 장치·토픽·처리 단계와
`LIVE/WAITING/STALE` 상태가 함께 표시됩니다. Go2 프로필의 기본 소스는
`/velodyne_points`로 고정되며, 사용자가 명시적으로 고른 허용 소스는
`~/.local/state/robot-scope/source-selection.json`에 0600 권한으로 저장됩니다.
선택한 XT16 publisher가 재시작 중 사라져도 내장 LiDAR로 전환하지 않고 해당 항목을
`WAITING`으로 유지합니다. 빈 소스를 POST하면 사용자 override를 삭제하고 Go2 프로필의
기본 `/velodyne_points` 고정으로 돌아갑니다.

대시보드의 새 맵 시작 버튼은 저장소 안의 고정된 스크립트만 실행합니다.

~~~bash
./scripts/start_hesai_mapping_humble.sh
~~~

기본 작업공간은 다음과 같습니다.

| 역할 | 기본 경로 |
|---|---|
| Hesai driver | ~/ws/hesai_ws |
| Unitree ROS 2 | ~/unitree_ros2 |
| XT16 bridge와 map saver | 이 저장소의 scripts 디렉터리 |
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

관리 가능한 PCD를 선택하면 Saved Maps에서 바로 새 2D 지도를 만들 수 있습니다.
기본 시작값은 수업 자료와 같은 `z_min=-0.2 m`, `z_max=0.8 m`,
`resolution=0.05 m`, `noise_radius=0.1 m`, `min_neighbors=10`입니다. 서버의 자동
노이즈 처리는 PCL의 3D RadiusOutlierRemoval과 같은 구현이 아니라, 높이 슬라이스 뒤
XY에 투영한 점 밀도 필터입니다. 화면에도 **자동 점 노이즈 필터(2D 투영)** 로
표시합니다.

배경은 기본적으로 `unknown`입니다. 점이 관측된 셀만 장애물로 만들고 나머지를 미관측
영역으로 두므로 내비게이션에 더 안전합니다. 수업 자료의 PGM처럼 경계 상자 전체를
자유공간으로 채우려면 `free`를 명시적으로 선택할 수 있지만, 그 범위가 실제로 모두
스캔된 자유공간임을 확인한 경우에만 사용하세요.

2D 편집기는 Free, Unknown, Occupied 브러시를 제공합니다. 저장할 때는 현재 원본의
opaque 64자리 revision과 최대 10,000개의 정렬된 RLE run만 전송하며, 기본 최대
2,000,000개 셀까지만 바꿀 수 있습니다. 원본 PCD/PGM/YAML은 덮어쓰지 않고 새 이름의
PGM+YAML 쌍을 만듭니다. 입력은 독립된 제한 크기 스냅샷으로 복사되고, 원본 교체 경합,
출력 이름 충돌 또는 두 파일 중 하나의 게시 실패가 감지되면 새 출력 쌍을 롤백합니다.
웹 브러시 편집은 관리 허용 폴더의 `mode: trinary`(또는 mode 생략) YAML과
`P5`, `maxval=255` PGM 쌍에만 활성화됩니다. 읽기 전용 지도, ASCII P2, 16-bit PGM,
`scale` 또는 `raw` mode는 볼 수는 있지만 원본 픽셀 의미를 안전하게 보존할 수 없어
편집 버튼을 비활성화합니다.

PCD 변환 요청은 202를 반환하기 전에 단일 작업 lease와 고유 `job_id`를 예약합니다.
브라우저는 같은 `job_id`의 상태만 추적하며, preflight에서 읽은 source revision이 실제
worker 시작 전 바뀌거나 서버 종료 신호가 publish 전에 도착하면 결과 파일을 게시하지
않고 해당 작업을 실패 상태로 기록합니다.

전체 PCD 보기는 기본 2,000,000점까지 허용됩니다. 사용자 지정 요청은 기본
1,000,000점까지이며 config/go2.json 또는 config/generic.json의 saved_maps에서
상한을 조정할 수 있습니다. PCD→2D 변환도 기본 2,000,000점, 출력 지도는 기본
16,000,000셀 상한을 공유합니다.

매핑 시작·중지·저장과 저장 지도 생성·편집·이름 변경·삭제 요청은 브라우저의
same-origin 검사를 통과해야 합니다.
Robot Scope는 인증 없는 신뢰 LAN 실습 배포를 전제로 하므로 8088 포트를 인터넷에 직접
노출하지 마세요.

### Navigation: 저장 지도에서 Go2 주행

Navigation 메뉴는 관리 가능한 `mode: trinary` YAML + `P5/255` PGM 지도를 선택해
ROS 2 Humble Nav2를 실행합니다. 브라우저는 파일 경로나 ROS 토픽 이름을 보내지 않고
opaque map ID와 64자리 map/parameter revision만 전송합니다. 서버는 원본 지도를
덮어쓰지 않는 private snapshot을 만든 뒤 저장소의 고정 launcher와 생성된 Humble
parameter YAML만 `shell=False` process group으로 실행합니다.

같은 화면의 별도 3D 패널은 Settings에서 선택한 Go2, TurtleBot 또는 SO-101 모델을
표시합니다. Go2 관절 데이터는 선택 프로필과 runtime이 일치하고 최신 샘플이 있을 때만
반영하며, Navigation의 map 좌표 위치와 다른 telemetry 자세를 섞지 않습니다.

내비게이션 시작 시 Hesai + XT16 bridge + FAST-LIO가 이미 대시보드 소유 process로
실행 중이면 그대로 공유합니다. 파이프라인이 idle/failed 상태면 동일한 allowlisted
매핑 시작 경로를 자동 실행한 뒤 Nav2를 시작합니다. 이 shared pipeline이
`/velodyne_points`와 `/Odometry`를 공급하고 navigation runtime이 고정 `/scan`과
`odom -> base_link` TF를 만듭니다. Navigation의 중지는 Nav2와 signed motion lease만
정리하며 Hesai + FAST-LIO는 계속 실행하므로, 다시 매핑 화면에서 관측하거나 다음
내비게이션 시작에 재사용할 수 있습니다.

Nav2 controller 출력은 전역 `/cmd_vel`이 아니라 서버 고정
`/robot_scope/nav/cmd_vel_raw`로 격리됩니다. RosAgent는 publisher가 정확히 하나이고
scan, FAST-LIO odometry, Go2 `/utlidar/robot_odom`, TF, 위치추정과 signed bridge가 모두
fresh일 때만 이 명령을 기존 단일 lease/watchdog bridge로 전달합니다. 초기 위치와
목표는 선택한 revision의 known-free 셀 안에서 Go2 반경만큼 여유가 있을 때만
허용되며, 목표 전송은 화면 확인 뒤 `confirmed: true`가 있어야 합니다.

Navigation이 active인 동안 다음 요청은 409로 차단됩니다.

- Hesai + FAST-LIO 시작·중지와 현재 지도 저장
- PCD→2D 변환과 브러시 편집본 저장
- 저장 지도 이름 변경과 삭제

반대로 지도 저장·변환 작업 또는 파이프라인 시작/중지 전환 중에는 Navigation 시작을
허용하지 않습니다. STOP과 목표 CANCEL은 로봇이나 센서가 offline이어도 정리를 위해
계속 사용할 수 있습니다. 이 기능은 경로 주변의 사람·장애물 확인과 물리 리모컨을
대체하지 않습니다.

대시보드에서는 다음 순서로 사용합니다.

1. Saved Maps에서 PCD를 2D로 변환하거나 관리 가능한 기존 2D 지도를 확인합니다.
2. Navigation에서 지도를 선택하고 필요하면 안전 범위 안의 파라미터를 적용합니다.
3. START로 공유 Hesai + FAST-LIO와 Nav2를 준비합니다.
4. 지도에서 `INITIAL POSE`를 드래그해 방향까지 지정하고 전송합니다.
5. 모든 readiness가 초록색일 때 `GOAL POSE`를 지정하고 물리 리모컨을 손에 든 상태에서
   확인 후 전송합니다.
6. 이상 동작 시 먼저 CANCEL 또는 STOP을 누르고 물리 리모컨으로 정지합니다.

파라미터 변경은 Navigation이 정지된 상태에서만 저장되며 다음 START부터 적용됩니다.
브라우저가 보내는 값은 27개 allowlist와 교차 조건을 다시 검사합니다. PDF의
`0.9 rad/s`, `2.0 rad/s²` 값은 현재 대시보드 하드 한계보다 높으므로 각각
`0.5 rad/s`, `1.2 rad/s²` 이하로 제한됩니다.

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
상태, FPS, 해상도와 인터페이스가 표시됩니다. GStreamer 수신·디코딩과 카메라
WebSocket은 Sensors 화면을 실제로 보는 클라이언트가 있을 때만 실행되고 마지막
클라이언트가 떠나면 멈추므로 Live Mapping의 대역폭과 CPU를 경쟁하지 않습니다.

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

실습실에서 사용한 Jetson, Go2, XT16의 주소와 Mac 인터넷 공유 시 주의사항은
[`docs/lab-network.md`](docs/lab-network.md)에 날짜와 확인 상태별로 기록합니다.

RealSense가 로봇 탑재 Jetson USB에 연결되어 있다면 같은 Jetson에서
realsense2_camera를 실행합니다. 표준 color, depth, points 토픽이 발견되면
카메라와 PointCloud 소스 목록에서 선택할 수 있습니다.

## 자동 시작

deploy의 두 서비스 예제는 기본적으로 `jetson_orin_nano` 사용자의
`/home/jetson_orin_nano/robot-scope` 설치를 가리킵니다. 다른 사용자명이나 경로를
사용하면 두 값을 먼저 수정한 뒤 systemd에 등록합니다. 제어를 사용하지 않으면
대시보드 서비스만 등록합니다.

일반 호스트 설정은 installer가 만드는 mode-0600
`~/.config/robot-scope/robot-scope.env`, 제어 secret은 별도 mode-0600 `control.env`에
둡니다. Service example은 일반 설정을 먼저, 제어 secret을 다음에 읽습니다. 두 파일을
Git에 커밋하지 않습니다.

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

Ubuntu host 부팅 시 Wi-Fi가 먼저 연결되면 `network-online.target`은 Go2 전용 랜선보다
먼저 완료될 수 있습니다. 서비스 예제는 이 순서를 다음과 같이 안전하게 처리합니다.

- 대시보드는 먼저 offline viewer로 시작하므로 Saved Maps와 진단 화면을 계속 사용할
  수 있습니다. `eno1`의 carrier와 정확한 `192.168.123.99/24`가 준비되면 기존
  Uvicorn 프로세스를 정상 종료하고 CycloneDDS를 전용 인터페이스로 다시 초기화합니다.
- 제어 브리지 서비스는 즉시 active 상태가 되지만 main supervisor가 같은 조건을
  기다리며 ROS participant나 publisher를 만들지 않습니다. 따라서 부팅 target을
  막거나 재시도를 소진하지 않으며, 조건이 맞지 않는 동안에는 제어 명령을 발행할 수
  없습니다.

인터페이스 이름이나 고정 주소를 바꾼 배포에서는 두 unit의
`ROBOT_SCOPE_GO2_INTERFACE`, `ROBOT_SCOPE_GO2_INTERFACE_CIDR`를 함께 수정합니다.
변경 후에는 `systemctl daemon-reload`가 필요합니다.

### 대시보드 서비스 재시작·중지 권한

Settings에서 대시보드 자체를 재시작하거나 중지하는 기능은 기본적으로 꺼져 있습니다.
운영체제 재부팅·종료 권한은 제공하지 않으며, root로 실행되는 저장소 스크립트도
허용하지 않습니다. 대신 sudoers에는 root 소유 `/usr/bin/systemctl`의 다음 두 argv만
정확히 허용합니다.

~~~text
/usr/bin/systemctl --no-block restart robot-scope.service
/usr/bin/systemctl --no-block stop robot-scope.service
~~~

Jetson에서 예제 문법을 먼저 검사한 뒤 root 소유 0440 파일로 설치합니다. 사용자명이나
unit 이름을 바꾸면 예제와 앱의 고정 allowlist를 함께 검토해야 하며 wildcard를 넣으면
안 됩니다.

~~~bash
sudo visudo -cf deploy/robot-scope-service-lifecycle.sudoers.example
sudo install -o root -g root -m 0440 \
  deploy/robot-scope-service-lifecycle.sudoers.example \
  /etc/sudoers.d/robot-scope-service-lifecycle
sudo visudo -cf /etc/sudoers.d/robot-scope-service-lifecycle
~~~

16자 이상의 임의 관리 토큰을 별도로 보관하고 SHA-256만 0600 `control.env`에 넣습니다.
원문 토큰을 환경 파일·Git·shell history에 저장하지 않습니다. `openssl rand -hex 32`로
원문을 한 번 생성해 안전한 암호 관리 도구에 보관한 뒤, 다음 no-echo 입력으로 64자리
SHA-256을 계산할 수 있습니다.

~~~bash
python3 -c 'import getpass,hashlib; print(hashlib.sha256(getpass.getpass("Admin token: ").encode()).hexdigest())'
~~~

~~~dotenv
ROBOT_SCOPE_SERVICE_LIFECYCLE_ENABLED=1
ROBOT_SCOPE_SERVICE_ADMIN_TOKEN_SHA256=<64자리-SHA-256>
~~~

초기 설정 반영은 SSH에서 기존 방식으로 `robot-scope.service`를 한 번 재시작합니다.
이후 웹 요청은 same-origin, `confirmed=true`, 매번 입력하는 관리 토큰과 idle preflight를
모두 통과해야 합니다. 수동 제어 lease, 모션 안전 구간, SOFTWARE STOP 래치, 활성
navigation/goal, 실행 중인 매핑 pipeline·저장·변환이 하나라도 있으면 HTTP 409로
거부됩니다. 요청 접수 후에도 고정 명령을 보내기 직전에 같은 상태를 다시 확인합니다.

재시작은 새 dashboard instance가 올라오면 상태가 초기화되고, 중지는 API 자체가
사라지는 것이 정상입니다. 기능을 끄려면 `control.env`의 enable 값을 `0`으로 바꾸고
sudoers 파일을 제거한 뒤 SSH에서 서비스를 재시작합니다.

## 설정

- config/go2.json: Go2 토픽 우선순위, 장착 오프셋, 저장 지도 폴더와 포인트 상한
- config/generic.json: 범용 ROS 2 토픽 우선순위와 저장 지도 설정
- config/turtlebot.json, config/so101.json: 해당 유형의 관측 전용 시작 프로필
- ROBOT_SCOPE_DIR: 프로젝트 루트 강제 지정
- ROBOT_SCOPE_PORT: HTTP 포트, 기본 8088
- ROBOT_SCOPE_ROBOT_IP: 네트워크 생존 확인 대상
- ROBOT_SCOPE_CAMERA_INTERFACE: Go2 영상 멀티캐스트를 받을 allowlist 유선 인터페이스
- ROBOT_SCOPE_OVERLAY: Generic 프로필에서 불러올 ROS workspace setup 파일
- ROBOT_SCOPE_WORKSPACE_ROOT: 외부 ROS workspace 공통 root, custom 값은 절대 경로만 허용
- ROBOT_SCOPE_LIVOX_SDK_PREFIX: Livox SDK2 private prefix, custom 값은 절대 경로만 허용
- ROBOT_SCOPE_PROFILE: run_generic.sh의 허용 프로필, generic | turtlebot | so-101
- ROBOT_SCOPE_MAPS_DIR: Go2 지도 저장 폴더
- ROBOT_SCOPE_CONTROL_ENABLED: `1`일 때만 서버 측 Go2 제어 활성화
- ROBOT_SCOPE_CONTROL_BRIDGE_KEY: 두 로컬 프로세스 사이 서명용 32바이트 이상 비밀키
- ROBOT_SCOPE_SERVICE_LIFECYCLE_ENABLED: `1`일 때만 서비스 관리 API opt-in
- ROBOT_SCOPE_SERVICE_ADMIN_TOKEN_SHA256: 매 요청 관리 토큰의 SHA-256, 원문 저장 금지

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
| GET /api/v1/pointcloud.bin | packed float32 최신 실시간 점군 |
| GET/POST /api/v1/pointcloud/settings | 실시간 포인트 예산 |
| GET /api/v1/map | 최신 OccupancyGrid |
| GET /api/v1/saved-maps | 저장 지도 목록 |
| GET /api/v1/saved-maps/{id}/data | 저장 지도 렌더링 데이터 |
| PATCH/DELETE /api/v1/saved-maps/{id} | 지도 이름 변경과 삭제 |
| POST /api/v1/saved-maps/{id}/convert-2d | 저장 PCD를 새 PGM+YAML로 비동기 변환 |
| POST /api/v1/saved-maps/{id}/edited-copy | RLE 브러시 편집을 새 2D 지도 복사본으로 저장 |
| POST /api/v1/mapping/start | 새 매핑 세션 시작 |
| POST /api/v1/mapping/stop | 매핑 세션 중지 |
| POST /api/v1/mapping/save | 현재 지도 저장 |
| GET /api/v1/navigation | Nav2 파이프라인, 센서, 위치추정과 목표 상태 |
| GET/PATCH /api/v1/navigation/parameters | revision 기반 안전 파라미터 조회와 변경 |
| POST /api/v1/navigation/start | 선택한 지도 revision으로 공유 파이프라인과 Nav2 시작 |
| POST /api/v1/navigation/stop | signed motion gate를 닫고 Nav2 정지 |
| POST /api/v1/navigation/initial-pose | known-free 셀의 초기 위치·방향 지정 |
| POST /api/v1/navigation/goal | 확인된 known-free 목표 전송 |
| POST /api/v1/navigation/cancel | 현재 목표 취소와 즉시 정지 |
| POST /api/v1/navigation/clear-costmaps | 정지 상태에서 local/global costmap 정리 |
| GET /api/v1/control | 제어 준비, lease, 브리지와 허용 모션 상태 |
| POST /api/v1/control/arm | 버튼 요청으로 단일 제어 lease 발급 |
| POST /api/v1/control/disarm | 제로 명령과 제어 lease 반납 |
| POST /api/v1/control/stop | lease와 무관한 대시보드 SOFTWARE STOP 래치 |
| POST /api/v1/control/estop/clear | 명시적 확인으로 대시보드 정지 해제 |
| GET /api/v1/system/service | dashboard service 관리 가능 여부, blocker와 최근 작업 상태 |
| POST /api/v1/system/service/restart | 확인·관리 토큰·idle preflight 후 dashboard만 재시작 |
| POST /api/v1/system/service/stop | 확인·관리 토큰·idle preflight 후 dashboard만 중지 |
| WS /api/v1/ws/camera | 카메라 스트림 |
| WS /api/v1/ws/pointcloud | 최신 프레임 우선 binary 점군 스트림 |
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
node --check robot_dashboard/static/navigation.js
node --check robot_dashboard/static/robot_profiles.js
node --check robot_dashboard/static/scene3d.js
~~~

## 프로젝트 구조

~~~text
config/             Go2, Generic, TurtleBot, SO-101 시작 프로필
deploy/             systemd 서비스 예제
docs/               설치, 의존성, 토폴로지, 진단과 업데이트 문서
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
- 서비스 재시작·중지는 same-origin만으로 인증하지 않고 별도 관리 토큰도 요구합니다.
  하지만 기본 HTTP에서는 토큰이 암호화되지 않으므로 반드시 도청 위험이 없는 신뢰
  유선 LAN에서만 사용하고, 범위가 넓은 네트워크에서는 TLS reverse proxy와 접근 제어를
  먼저 구성합니다.
- 네트워크 검색 API도 same-origin으로 제한하고, 서버가 직접 확인한 로컬 인터페이스의
  최대 /24만 검색합니다. 검색 결과는 장비 유형을 보증하지 않으므로 선택 전에 확인합니다.
- 인터넷이나 공용망에 노출하기 전 토큰 인증, TLS와 접근 제어를 추가해야 합니다.
- 비밀번호, SSH 키, 토큰, .env, rosbag, PCD와 생성 지도는 Git에 올리지 않습니다.
- 지도 삭제는 되돌릴 수 없으므로 대상 이름과 파일 묶음을 확인한 뒤 실행합니다.

## 라이선스

Robot Scope 코드는 MIT License로 배포합니다. 포함된 Go2 경량 모델은 Unitree
Robotics의 `unitree_ros/robots/go2_description`에서 변환했으며 BSD 3-Clause 원문과
변환 내역을 보존합니다. TurtleBot3 Burger 원본과 경량 파생물은 ROBOTIS
`turtlebot3`의 Apache-2.0, SO-101 원본과 경량 파생물은 TheRobotStudio
`SO-ARM100`의 Apache-2.0을 따릅니다. 각 모델의 고정 commit, SHA-256 manifest,
라이선스와 변환 내역은 `robot_dashboard/static/assets` 아래 README와 catalog에
기록합니다.

한 곳에서 확인할 수 있는 재배포 고지는
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)에 정리되어 있습니다. 저장소에
포함되지 않은 ROS workspace나 현장별 추가 artifact를 설치 이미지에 함께 넣는 경우에는
각 외부 구성 요소의 라이선스와 NOTICE 의무를 별도로 확인해야 합니다.
