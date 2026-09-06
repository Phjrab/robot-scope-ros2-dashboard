# Robot Scope — ROS2 Autonomous Mobile Robot Mapping, Navigation and Control Dashboard

Robot Scope는 ROS 2 기반 모바일 로봇의 센서 관측, 매핑, 위치추정, 자율 주행,
수동 원격 조작, 모션 안전과 런타임 운영을 한 브라우저에서 제공하는 웹 제어
패널입니다. 대시보드에서 허용된 Hesai + FAST-LIO 매핑 파이프라인을 시작하고,
현재 지도를 3D PCD와 선택적 2D PGM/YAML 형식으로 저장할 수도 있습니다.

Ubuntu 22.04 + ROS 2 Humble과 Ubuntu 24.04 + ROS 2 Jazzy를 지원합니다. Jazzy는
현재 `observer`/Generic 웹 계층까지 검증했고, Unitree Go2 + XT16 전체 경로는
Ubuntu 22.04/Humble의 Jetson Orin Nano에서 검증했습니다. Jetson 전용 애플리케이션은
아니며, 표준 sensor_msgs와 nav_msgs를 사용하는 다른 ROS 2 로봇에는 Generic 프로필을
사용할 수 있습니다.

웹/Generic 계층은 Ubuntu 22.04/Humble과 Ubuntu 24.04/Jazzy의 `x86_64`와 `arm64`를
지원합니다. Jazzy에서 `go2`, `go2-control`, `go2-xt16`, `go2-nav` 설치는 검증되지 않은
제조사 workspace 조합을 만들지 않도록 installer와 doctor가 차단합니다.

## 설치 및 운영 문서

| 문서 | 내용 |
|---|---|
| [현재 진행 현황과 향후 계획](docs/CURRENT_PROGRESS_AND_NEXT_STEPS_2026-09-01.md) | 완료·보류·차단 항목, 검증 기준선과 승인 게이트별 다음 순서 |
| [현재 아키텍처](docs/ARCHITECTURE.md) | subsystem 소유권, safety boundary, Phase 0 대비 구조와 남은 부채 |
| [대회용 분산 아키텍처](docs/COMPETITION_SYSTEM_ARCHITECTURE.md) | 내부 Jetson·외부 Orin·노트북 책임, 무선 데이터 경계와 WP 기준선 |
| [설치](docs/INSTALL.md) | `observer`, `go2`, `go2-control`, `go2-xt16`, `go2-nav` 모드와 스모크 테스트 |
| [의존성](docs/DEPENDENCIES.md) | 외부 ROS workspace, pin/라이선스 기록과 미포함 구성 요소 |
| [토폴로지](docs/TOPOLOGY.md) | 단일/두 호스트 배선, 서비스 역할과 관리망 분리 |
| [문제 해결](docs/TROUBLESHOOTING.md) | DDS, XT16, 저장, 카메라, 제어와 Nav 진단 순서 |
| [Cockpit 운영자 가이드](docs/COCKPIT_OPERATOR_GUIDE.md) | Layout, Xbox, STOP, Takeover, Mission과 대회 전후 절차 |
| [Cockpit 통합 Acceptance](docs/COCKPIT_ACCEPTANCE.md) | software evidence, 성능·soak·hardware 결과와 P0 |
| [AI 데이터셋](docs/AI_DATASET.md) | 듀얼 카메라 서버 수집, 저장 구조, 라벨링과 YOLO/UFLD 배포 판단 |
| [업데이트/롤백](docs/UPDATE_ROLLBACK.md) | 지도·상태 보존, fast-forward update와 안전 롤백 |
| [대회 release runbook](docs/WP08_RELEASE_LOCK_ROLLBACK_RUNBOOK.md) | offline bundle, Competition Lock, 시작·종료와 commit/model rollback |
| [하드웨어 인수 검증](docs/HARDWARE_ACCEPTANCE.md) | 읽기 전용 Jetson/Go2/XT16 점검, 감독 시나리오와 fail-stop 보고서 |
| [Track C2 controller odometry ADR](docs/ADR_COMPETITION_FASTLIO_CONTROLLER_ODOM.md) | wireless FAST-LIO 기반 명시적 controller odometry와 NG0/NG1 안전 경계 |
| [Track C2 no-goal acceptance](docs/TRACK_C2_COMPETITION_FASTLIO_NO_GOAL_ACCEPTANCE.md) | stationary 센서·controller odometry·NG0 실행 및 cleanup 판정 |
| [3D/2D map-family lineage ADR](docs/ADR_3D_2D_MAP_FAMILY_LINEAGE.md) | PCD와 파생 Nav2 지도 사이의 private exact-revision 계보 계약 |
| [Track D0 map lineage acceptance](docs/TRACK_D0_MAP_LINEAGE_ACCEPTANCE.md) | hardware-free 계보 저장·편집·snapshot 검증 결과와 D1 gate |
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
- Go2·RealSense·동시 선택형 서버 데이터셋 JPEG 수집과 웹 갤러리
- RViz처럼 회전·이동·확대할 수 있는 3D PointCloud 장면
- 같은 라이브 점군을 추가 전송 없이 위에서 투영하는 2D 매핑 화면
- Settings에서 Go2와 TurtleBot 유형 선택 및 제한된 로컬 네트워크 자동 검색
- 발견 후보의 IP, hostname, 인터페이스와 응답 지연을 확인한 뒤 연결 대상 선택
- 유형별 3D 모델 자동 전환: 공식 기반 Go2와 TurtleBot3 Burger 경량 모델
- Go2 12축 다리 관절, 몸통 자세와 이동 궤적 표시
- 실시간 점군 포인트 수를 10K~250K, 사용자 지정 또는 ALL SESSION으로 선택
- 저장 PCD를 미리보기 포인트 수 또는 ALL로 표시
- 대시보드 실행 중 Hesai + XT16 원시 점군 미리보기
- FAST-LIO 누적 매핑 시작·중지
- 현재 Laser_map을 PCD 또는 PCD + 2D 지도 묶음으로 안전하게 저장
- 저장 PCD를 높이 범위·해상도·2D 투영 점 밀도로 새 PGM/YAML 지도에 변환
- 저장 2D 지도를 브러시로 정리하고 원본을 보존한 새 복사본으로 저장
- 저장 지도 선택, 이름 변경, 삭제와 2D/3D 보기
- 버튼으로 여는 단일 제어 세션과 별도 ROS 2 명령 워치독
- 키보드, 화면 패드 또는 표준 Gamepad를 선택하는 Go2 주행 제어
- 서버 allowlist에 등록된 Go2 자세·제스처·보행 모드 실행
- Overview, Live Mapping, Saved Maps, Sensors, ROS Graph, Controls, Settings 메뉴
- 공용 Camera/LiDAR owner, Safety HUD, Map, Navigation과 Mission을 조합하고 별도 전체 작업창·선택적 native fullscreen을 제공하는 Cockpit
- exact map/annotation revision에 고정된 server-owned 다중 waypoint Mission
- Settings에서 로봇 작업을 중지하지 않고 생성하는 redacted·size-bounded 진단 ZIP
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
| 운영체제 | Ubuntu 22.04 (전체 경로), Ubuntu 24.04 (`observer`) |
| 아키텍처 | Jetson Orin Nano arm64 전체 경로 검증; x86_64/arm64 웹·Generic 지원 |
| ROS | ROS 2 Humble (전체 경로), ROS 2 Jazzy (`observer`) |
| DDS | Cyclone DDS |
| 로봇 | Unitree Go2 |
| 외장 LiDAR | Hesai PandarXT-16 |
| SLAM | FAST-LIO ROS 2 |
| 브라우저 주소 | http://JETSON_IP:8088 |

Go2·XT16·제어·Nav 스크립트는 ROS 2 Humble 전용입니다. Ubuntu 24.04/Jazzy에서는
Generic `observer` 실행 경로만 사용하세요.

## 빠른 설치

새 호스트에는 [설치 가이드](docs/INSTALL.md)의 mode별 절차를 권장합니다. 설치 helper와
하드웨어를 변경하지 않는 doctor는 다음 이름을 사용합니다.

Installer는 `/etc/os-release`를 읽어 Ubuntu 22.04에서는 Humble, Ubuntu 24.04에서는
Jazzy package manifest를 자동 선택합니다. Ubuntu 24.04에서는 `observer`만 허용합니다.

~~~bash
./scripts/install_ubuntu.sh --mode observer \
  --install-system-packages --install-service          # read-only dry-run
./scripts/install_ubuntu.sh --mode observer --apply \
  --install-system-packages --install-service          # explicit install
python3 scripts/robot_scope_doctor.py --mode observer
~~~

Installer는 target 사용자로 실행하며 root로 직접 실행하지 않습니다. `--apply`와
`--install-system-packages` 또는 `--install-service` opt-in을 함께 지정한 경우에만 해당
APT/systemd 작업에 sudo를 사용합니다. 설치한 unit은 기본적으로 enable/start하지 않으며,
사용자가 명시적으로 시작할 때만 실행됩니다. 기존 unit의 enable 상태도 임의로 바꾸지 않습니다.
설치 중에는 분리된 로봇 NIC를 경고로 허용하지만, 서비스 시작 전 별도 `doctor` 명령은
NIC와 고정 주소를 다시 엄격하게 검사합니다.

설치 후 실제 Jetson/Go2/XT16 인수 검증은 기본적으로 읽기 전용인 다음 도구로 기록합니다.
물리 동작과 fault injection은 자동 실행되지 않으며, 별도 안전 확인을 모두 제공한 운영자의
결과만 한 시나리오씩 기록합니다. 자세한 절차와 중단 조건은
[하드웨어 인수 검증 문서](docs/HARDWARE_ACCEPTANCE.md)를 확인하세요.

~~~bash
python3 scripts/robot_scope_acceptance.py --mode go2-nav
~~~

아래 명령은 Python 웹 계층의 수동 최소 설치입니다. Go2, XT16, 제어와 Nav2 전체 기능은
외부 의존성과 호스트별 설정이 추가로 필요합니다.

Ubuntu ROS host에서 저장소를 clone하고 ROS 패키지를 볼 수 있도록 system site packages를
포함한 가상환경을 만듭니다.

~~~bash
mkdir -p "$HOME/project"
git clone https://github.com/Phjrab/robot-scope-ros2-dashboard.git \
  "$HOME/project/robot-scope"
cd "$HOME/project/robot-scope"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
chmod +x scripts/*.sh scripts/check_pcd_bounds.py
~~~

Navigation 화면까지 사용할 Ubuntu 22.04/Humble ROS host에는 Nav2가 설치되어 있어야 합니다.
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
mkdir -p runtime/config
chmod 700 runtime runtime/config

openssl rand -hex 32
~~~

출력된 값을 사용해 `runtime/config/control.env`를 만들고 권한을 제한합니다.

~~~dotenv
ROBOT_SCOPE_CONTROL_ENABLED=1
ROBOT_SCOPE_CONTROL_BRIDGE_KEY=64자리_무작위_브리지_키
~~~

~~~bash
chmod 600 runtime/config/control.env
~~~

수동 실행은 터미널 두 개를 사용합니다. 환경 파일을 export한 뒤 브리지를 먼저,
대시보드를 다음에 실행합니다.

~~~bash
set -a
source runtime/config/control.env
set +a
./scripts/run_go2_control_bridge_humble.sh
~~~

~~~bash
set -a
source runtime/config/control.env
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
export ROS_DISTRO=jazzy  # Ubuntu 24.04; use humble on Ubuntu 22.04
export ROBOT_SCOPE_ROBOT_IP=192.168.1.20
export ROBOT_SCOPE_OVERLAY=$HOME/ros2_ws/install/setup.bash
export ROBOT_SCOPE_PROFILE=turtlebot  # generic | turtlebot
./scripts/run_generic.sh
~~~

Generic 프로필은 표준 sensor_msgs와 nav_msgs 타입을 기준으로 카메라, 점군,
IMU, 배터리, 관절, GPS, 거리 센서, odometry와 OccupancyGrid를 분류합니다.
표시할 토픽은 Settings의 Data Sources에서 변경할 수 있습니다.
`ROBOT_SCOPE_PROFILE`은 `generic` 또는 `turtlebot`만 허용합니다. TurtleBot은
`config/turtlebot.json`을 시작 프로필로 사용하며 Go2 제어는
활성화하지 않습니다.

Settings의 Connection에서 다음 표시 유형을 선택할 수 있습니다.

| 유형 | 검색 대상 | 3D 모델 | 현재 제어 범위 |
|---|---|---|---|
| Unitree Go2 | Go2 본체와 전용 유선망 | Unitree 공식 URDF 기반 경량 모델 | 안전 설정을 마친 경우 주행·허용 모션 |
| TurtleBot | 같은 LAN의 TurtleBot ROS 2 컴퓨터 | ROBOTIS 공식 TurtleBot3 Burger URDF/STL 기반 | 관측·센서·지도 표시 |

지원 범위는 고정된 capability metadata로도 제공합니다. Go2는 `observability`,
`camera`, `pointcloud`, `mapping`, `localization`, `navigation`, `manual_control`,
`autonomous_control`의 기준 구현입니다. 현재 TurtleBot과 Generic 프로필은
`observability`, `camera`, `pointcloud`만 지원하며 나머지는 fail-closed입니다.
이 값은 제품 지원 선언이며 현재 로봇 연결 상태나 센서 readiness를 뜻하지 않습니다.
`GET /api/v1/robots/types`는 선택 가능한 유형의 선언을, health 응답의
`runtime_profile.capabilities`와 `selected_profile.capabilities`는 실제 시작 프로필과
화면에서 선택한 프로필을 구분해 반환합니다. 설정 파일이나 ROS graph는 capability를
추가로 부여할 수 없습니다.

TurtleBot은 ROBOTIS `turtlebot3_description`의 Burger 모델을 고정된 upstream commit에서
가져옵니다. 원본 URDF와 visual STL은 바이트 그대로 포함하며, 브라우저는 그 표면을
결정론적으로 경량화한 JSON을 표시합니다. 현재 기본 URDF 자세로 표시되고 각 로봇의
실시간 joint topic 매핑은 포함하지 않습니다. 경량 파생물은 시뮬레이션, 충돌 검사,
제어 또는 제작 치수로 사용하지 마세요.

## 대시보드 사용 방법

### Settings: 로봇 찾기와 모델 선택

1. Connection에서 Go2 또는 TurtleBot을 선택합니다.
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

Go2 전용 인터페이스로 대시보드가 시작되면 Hesai driver와 XT16 bridge는 별도
미리보기 process group으로 실행됩니다. 따라서 매핑 세션이 `IDLE`이어도
`/lidar_points`와 `/velodyne_points`를 볼 수 있습니다. `새 맵 시작`은 이 두 publisher를
재사용해 FAST-LIO만 새 accumulator로 시작하고, `매핑 중지`는 FAST-LIO만 종료하므로
원시·변환 점군 미리보기는 유지됩니다. 대시보드를 종료하면 미리보기 process group도
함께 정리됩니다. 로봇 전용 NIC가 없는 offline viewer나 Generic 프로필에서는 미리보기를
자동 실행하지 않습니다.

FAST-LIO 없이 볼 수 있는 `/lidar_points`와 `/velodyne_points`는 센서 기준 현재 scan이며,
지도 좌표로 누적된 결과가 아닙니다. `/cloud_registered`, `/Laser_map`, `/Odometry`와 지도
저장은 FAST-LIO 매핑 세션이 실행 중일 때만 제공됩니다.

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

대시보드는 먼저 저장소의 고정 preview supervisor를 실행하고, 새 맵 시작 버튼은
FAST-LIO 전용 고정 런처만 실행합니다.

~~~bash
./scripts/start_xt16_preview_humble.sh
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

관리 가능한 2D 지도에는 원본 PGM/YAML을 바꾸지 않는 별도 annotation layer를 저장할
수 있습니다. Navigation의 `POI, Home & safety zones` 패널에서 다음을 지도 위에
그립니다.

- POI, HOME, DOCK, INSPECTION POINT: known-free 셀의 위치와 도착 방향
- KEEP OUT, SLOW, WAIT ZONE: 지도 경계 안의 3–64 꼭짓점 영역

HOME은 지도마다 하나이며, DOCK은 충전 동작이 아니라 접근 위치 의미입니다. 주석은
지도 ID/revision과 자체 annotation revision에 함께 고정되고, 저장 시 두 revision을
검사한 뒤 private sidecar 파일로 원자 게시됩니다. 지도 이름 변경·삭제에도 같은
sidecar가 rollback-safe하게 포함됩니다.

현재 KEEP OUT·SLOW·WAIT 영역은 **표시와 향후 미션 선택용**입니다. Nav2 costmap이나
속도 제어를 자동으로 바꾸지 않습니다. 저장된 point의 `GO`는 현재 지도와 annotation
revision을 모두 재검사한 뒤 기존 known-free/robot-radius/Navigation readiness 목표
경로를 그대로 사용합니다.

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

같은 화면의 별도 3D 패널은 Settings에서 선택한 Go2 또는 TurtleBot 모델을
표시합니다. Go2 관절 데이터는 선택 프로필과 runtime이 일치하고 최신 샘플이 있을 때만
반영하며, Navigation의 map 좌표 위치와 다른 telemetry 자세를 섞지 않습니다. `XYZ`
버튼으로 좌표축만 표시하거나 숨길 수 있고 선택은 해당 브라우저에 저장됩니다.

Mapping과 Navigation 콘솔은 사용자가 로그 맨 아래에 있을 때만 새 항목을 따라갑니다.
과거 로그를 보기 위해 위로 스크롤하면 갱신 중에도 현재 위치를 보존하며, Navigation의
`AUTO-SCROLL`을 다시 켜면 명시적으로 최신 줄로 이동합니다.

내비게이션 시작 시 Hesai + XT16 bridge + FAST-LIO가 이미 대시보드 소유 process로
실행 중이면 그대로 공유합니다. 파이프라인이 idle/failed 상태면 동일한 allowlisted
매핑 시작 경로를 백그라운드에서 자동 실행하고 센서가 안정화된 뒤 Nav2를 이어서
시작합니다. 사용자는 Live Mapping 화면으로 이동하거나 START를 다시 누를 필요가 없고,
Navigation 패널에서 위치추정 준비, 센서 대기, Nav2 시작과 활성화 단계를 확인하고
진행 중에도 `STOP STARTUP`으로 취소할 수 있습니다. 이 shared pipeline이
`/velodyne_points`와 `/Odometry`를 공급하고 navigation runtime이 고정 `/scan`과
`odom -> base_link` TF를 만듭니다. Navigation이 직접 시작한 Hesai + FAST-LIO는
Navigation STOP, 시작 실패 또는 대시보드 정상 종료 때 동일한 mapping job ID를 확인한
후 함께 정리합니다. 반대로 사용자가 Live Mapping에서 먼저 시작한 파이프라인은
Navigation이 재사용만 하며 STOP 때 종료하지 않으므로, 수동 매핑 작업을 침범하지
않습니다.

같은 Navigation 화면의 `Localization & TF health`는 PointCloud/odometry
주파수·지터·age, 두 동적 TF age, FAST-LIO jump, scan point, 목표 진행률·정체 시간과
costmap clear 횟수를 하나의 가짜 점수 없이 표시합니다. 상태는 `READY`, `DEGRADED`,
`STALE`, `DISCONTINUITY`, `FRAME_MISMATCH`, `CALIBRATION_SUSPECTED`,
`UNAVAILABLE` 중 하나이며 원인 코드와 `config/go2.json`의 임계값 근거를 함께
보여줍니다. `READY`는 stale 이후 실제 cloud/odometry 시퀀스가 연속으로 전진해야
복구됩니다. 옆의 Calibration Assistant는 frame, extrinsic, static TF, clock domain과
3D 모델 방향을 읽기 전용으로 안내할 뿐 설정을 자동 변경하지 않습니다.

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
3. START를 한 번 눌러 공유 Hesai + FAST-LIO와 Nav2를 준비하고 같은 패널의 단계 표시를
   확인합니다.
4. 지도에서 `INITIAL POSE`를 드래그해 방향까지 지정하고 전송합니다.
5. 모든 readiness가 초록색일 때 `GOAL POSE`를 지정하고 물리 리모컨을 손에 든 상태에서
   확인 후 전송합니다.
6. 반복 목적지가 필요하면 Nav2를 STOP한 상태에서 지도 주석을 저장하고, 다시 시작한
   뒤 저장된 POI/HOME/DOCK/INSPECTION POINT의 `GO`를 사용할 수 있습니다.
7. 이상 동작 시 먼저 CANCEL 또는 STOP을 누르고 물리 리모컨으로 정지합니다.

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

### 로봇 탑재 Jetson의 RealSense 컬러 영상

RealSense가 `unitree@192.168.123.18`의 USB에 연결된 참조 배선에서는 ROS 영상 토픽을
로봇망 전체에 송출하지 않고, 그 Jetson에서 컬러 영상 전용 MJPEG relay를 실행합니다.
Relay는 실제 D435i RGB 장치 계약인
`/dev/v4l/by-id/usb-Intel_R__RealSense_TM__Depth_Camera_435i_*-video-index0`가
정확히 하나일 때만 `192.168.123.18:8090`에 bind합니다. 제공하는 경로는
`/health`, `/stream`뿐입니다.
영상 `/stream`은 고정 dashboard NIC `192.168.123.99`에서만 읽을 수 있고,
`/health`도 relay 자신·loopback·dashboard host만 허용합니다.

~~~text
RealSense USB --> robot-side Jetson GStreamer --> fixed HTTP MJPEG :8090
                                                   |
Dashboard Jetson <---------------------------------+
~~~

640×480, 최대 15fps, JPEG 품질 72로 제한하며 최대 viewer는 4개입니다. 첫 viewer가
연결될 때만 GStreamer producer가 시작되고 마지막 viewer가 떠난 3초 뒤 멈춥니다. 각
viewer에는 누적 queue가 아닌 최신 프레임만 전달하므로 느린 연결이 전체 영상을 지연시키지
않습니다. Dashboard의 단일/2화면 선택은 이 relay를 직접 브라우저에 공개하지 않고
Dashboard host가 고정 `/stream`을 가져오는 구조입니다.

로봇 탑재 Jetson에서 장치와 plugin을 먼저 확인하고 root 소유 경로에 설치합니다.

~~~bash
ls -l /dev/v4l/by-id/usb-Intel_R__RealSense_TM__Depth_Camera_435i_*-video-index0
gst-inspect-1.0 nvjpegenc || gst-inspect-1.0 jpegenc
sudo install -d -o root -g root -m 0755 /usr/local/libexec/robot-scope
sudo install -o root -g root -m 0755 scripts/realsense_mjpeg_relay.py \
  /usr/local/libexec/robot-scope/realsense_mjpeg_relay.py
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-realsense-camera.service.example \
  /etc/systemd/system/robot-scope-realsense-camera.service
sudo systemctl daemon-reload
~~~

설치만으로 시작 정책을 정하지는 않습니다. 다른 프로젝트도 사용하는 relay host라면 A를,
Robot Scope 전용 relay host로 부팅할 때마다 준비해야 한다면 B를 하나만 선택합니다.
`enable --now`는 현재 서비스를 시작하는 동시에 다음 부팅의 자동 시작도 활성화합니다.

~~~bash
# A. 수동 실행 전용: 다음 부팅에는 자동 시작하지 않음
sudo systemctl disable --now robot-scope-realsense-camera.service
sudo systemctl start robot-scope-realsense-camera.service

# B. 전용 relay host: 지금 시작하고 다음 부팅부터 자동 시작
sudo systemctl enable --now robot-scope-realsense-camera.service
~~~

이미 active인 서비스를 새 파일로 업데이트했다면 `enable --now`만으로 기존 프로세스가
교체되지 않습니다. enable 상태를 바꾸지 말고 `daemon-reload` 뒤 명시적으로 restart합니다.
그 다음 기대한 시작 정책과 현재 상태를 각각 확인합니다.

~~~bash
sudo systemctl restart robot-scope-realsense-camera.service
systemctl is-enabled robot-scope-realsense-camera.service  # A: disabled, B: enabled
systemctl is-active robot-scope-realsense-camera.service   # 시작 후: active
curl -fsS http://192.168.123.18:8090/health
~~~

서비스는 `unitree` 사용자와 `video` 보조 그룹으로 실행하고 capability를 부여하지 않습니다.
스크립트는 사용자 쓰기 가능한 경로에서 실행하지 마세요. 현재 구현은 컬러 영상 전용이며
depth/point cloud는 relay하지 않습니다. `/health`의 `idle`은 viewer가 없다는 뜻일 뿐,
장치에서 JPEG가 생성된다는 검증은 아닙니다. 실제 영상 검증은 고정 dashboard host
`192.168.123.99`에서 `/stream`을 열어 완전한 JPEG 한 장 이상을 확인합니다.

~~~bash
relay_capture=/tmp/robot-scope-realsense-stream.mjpeg
curl -fsS --max-time 5 http://192.168.123.18:8090/stream -o "$relay_capture"
relay_curl_status=$?
test "$relay_curl_status" -eq 0 -o "$relay_curl_status" -eq 28
python3 - <<'PY'
from pathlib import Path

payload = Path("/tmp/robot-scope-realsense-stream.mjpeg").read_bytes()
start = payload.find(b"\xff\xd8")
end = payload.find(b"\xff\xd9", start + 2)
if start < 0 or end < 0:
    raise SystemExit("no complete JPEG frame received")
print(f"complete JPEG frame: {end + 2 - start} bytes")
PY
rm -f "$relay_capture"
curl -fsS http://127.0.0.1:8088/api/v1/cameras
~~~

지속 스트림을 5초 뒤 끊기 때문에 curl 종료 코드 28은 위 절차에서만 정상으로 허용합니다.
그 뒤 Sensors에서 RealSense를 단일 화면으로 선택하고, 2화면 모드에서도 Go2와 동시에
`LIVE`가 되는지 확인합니다. `/health`나 camera catalog만으로 프레임 정상을 판정하지 마세요.

### 주행 이미지 데이터셋 수집

Sensors의 **Dataset Capture**는 브라우저의 1회 `화면 캡처`와 별개입니다. Go2,
RealSense 또는 두 카메라를 선택해 `START SERVER CAPTURE`를 누르면 대시보드 서버가
고정된 `runtime/datasets` 아래에 JPEG와 JSON metadata를 저장합니다. Controls나
Navigation으로 이동하거나 브라우저를 닫아도 서버 수집은 계속되며, 끝날 때 반드시
`STOP & FINALIZE`로 manifest를 마무리합니다. 수집 중에는 실수로 세션을 절단하지 않도록
대시보드 서비스 restart/stop이 차단됩니다.

`웹에서 폴더 열기`는 원격 Jetson의 OS 파일 관리자를 실행하지 않습니다. 같은 출처의
대시보드 갤러리에서 한 페이지에 최대 24개 샘플을 보여 주고 `NEWER`·`OLDER`로 세션
전체를 탐색합니다. 변경 없는 페이지는 10초 목록 갱신 때 JPEG를 다시 다운로드하지
않습니다. 화면에는 대시보드 호스트의 실제 저장 경로도 표시됩니다. 저장 위치를
바꿀 때는 HTTP 요청이 아니라 mode-0600 환경 파일에서 절대 경로만 지정합니다.

~~~text
ROBOT_SCOPE_DATASET_DIR=/absolute/path/to/robot-scope-datasets
~~~

기본 안전 한도는 세션당 20 GiB, 파일시스템 여유 공간 5 GiB, JPEG 하나당
4 MiB입니다. 한도를 넘거나 여유 공간을 유지할 수 없으면 수집을 fail-closed로
중지하고 화면에 오류를 표시합니다. 세션 한도와 여유 공간 기준은 Dataset Capture 상태에서
확인할 수 있습니다. Custom 경로를 checkout 안에 두면 기본 `/runtime/` ignore가 적용되지
않을 수 있으므로, Git 추적 대상 밖의 경로를 쓰거나 별도 ignore를 추가합니다.

저장 직후 파일은 라벨 없는 원본 이미지입니다. YOLO detection에는 bounding box/class,
UFLD에는 lane annotation을 별도로 작성해야 지도학습에 쓸 수 있습니다. 자세한 수집 구조,
Jetson AI 사양과 권장 학습/추론 분리는 [AI 데이터셋 가이드](docs/AI_DATASET.md)를 봅니다.


## 수동 실행과 선택적 자동 시작

deploy의 두 서비스 예제는 기본적으로 `jetson_orin_nano` 사용자의
`/home/jetson_orin_nano/project/robot-scope` 설치를 가리킵니다. 다른 사용자명이나 경로를
사용하면 두 값을 먼저 수정한 뒤 systemd에 등록합니다. 제어를 사용하지 않으면
대시보드 서비스만 등록합니다.

아래 project-local service example은 일반 호스트 설정을 mode-0600
`runtime/config/robot-scope.env`, 제어 secret을 같은 프로젝트의 별도 mode-0600
`runtime/config/control.env`에서 읽습니다. Portable installer가 기존 XDG config 경로를
사용하도록 렌더한 설치는 그 경로를 계속 따릅니다. 두 파일은 모두 Git에 커밋하지 않습니다.

~~~bash
sudo cp deploy/robot-scope.service.example /etc/systemd/system/robot-scope.service
sudo cp deploy/robot-scope-control-bridge.service.example \
  /etc/systemd/system/robot-scope-control-bridge.service
sudo systemctl daemon-reload
sudo systemctl start robot-scope.service
~~~

공용 개발 호스트에서는 위처럼 unit을 disabled 상태로 두고 필요할 때만 시작합니다. 전용
Robot Scope 호스트에서만 부팅 자동 시작이 필요할 경우, 준비 상태와 충돌 가능성을 검토한
뒤 명시적으로 `sudo systemctl enable robot-scope.service`를 실행합니다. 제어 브리지는 별도
서비스이므로 자동 시작이 정말 필요한 전용 제어 호스트에서만 따로 enable합니다.

Uvicorn worker는 반드시 하나만 사용합니다. 여러 worker는 ROS 구독과 매핑 상태
관리뿐 아니라 단일 제어 lease를 중복시킵니다. 실제 제어 환경 파일은 0600 권한으로
유지하며 두 서비스가 동일한 파일을 읽게 합니다.

서비스를 명시적으로 enable한 Ubuntu host에서 부팅 시 Wi-Fi가 먼저 연결되면
`network-online.target`은 Go2 전용 랜선보다
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
sudo install -o root -g root -m 0440 \
  deploy/robot-scope-service-lifecycle.sudoers.example \
  /etc/sudoers.d/.robot-scope-service-lifecycle.new
sudo visudo -cf /etc/sudoers.d/.robot-scope-service-lifecycle.new
sudo mv /etc/sudoers.d/.robot-scope-service-lifecycle.new \
  /etc/sudoers.d/robot-scope-service-lifecycle
sudo visudo -cf /etc/sudoers.d/robot-scope-service-lifecycle
~~~

~~~dotenv
ROBOT_SCOPE_SERVICE_LIFECYCLE_ENABLED=1
~~~

초기 설정 반영은 SSH에서 기존 방식으로 `robot-scope.service`를 한 번 재시작합니다.
이후 웹 요청은 same-origin, Settings 확인 체크, 브라우저 확인 대화상자,
`confirmed=true`, idle preflight를 모두 통과해야 합니다. 수동 제어 lease, 모션 안전 구간, 활성
navigation/goal, 실행 중인 매핑 pipeline·저장·변환이 하나라도 있으면 HTTP 409로
거부됩니다. 요청 접수 후에도 고정 명령을 보내기 직전에 같은 상태를 다시 확인합니다.
SOFTWARE STOP 래치는 이미 모든 lease와 모션 명령을 폐기한 안전 정지 상태이므로 서비스
재시작을 막지 않으며, 재시작 후에도 제어는 자동 ARM되지 않습니다.
별도 관리 키를 요구하지 않으므로 이 기능은 신뢰할 수 있는 직접 LAN에서만 활성화하고,
공유망에서는 방화벽·VPN 또는 TLS reverse proxy 접근 제어를 먼저 구성합니다.

재시작은 새 dashboard instance가 올라오면 상태가 초기화되고, 중지는 API 자체가
사라지는 것이 정상입니다. 기능을 끄려면 `control.env`의 enable 값을 `0`으로 바꾸고
sudoers 파일을 제거한 뒤 SSH에서 서비스를 재시작합니다.

### 대시보드에서 제어 브리지 시작·중지

Controls 화면에서 `robot-scope-control-bridge.service`만 시작·중지하는 기능은 대시보드
자체 lifecycle과 독립된 opt-in입니다. unit 이름, 임의 argv, shell, 환경 변수, force 또는
restart를 HTTP 요청으로 전달할 수 없습니다. 먼저 위의 제어 브리지 unit을 설치한 뒤,
다음 두 명령만 허용하는 별도 sudoers 예제를 검사·설치합니다.

~~~text
/usr/bin/systemctl --no-block start robot-scope-control-bridge.service
/usr/bin/systemctl --no-block stop robot-scope-control-bridge.service
~~~

~~~bash
sudo install -o root -g root -m 0440 \
  deploy/robot-scope-control-bridge-lifecycle.sudoers.example \
  /etc/sudoers.d/.robot-scope-control-bridge-lifecycle.new
sudo visudo -cf /etc/sudoers.d/.robot-scope-control-bridge-lifecycle.new
sudo mv /etc/sudoers.d/.robot-scope-control-bridge-lifecycle.new \
  /etc/sudoers.d/robot-scope-control-bridge-lifecycle
sudo visudo -cf /etc/sudoers.d/robot-scope-control-bridge-lifecycle
~~~

mode-0600 `runtime/config/control.env`에 별도 enable을 추가하고, 최초 한 번은 SSH에서
대시보드만 재시작해 설정을 반영합니다. 이 값은 제어 기능의
`ROBOT_SCOPE_CONTROL_ENABLED`나 대시보드 자체 lifecycle enable을 대신하지 않습니다.

~~~dotenv
ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_ENABLED=1
~~~

이후 Controls 화면의 Bridge Service 카드에서 시작 또는 중지를 확인할 수 있습니다.
GET 상태 조회는 읽기 전용이며, start/stop은 same-origin과 `confirmed=true`를 요구합니다.
시작은 대시보드 제어 전송이 설정되고 현재 Go2가 시작 시 고정된 IP·프로필과 일치할 때만
허용됩니다. 시작·중지 모두 수동 lease, one-shot 동작 안전 구간, navigation/goal 또는
대시보드 자체 lifecycle이 활성 상태이면 HTTP 409로 거부되며 force 우회는 없습니다.
Mapping과 Dataset Capture는 별도 프로세스·소유권이므로 브리지 lifecycle을 막지 않습니다.

중지는 로봇이나 LowState가 offline이어도 실행할 수 있습니다. systemd가 inactive가 된
뒤에도 마지막 인증된 브리지 상태가 0.75초 freshness 경계를 지나 stale될 때까지 화면은
전환 중으로 유지됩니다. systemd unit 조회가 실패하거나 `LoadState=loaded`를 확인할 수
없으면 start와 stop을 모두 fail-closed로 비활성화합니다. 대시보드 unit의 enable/disabled
상태와 기존 Settings lifecycle은 이 기능으로 변경되지 않습니다. 제어 브리지 unit도 이
API가 `start`와 `stop`만 실행하므로 `UnitFileState`를 바꾸지 않습니다. 다른 프로젝트와
공유하는 Jetson에서는 다음 결과가 `disabled`인지 설치 전후로 확인하고 그대로 유지합니다.

~~~bash
systemctl is-enabled robot-scope-control-bridge.service  # expected: disabled
~~~

롤백은 먼저 `control.env` 값을 `0`으로 바꾸고 SSH에서 대시보드를 재시작한 다음,
sudoers를 복구 가능한 위치로 이동합니다. 제어 브리지 unit 자체와 데이터는 삭제되지
않습니다.

~~~bash
sudo mv /etc/sudoers.d/robot-scope-control-bridge-lifecycle \
  /root/robot-scope-control-bridge-lifecycle.sudoers.backup
sudo visudo -c
~~~

되돌리려면 백업을 원래 경로에 root:root 0440으로 다시 설치하고 `visudo -cf`로 검사한 뒤
enable 값을 `1`로 복원하고 대시보드를 재시작합니다.

### SSH에서 한 명령으로 대시보드 시작·종료

설치 프로그램에 `--install-service`를 지정하면 고정 unit만 다루는
`/usr/local/bin/robot-scope-dashboard`도 root 소유 0755로 설치합니다. 기존 배포에는
다음처럼 설치합니다.

~~~bash
sudo install -o root -g root -m 0755 \
  scripts/robot_scope_dashboard_service.py \
  /usr/local/bin/robot-scope-dashboard
~~~

비대화식 SSH 명령은 위의 기존 lifecycle sudoers 두 명령만 재사용합니다. `start`는 inactive
unit에도 동작하는 exact `systemctl --no-block restart robot-scope.service`로 구현되며,
helper 자체나 wildcard에는 sudo 권한을 주지 않습니다.

설치 후 SSH 세션에서는 다음 명령만 입력하면 됩니다.

~~~bash
robot-scope-dashboard start
robot-scope-dashboard stop
robot-scope-dashboard restart
robot-scope-dashboard status
robot-scope-dashboard logs
~~~

`start`와 `restart`는 새 systemd 실행 ID가 active가 될 때까지 확인하고, `stop`은 inactive를
확인합니다. `start`, `restart`와 실행 중인 `status`는 준비 확인 후 현재 SSH가 접속한
관리망 주소와 설정 포트를 조합한 브라우저 URL도 터미널에 출력합니다. 예:
`[Robot Scope] dashboard URL: http://192.168.50.10:8088`. 다중 NIC host는
`ROBOT_SCOPE_DASHBOARD_ADDRESS`에 운영자가 사용할 private/link-local IPv4를 지정하면
installer가 root 소유 고정 설정으로 설치하고 `start`, `restart`, `status` 모두 같은 URL을
출력합니다. 값이 없을 때만 현재 SSH server 주소와 local route 순서로 자동 선택합니다.
60초 안에 전환되지 않으면
강제 종료나 재시도를 하지 않습니다. 실행 중인
제어 lease, 매핑, 저장, navigation 또는 안전 래치가 있으면 로컬 관리 API preflight가
명령 전송을 거부합니다. 이 SSH 도구는 관리용 경로이므로 로봇 작업이 idle일 때 사용하며,
control bridge·XT16 relay·ROS 작업·호스트 재부팅/종료는 건드리지 않습니다. 로봇 NIC가
분리된 경우에도 offline viewer가 정상 실행되면 dashboard service 시작은 성공입니다.
CLI preflight와 UI 작업 시작은 하나의 서버 transaction이 아니므로 명령이 끝날 때까지
다른 사용자가 UI에서 새 제어·매핑·Nav 작업을 시작하면 안 됩니다.
`ROBOT_SCOPE_PORT`를 기본 8088에서 바꾸면 installer가 같은 값을 root 소유 operator port
설정에도 기록합니다. 기존 배포에서 포트만 수동 변경했다면 환경 파일을 확인한 뒤
`install_ubuntu.sh --apply --install-service`로 helper 설정을 다시 설치합니다.

## 설정

- config/go2.json: Go2 토픽 우선순위, 장착 오프셋, 저장 지도 폴더와 포인트 상한
- config/generic.json: 범용 ROS 2 토픽 우선순위와 저장 지도 설정
- config/turtlebot.json: TurtleBot 관측 전용 시작 프로필
- ROBOT_SCOPE_DIR: 프로젝트 루트 강제 지정
- ROBOT_SCOPE_PORT: HTTP 포트, 기본 8088
- ROBOT_SCOPE_DASHBOARD_ADDRESS: 다중 NIC host에서 터미널에 출력할 고정 private/link-local IPv4
- ROBOT_SCOPE_ROBOT_IP: 네트워크 생존 확인 대상
- ROBOT_SCOPE_CAMERA_INTERFACE: Go2 영상 멀티캐스트를 받을 allowlist 유선 인터페이스
- ROBOT_SCOPE_OVERLAY: Generic 프로필에서 불러올 ROS workspace setup 파일
- ROBOT_SCOPE_WORKSPACE_ROOT: 외부 ROS workspace 공통 root, custom 값은 절대 경로만 허용
- ROBOT_SCOPE_RUNTIME_DIR: Git에서 제외되는 상태·로그·데이터의 프로젝트 로컬 root
- ROBOT_SCOPE_DATASET_DIR: 서버 카메라 데이터셋 저장 root, 기본 `runtime/datasets`
- ROBOT_SCOPE_LIVOX_SDK_PREFIX: Livox SDK2 private prefix, custom 값은 절대 경로만 허용
- ROBOT_SCOPE_PROFILE: run_generic.sh의 허용 프로필, generic | turtlebot
- ROBOT_SCOPE_MAPS_DIR: Go2 지도 저장 폴더
- ROBOT_SCOPE_CONTROL_ENABLED: `1`일 때만 서버 측 Go2 제어 활성화
- ROBOT_SCOPE_CONTROL_BRIDGE_KEY: 두 로컬 프로세스 사이 서명용 32바이트 이상 비밀키
- ROBOT_SCOPE_SERVICE_LIFECYCLE_ENABLED: `1`일 때만 서비스 관리 API opt-in
- ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_ENABLED: `1`일 때만 고정 제어 브리지 start/stop API opt-in

## 주요 API

| 경로 | 용도 |
|---|---|
| GET /api/v1/health | 에이전트와 로봇 연결 상태 |
| GET /api/v1/state | 센서, 카메라, 매핑 요약 |
| GET /api/v1/cameras | Go2·RealSense 고정 카메라 catalog와 소스별 상태 |
| GET /api/v1/datasets/capture | 서버 데이터셋 캡처와 디스크 상태 |
| POST /api/v1/datasets/capture/start | 고정 카메라 선택과 저장률로 서버 캡처 시작 |
| POST /api/v1/datasets/capture/stop | 일치하는 활성 세션을 중지하고 manifest 마무리 |
| GET /api/v1/datasets | 완성·복구된 데이터셋 세션 목록 |
| GET /api/v1/datasets/{id}?before={exclusive-index}&limit=24 | 세션의 최대 24개 샘플과 NEWER·OLDER cursor metadata |
| GET /api/v1/datasets/{id}/samples/{index}/{source}.jpg | 저장된 고정 소스 JPEG 한 장 |
| GET /api/v1/control/bridge-service | 고정 제어 브리지 systemd 상태와 안전 preflight |
| POST /api/v1/control/bridge-service/start | 확인 후 고정 제어 브리지 unit 시작 |
| POST /api/v1/control/bridge-service/stop | 확인 후 고정 제어 브리지 unit 안전 중지 |
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
| POST /api/v1/navigation/start | 선택한 지도 revision으로 공유 파이프라인과 Nav2의 백그라운드 시작 예약(202) |
| POST /api/v1/navigation/stop | 진행 중인 시작을 취소하거나 signed motion gate와 Nav2를 닫고 Nav 소유 파이프라인 정리 |
| POST /api/v1/navigation/initial-pose | known-free 셀의 초기 위치·방향 지정 |
| POST /api/v1/navigation/goal | 확인된 known-free 목표 전송 |
| POST /api/v1/navigation/cancel | 현재 목표 취소와 즉시 정지 |
| POST /api/v1/navigation/clear-costmaps | 정지 상태에서 local/global costmap 정리 |
| GET/POST /api/v1/missions | bounded revision-pinned Mission 목록과 생성 |
| GET /api/v1/missions/{id} | server-owned current waypoint와 bounded progress log |
| POST /api/v1/missions/{id}/{start,pause,resume,skip,retry,abort} | explicit Mission state transition |
| GET /api/v1/control | 제어 준비, lease, 브리지와 허용 모션 상태 |
| POST /api/v1/control/arm | 버튼 요청으로 단일 제어 lease 발급 |
| POST /api/v1/control/disarm | 제로 명령과 제어 lease 반납 |
| POST /api/v1/control/stop | lease와 무관한 대시보드 SOFTWARE STOP 래치 |
| POST /api/v1/control/estop/clear | 명시적 확인으로 대시보드 정지 해제 |
| DELETE /api/v1/robot | 선택 대상과 Go2 제어 권한 해제(네트워크·전원은 유지) |
| GET /api/v1/system/service | dashboard service 관리 가능 여부, blocker와 최근 작업 상태 |
| POST /api/v1/system/service/restart | 확인·idle preflight 후 dashboard만 재시작 |
| POST /api/v1/system/service/stop | 확인·idle preflight 후 dashboard만 중지 |
| POST /api/v1/system/diagnostics/export | 로봇 작업 lock 없이 deterministic redacted 진단 ZIP 생성 |
| WS /api/v1/ws/camera?source_id={id} | 선택한 고정 카메라 스트림 (`go2_front`, `realsense_color`) |
| WS /api/v1/ws/cameras/{id} | 위와 같은 소스별 카메라 WebSocket 경로 |
| WS /api/v1/ws/pointcloud | 최신 프레임 우선 binary 점군 스트림 |
| WS /api/v1/ws/joints | Go2 관절 스트림 |
| WS /api/v1/ws/pose | 로봇 자세 스트림 |
| WS /api/v1/ws/control | 순서 보장된 주행·heartbeat·허용 모션 명령 |
| /docs | FastAPI OpenAPI 문서 |

## 테스트

ROS가 없는 개발 PC에서도 핵심 로직 테스트를 실행할 수 있습니다.

~~~bash
python3 -m unittest discover -s tests -v
npm run test:unit
npm run test:cockpit
node scripts/check_frontend_syntax.mjs
~~~

실제 브라우저에서 프런트엔드 계약을 확인하는 테스트도 ROS와 로봇 없이 실행할 수
있습니다. 고정된 메모리 내 fake backend만 사용하며, 운영 서비스나 센서 프로세스를
시작하지 않습니다.

~~~bash
npm ci --ignore-scripts
npx playwright install chromium
npm run test:e2e
npm run test:cockpit:e2e
~~~

`test:cockpit`은 Cockpit 전용 Node behavior suite, `test:cockpit:e2e`는 Cockpit 이름의
hardware-free browser 흐름을 실행합니다. 실제 Camera/LiDAR 성능, 60분 soak와 motion
결과는 [Cockpit 통합 Acceptance](docs/COCKPIT_ACCEPTANCE.md)에 software test와 분리해
기록합니다.

기여자와 CI는 별도 품질 도구를 설치해 아래 검사를 추가로 실행합니다. 이 파일은
운영 ROS 의존성과 분리되어 있으므로 Jetson의 `rclpy` 또는 system-site-packages를
pip로 대체하지 않습니다.

~~~bash
python3 -m pip install -r requirements-quality.txt
python3 -m ruff check robot_dashboard scripts
python3 -m mypy --config-file mypy.ini
python3 scripts/check_repository_secrets.py
python3 -m pip check
python3 -m pip_audit -r requirements.txt
~~~

## 프로젝트 구조

~~~text
config/                         Go2, Generic, TurtleBot 시작 프로필
deploy/                         고정 systemd·sudoers 예제
docs/                           현재 아키텍처, 설치, 토폴로지와 운영 기록
robot_dashboard/api/            FastAPI dependency, request model, domain router
robot_dashboard/application/    runtime container와 mapping/navigation/lifecycle coordinator
robot_dashboard/ros/            ROS runtime, 관측, control transport와 navigation gateway
robot_dashboard/static/core/    공용 API·DOM·format·log-scroll ES module
robot_dashboard/static/features/  기능별 브라우저 state/network/render 소유자
robot_dashboard/*.py            안전 domain manager, adapter와 호환 facade
scripts/                        실행, bridge, mapping, 저장과 검증 도구
tests/                          unit, contract, architecture와 browser module 테스트
requirements*.txt               runtime 및 분리된 contributor 품질 의존성
~~~

현재 소유권과 Phase 0 대비 변경은 [아키텍처 문서](docs/ARCHITECTURE.md)를 기준으로
확인합니다. `docs/ARCHITECTURE_PHASE*.md`는 각 단계 당시의 결정 기록이며 현재 구조를
대체하지 않습니다.

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
- 저장 데이터셋 JPEG와 메타데이터도 로그인 없이 같은 네트워크에서 조회할 수 있습니다.
  얼굴·번호판·실내 정보가 포함될 수 있으므로 신뢰 LAN 밖에 노출하지 말고, 공유 전에
  필요한 익명화와 접근 제어를 적용합니다.
- 서비스 재시작·중지는 Settings의 확인 체크와 브라우저 확인, same-origin, 서버측 idle
  재검사를 요구하지만 사용자 인증 기능은 아닙니다. 반드시 신뢰 LAN에서만 활성화하고,
  범위가 넓은 네트워크에서는 TLS reverse proxy와 접근 제어를 먼저 구성합니다.
- 네트워크 검색 API도 same-origin으로 제한하고, 서버가 직접 확인한 로컬 인터페이스의
  최대 /24만 검색합니다. 검색 결과는 장비 유형을 보증하지 않으므로 선택 전에 확인합니다.
- 인터넷이나 공용망에 노출하기 전 토큰 인증, TLS와 접근 제어를 추가해야 합니다.
- 비밀번호, SSH 키, 토큰, .env, rosbag, PCD, 생성 지도와 수집 데이터셋은 Git에 올리지 않습니다.
- Settings의 진단 ZIP은 지원 공유용 공개 projection이지만 사용자 인증 자료가 아닙니다.
  내보내기 전후에도 신뢰 LAN 정책을 유지하고, browser session ID를 사람의 신원으로
  해석하지 않습니다. 기록 범위와 제외 항목은
  [Phase 13 계약](docs/ARCHITECTURE_PHASE13.md)을 따릅니다.
- 지도 삭제는 되돌릴 수 없으므로 대상 이름과 파일 묶음을 확인한 뒤 실행합니다.

## 라이선스

Robot Scope 코드는 MIT License로 배포합니다. 포함된 Go2 경량 모델은 Unitree
Robotics의 `unitree_ros/robots/go2_description`에서 변환했으며 BSD 3-Clause 원문과
변환 내역을 보존합니다. TurtleBot3 Burger 원본과 경량 파생물은 ROBOTIS
`turtlebot3`의 Apache-2.0을 따릅니다. 각 모델의 고정 commit, SHA-256 manifest,
라이선스와 변환 내역은 `robot_dashboard/static/assets` 아래 README와 catalog에
기록합니다.

한 곳에서 확인할 수 있는 재배포 고지는
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)에 정리되어 있습니다. 저장소에
포함되지 않은 ROS workspace나 현장별 추가 artifact를 설치 이미지에 함께 넣는 경우에는
각 외부 구성 요소의 라이선스와 NOTICE 의무를 별도로 확인해야 합니다.
