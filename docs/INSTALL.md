# 설치 가이드

이 문서는 새 Ubuntu 호스트에 Robot Scope를 설치하는 기준 절차입니다. Robot Scope의
웹 애플리케이션 자체는 `x86_64`와 `arm64`에서 실행할 수 있지만, 실제 로봇·LiDAR
기능은 설치한 ROS 드라이버와 제조사 SDK가 해당 아키텍처를 지원해야 합니다.

## 지원 기준

| 항목 | 지원 범위 | 검증 수준 |
|---|---|---|
| 운영체제 | Ubuntu 22.04 LTS | 필수 기준 |
| 아키텍처 | `x86_64`, `arm64` | 웹/Generic 계층 지원 |
| ROS | ROS 2 Humble | 필수 기준 |
| 참조 장비 | Jetson Orin Nano (`arm64`) | Go2 + XT16 전체 경로 검증 |
| 브라우저 | 최신 Chromium 계열 | 주 검증 대상 |

Ubuntu 24.04, ROS 2 Jazzy, 다른 Jetson 제품과 일반 PC는 자동 호환으로 간주하지
않습니다. 먼저 `observer` 모드에서 확인한 뒤 하드웨어 기능을 한 단계씩 추가하세요.

## 설치 모드

`scripts/install_ubuntu.sh`는 다음 모드 이름을 사용합니다. 모드는 필요한 구성 요소를
선택하는 프리셋입니다. Dry-run은 제어 설정을 바꾸지 않지만, 명시적으로
`go2-control` 또는 `go2-nav`에 `--apply`를 사용하면 signed bridge 구성이 활성화됩니다.
어떤 모드도 서비스를 시작하거나 로봇을 ARM하거나 주행 명령을 보내지는 않습니다.

| 모드 | 대상 | 포함 범위 | 별도 준비 |
|---|---|---|---|
| `observer` | ROS 센서/지도 관측 | 웹 앱, Generic 실행 환경 | ROS 2 Humble |
| `go2` | Go2 센서·카메라 관측 | `observer` + Go2 프로필 | Unitree DDS 환경, 전용 NIC |
| `go2-control` | 수동 Go2 주행 | `go2` + 독립 제어 브리지 | private 제어 env, 안전 검증, 물리 리모컨 |
| `go2-xt16` | XT16 매핑·저장 | `go2` + Hesai/FAST-LIO 연동 | 외부 workspace와 저장소 내 bridge/saver/converter |
| `go2-nav` | 저장 지도 Nav2 주행 | `go2-control` + `go2-xt16` + Nav2 | 검증된 2D 지도와 현장 안전 검증 |

XT16 bridge, Laser map saver와 PCD→2D converter는 저장소에 포함됩니다. 제조사 ROS
workspace와 FAST-LIO는 외부 pinned dependency이므로 각 모드의 필수 항목을
[의존성 문서](DEPENDENCIES.md)에서 먼저 확인하세요. 임의 버전의 workspace를 섞지 마세요.

## 1. 호스트 사전 확인

~~~bash
uname -m
. /etc/os-release && printf '%s %s\n' "$ID" "$VERSION_ID"
ip -br link
df -h /
~~~

다음을 확인합니다.

- Ubuntu가 `22.04`인지 확인합니다.
- 관리용 LAN과 로봇/센서 전용 LAN을 구분합니다.
- Go2 또는 XT16을 사용할 호스트는 전용 NIC 이름과 고정 CIDR을 기록합니다.
- 로봇 제어 시험 전에는 충분한 공간과 물리 리모컨을 준비합니다.
- 지도, 환경 파일, 키와 토큰은 Git 저장소 밖에 보관합니다.

권장 배선은 [토폴로지 문서](TOPOLOGY.md)를 참고하세요.

### 운영체제와 ROS 패키지

Installer는 기본적으로 사용자 영역만 다룹니다. 운영체제 패키지도 함께 준비하려면 target
사용자로 실행하면서 `--apply --install-system-packages`를 명시합니다. 이 조합에서만
checksum으로 검증한 공식 ROS apt source와 manifest package를 설치하기 위해 `sudo`를
사용합니다. 정확한 목록은 `config/ros_dependencies_humble.json`이 기준입니다.

다음 수동 APT 명령은 별도 관리자 절차를 원하는 경우의 대안입니다.

~~~bash
sudo apt update
sudo apt install build-essential ca-certificates cmake curl git gnupg iproute2 iputils-ping \
  libapr1-dev libboost-all-dev libeigen3-dev libpcl-dev libyaml-cpp-dev \
  libssl-dev locales lsb-release openssl pkg-config procps \
  python3-colcon-common-extensions python3-dev python3-pip python3-rosdep python3-venv \
  ros-humble-ament-cmake-auto ros-humble-common-interfaces ros-humble-pcl-conversions \
  ros-humble-pcl-ros ros-humble-rclcpp-components ros-humble-rmw-cyclonedds-cpp \
  ros-humble-ros-base ros-humble-rosbag2 ros-humble-rosidl-default-generators \
  ros-humble-rosidl-generator-dds-idl ros-humble-tf2-ros software-properties-common
~~~

Go2 카메라에는 다음 package group을 추가합니다.

~~~bash
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-libav
~~~

`go2-nav`에는 Nav2를 추가합니다.

~~~bash
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup
~~~

ROS 2 APT repository 자체를 아직 설정하지 않았다면 Ubuntu 22.04용 ROS 2 Humble 공식
설치 절차를 먼저 따릅니다. 다른 ROS 배포판의 package를 섞지 마세요.

### 로봇 탑재 relay host 최초 SSH 보안 설정

현재 참조 배선의 relay host는 `unitree@192.168.123.18`입니다. 초기 암호가 필요한 첫
로그인은 터미널에서 대화형으로만 수행합니다. 암호를 명령 인자, URL, `.env`, 문서,
Git history 또는 자동화 로그에 넣지 마세요. `sshpass`도 사용하지 않습니다.

첫 로그인 직후 다음 순서로 설정합니다.

1. `passwd`로 초기 암호를 즉시 변경합니다.
2. 관리 PC에 별도 ED25519 SSH key를 만들고 공개키만 relay host에 등록합니다.
3. 두 번째 터미널에서 암호 인증을 끈 접속이 성공하는지 먼저 확인합니다.
4. 현장 운영 정책이 허용하면 SSH server의 password/keyboard-interactive 인증을
   비활성화합니다.

~~~bash
ssh-keygen -t ed25519 -a 100
ssh-copy-id unitree@192.168.123.18
ssh -o PasswordAuthentication=no unitree@192.168.123.18
~~~

Password 인증을 끌 때는 기존 세션을 유지한 상태에서
`/etc/ssh/sshd_config.d/`의 root-owned drop-in을 사용하고, `sudo sshd -t`가 통과한 뒤
SSH service를 reload합니다. 공개키 접속을 별도 터미널에서 검증하기 전에 현재 세션을
닫지 마세요. 개인키는 relay host나 Robot Scope 저장소에 복사하지 않습니다.

예를 들어 `sudoedit /etc/ssh/sshd_config.d/60-robot-scope-key-only.conf`로 다음 세 줄만
추가합니다.

~~~text
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
~~~

그 다음 문법 검사와 reload를 수행합니다. 문법 검사가 실패하면 reload하지 않습니다.

~~~bash
sudo sshd -t
sudo systemctl reload ssh
~~~

## 2. 저장소 받기

운영 설치는 임의 브랜치보다 검증된 release tag 또는 담당자가 지정한 commit을
사용합니다. 아직 tag가 없다면 설치 기록에 commit SHA를 반드시 남기세요.

~~~bash
git clone https://github.com/Phjrab/robot-scope-ros2-dashboard.git robot-scope
cd robot-scope
git status --short --branch
git rev-parse HEAD
~~~

개인 환경 파일이나 지도 데이터를 clone한 디렉터리에 복사하지 마세요. 다른 사람에게
소스를 전달할 때도 작업 폴더 전체가 아니라 Git commit이나 `git archive` 결과를
사용합니다.

## 3. 설치 프로그램 실행

설치 프로그램의 기본 동작은 읽기 전용 dry-run입니다. 먼저 변경 예정 항목과 진단 결과를
확인합니다.

~~~bash
./scripts/install_ubuntu.sh --mode observer
~~~

문제가 없을 때만 사용자 영역에 적용합니다. Installer 자체를 root나 `sudo`로 실행하지
마세요.

~~~bash
./scripts/install_ubuntu.sh --mode observer --apply
~~~

새 Ubuntu host에서 system package와 systemd unit까지 준비하려면 dry-run으로 전체 계획을
먼저 확인한 다음 두 opt-in을 함께 적용합니다.

~~~bash
./scripts/install_ubuntu.sh --mode observer \
  --install-system-packages --install-service
./scripts/install_ubuntu.sh --mode observer --apply \
  --install-system-packages --install-service
~~~

이 명령도 서비스를 즉시 시작하지 않습니다. 검증 후 운영자가 별도로 시작합니다.
Installer 내부 doctor는 새 호스트에서 로봇 케이블이 아직 없어도 소프트웨어 설치를
마칠 수 있도록, 존재하지 않는 Go2 NIC·주소만 경고로 취급합니다. 인터페이스 이름과
고정 CIDR의 형식 오류, 누락된 패키지·workspace·키는 계속 실패합니다. 서비스 시작 전에는
아래의 독립 doctor를 다시 실행하며, 이때 NIC와 주소도 필수 조건으로 검사됩니다.

Go2 전체 경로도 가장 작은 모드부터 순서대로 확인하는 것이 좋습니다.
실제 NIC와 static CIDR을 알고 있다면 아래 [Go2 전용 NIC 설정](#go2-전용-nic-설정)을
먼저 적용하세요. 로봇이 꺼졌거나 케이블이 없는 설치 시점에는 installer가 그 하드웨어
항목만 경고로 남기고 계속할 수 있지만, live 기능 시작 전 strict doctor는 통과해야 합니다.

~~~bash
./scripts/install_ubuntu.sh --mode go2
./scripts/install_ubuntu.sh --mode go2 --apply
python3 scripts/robot_scope_doctor.py --mode go2
~~~

그 다음 필요한 경우에만 `go2-control`, `go2-xt16`, `go2-nav` 중 하나를 선택합니다.
설치 프로그램은 사용자 설정·virtualenv와 pinned source bootstrap을 준비합니다. 명시적인
opt-in이 있으면 manifest의 운영체제 패키지와 현재 사용자/checkout에 맞춘 systemd unit도
설치합니다. 외부 workspace의 출처·commit을 추측하거나 LiDAR의 목적지 주소를 바꾸지
않습니다. Doctor가 외부 구성 요소를 찾지 못하면 [의존성 문서](DEPENDENCIES.md)의
manifest와 현장별 placeholder를 먼저 확인하세요.

`go2-control`과 `go2-nav`의 `--apply`는 sibling mode-0600 `control.env`가 없을 때만
무작위 64자리 bridge key와 explicit enable 값을 생성합니다. Key를 명령행에서 받거나
출력하지 않고, 기존 파일은 덮어쓰지 않습니다. Installer를 사용하지 않는 수동 설치는
README의 [제어 키 절차](../README.md#go2-제어-기능-활성화)를 따릅니다. 일반
`robot-scope.env`에는 secret을 넣지 않습니다.

Installer는 선택한 mode를 pinned dependency bootstrap에 전달합니다. Bootstrap도 기본은
dry-run이며, `--apply`에서만 외부 source를 clone/build합니다. 기존 repository는 reset하지
않고 origin, commit과 tracked 변경이 정확하지 않으면 중단합니다.

외부 workspace의 기본 root는 target 사용자의 홈 디렉터리입니다. 다른 디스크나 기존
workspace를 사용해야 하면 일반 `robot-scope.env`의 `ROBOT_SCOPE_WORKSPACE_ROOT`에 절대
경로를 지정합니다. `~`와 `$HOME`은 systemd가 확장하지 않으므로 쓰지 않습니다. 빈 값은
target 사용자의 홈을 뜻합니다. Installer, doctor와 systemd runtime이 같은 값을
사용하므로 홈 경로를 스크립트별로 따로 수정하지 마세요. Livox SDK2를 별도 위치에
설치할 때의 `ROBOT_SCOPE_LIVOX_SDK_PREFIX`도 절대 경로만 허용합니다. `go2-xt16`과
`go2-nav`는 pinned Livox upstream build helper의 제한 때문에 workspace와 Livox SDK
prefix 경로에 공백도 허용하지 않습니다.

주요 installer 옵션은 다음과 같습니다.

| 옵션 | 의미 |
|---|---|
| `--dry-run` | 기본값. 파일과 서비스를 변경하지 않고 계획·진단만 수행 |
| `--apply` | 확인된 사용자 영역 설치를 적용 |
| `--install-system-packages` | `--apply`와 함께 공식 ROS apt source와 mode별 manifest 패키지 설치 |
| `--install-service` | `--apply`와 함께 현재 사용자용 unit을 render/검증/설치, enable/start는 하지 않음 |
| `--project-dir DIR` | 명시적인 Robot Scope checkout 사용 |
| `--config-dir DIR` / `--env-file FILE` | 호스트별 설정 위치 지정 |
| `--os-release FILE` | 진단에 사용할 os-release 파일 지정; 일반 설치에서는 기본값 유지 |
| `--skip-python-deps` | 이미 검증된 Python 환경을 재사용할 때만 사용 |
| `--json-doctor` | 후속 doctor 결과를 JSON으로 출력 |

doctor는 `--json`을 지원하며 exit `0`은 준비 완료, `1`은 필수 항목 누락, `2`는 잘못된
호출 또는 설정을 뜻합니다. 비밀값은 결과에 포함하지 않습니다.

Installer가 내부에서 실행하는 doctor는 로봇이 꺼진 설치도 가능하도록 NIC/carrier
누락만 경고로 처리합니다. 같은 동작을 직접 확인할 때는 다음 명령을 사용할 수 있지만,
이는 실주행 준비 완료 판정이 아닙니다.

~~~bash
python3 scripts/robot_scope_doctor.py --mode go2 --allow-hardware-offline
~~~

서비스를 시작하거나 로봇을 연결하기 전에는 `--allow-hardware-offline` 없이 실제 mode의
doctor가 exit `0`인지 확인합니다.

### Go2 전용 NIC 설정

처음 Go2 mode를 적용하기 전에 private env를 만들고, 실제 유선 NIC 이름을 기록합니다.
기존 파일이 있으면 installer와 아래 명령 모두 덮어쓰지 않습니다.

~~~bash
install -d -m 700 "$HOME/.config/robot-scope"
test -e "$HOME/.config/robot-scope/robot-scope.env" || \
  install -m 600 deploy/robot-scope.env.example \
    "$HOME/.config/robot-scope/robot-scope.env"
ip -br -4 address
~~~

`robot-scope.env`에서 다음 값을 현재 host에 맞춥니다.

~~~dotenv
ROBOT_SCOPE_ROBOT_IP=192.168.123.161
ROBOT_SCOPE_GO2_INTERFACE=<실제_유선_NIC>
ROBOT_SCOPE_GO2_INTERFACE_CIDR=192.168.123.99/24
ROBOT_SCOPE_CAMERA_INTERFACE=<같은_유선_NIC>
~~~

NetworkManager를 사용하는 전용 연결의 예시는 다음과 같습니다. `<...>`를 확인한 실제
연결 이름으로 바꾸고, 관리망 연결에는 적용하지 마세요.

~~~bash
nmcli -t -f NAME,DEVICE connection show
sudo nmcli connection modify "<Go2_전용_연결>" \
  ipv4.method manual ipv4.addresses 192.168.123.99/24 \
  ipv4.gateway "" ipv4.never-default yes
sudo nmcli connection up "<Go2_전용_연결>"
ip -br -4 address show dev "<실제_유선_NIC>"
~~~

다른 네트워크 관리 도구를 사용한다면 같은 static CIDR을 그 도구에 영구 설정합니다.
기존 default route나 관리용 Wi-Fi를 Go2 NIC로 옮기지 마세요.

## 4. 외부 구성 연결

다음 항목은 모드에 따라 필요합니다.

- Unitree Cyclone DDS workspace와 저장소의 Go2 환경 helper
- Hesai ROS 2 driver workspace와 XT16 설정 파일
- FAST-LIO ROS 2 workspace와 검증된 XT16 파라미터
- Livox SDK2/message dependency와 Nav2

XT16 변환 bridge, `/Laser_map` 저장 helper와 2D 지도 converter는 저장소의 `scripts/`
파일을 사용합니다. Go2 DDS도 `scripts/setup_go2_ros2_humble.sh`를 사용합니다. 운영 호스트
홈 디렉터리의 이전 prototype이나 helper를 우선하지 않습니다.

외부 구성의 저장소 URL, commit 또는 release, 로컬 경로와 라이선스를 배포 기록에 남깁니다.
우리 참조 호스트의 홈 디렉터리를 그대로 복제하지 말고 환경 변수 또는 설치 프로그램이
생성한 호스트별 설정을 사용하세요.

## 5. 서비스 시작 전 검사

~~~bash
python3 scripts/robot_scope_doctor.py --mode observer
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
~~~

Node.js가 없는 운영 호스트에서는 JavaScript 테스트를 생략할 수 있지만, release를
만드는 호스트와 CI에서는 반드시 실행합니다. doctor는 선택한 모드에 맞춰 다시 실행합니다.

`--install-service`를 사용하지 않았다면 installer는 systemd unit을 설치하지 않습니다.
사용한 경우에도 unit을 enable/start하지 않으며 기존 enable 상태도 바꾸지 않습니다.
먼저 foreground에서 가장 작은
실행 경로를 확인합니다.

~~~bash
./scripts/run_generic.sh
~~~

Go2 host는 doctor가 통과한 뒤 `./scripts/run_go2_humble.sh`를 사용합니다. Installer의
`--install-service`는 현재 사용자, checkout과 env 경로를 반영한 unit을 검증해 설치합니다.
수동 실행 또는 선택적 자동 시작은
[README의 systemd 절차](../README.md#수동-실행과-선택적-자동-시작)를 따르되 service
example의 `User`, `WorkingDirectory`, `EnvironmentFile`, `ExecStart`, `HOME`, NIC와
CIDR을 현재 호스트와 일치시킵니다. 참조 장비 값을 그대로 복사하지 마세요.

`--install-service`는 root 소유 `/usr/local/bin/robot-scope-dashboard` 관리 helper도
설치하지만 lifecycle sudoers와 로봇 탑재 XT16 relay service는 설치하지 않습니다.
각 권한은 별도의 최소권한 절차를 사용합니다. Installer는 service를
start/restart하거나 ARM·주행 명령을 보내지 않습니다.

서비스를 설치했다면 상태와 로그를 확인합니다.

~~~bash
systemctl status robot-scope.service --no-pager
journalctl -u robot-scope.service -n 100 --no-pager
curl -fsS http://127.0.0.1:8088/api/v1/health
~~~

SSH에서 고정 dashboard unit을 한 명령으로 관리하려면 README의
[SSH 관리 절차](../README.md#ssh에서-한-명령으로-대시보드-시작종료)에 따라 기존 lifecycle
exact-command sudoers를 설치합니다. 이후 관리 PC에서는 대화형 셸 또는 직접 SSH 명령을 사용할 수
있습니다. `sudo -n`을 쓰므로 TTY나 암호 입력은 필요하지 않습니다.

~~~bash
ssh robot-scope-host
robot-scope-dashboard status
robot-scope-dashboard start
robot-scope-dashboard stop

# 동일한 동작을 관리 PC에서 한 줄로 실행
ssh robot-scope-host robot-scope-dashboard restart
~~~

`start`, `restart`와 실행 중인 `status`는 대시보드 HTTP 준비가 끝난 뒤 브라우저에서 열
접속 주소를 터미널에 함께 출력합니다. SSH 세션에서는 해당 세션이 접속한 서버 IP를 우선
사용하므로 관리망 주소가 바뀌어도 고정 IP를 스크립트에 넣을 필요가 없습니다.

`robot-scope-host`는 관리 PC의 `~/.ssh/config`에 등록한 별칭입니다. 개인키, 비밀번호와
유동 관리망 주소는 저장소에 넣지 않습니다. start/stop/restart 전에 제어·mapping·Nav가
idle인지 확인하며, helper의 preflight가 blocker를 발견하면 변경 없이 종료합니다.
`logs`가 권한 오류를 내는 일반 Ubuntu 계정은 관리자에게 `systemd-journal` 그룹 정책을
검토받거나 기존 `sudo journalctl` 진단 절차를 사용합니다. Helper에 journal sudo 권한은
추가하지 않습니다.

`observer` 또는 로봇이 분리된 상태에서 `offline viewer`가 표시되는 것은 정상입니다.
서비스가 켜졌다는 이유만으로 제어·매핑·내비게이션 준비가 끝난 것은 아닙니다.

## 6. 모드별 안전 스모크 테스트

### observer

1. 브라우저에서 `http://HOST_IP:8088`을 엽니다.
2. `/api/v1/health`가 응답하는지 확인합니다.
3. Settings에서 Generic 프로필과 허용된 데이터 소스를 확인합니다.
4. 저장 지도 보기처럼 로봇 명령을 내리지 않는 기능부터 시험합니다.

### go2

1. 전용 NIC와 DDS mode가 올바른지 doctor로 확인합니다.
2. `/lowstate`와 필요한 센서 토픽의 publisher/freshness를 확인합니다.
3. 카메라 화면은 Sensors 메뉴를 열었을 때만 디코더가 시작되는지 확인합니다.
4. Controls는 활성화하지 않은 상태로 두고 관측 기능을 먼저 검증합니다.

### go2-control

1. Installer가 생성했거나 [수동 절차](../README.md#go2-제어-기능-활성화)로 만든
   mode-0600 `control.env`를 확인합니다. Key 값은 출력하지 않습니다.
2. 로봇 주변을 비우고 물리 리모컨을 손에 듭니다.
3. doctor와 Controls readiness를 확인하되 자동화된 설치 검사에서 ARM하지 않습니다.
4. 첫 실제 시험은 제조사가 권장하는 안전 자세에서 수행합니다.

### go2-xt16

다음 토픽을 순서대로 확인합니다.

~~~text
/lidar_points -> /velodyne_points -> /Laser_map + /Odometry
~~~

`/Laser_map`이 새 데이터이고 매핑 pipeline이 `RUNNING`일 때만 저장을 시험합니다. 사용자가
XT16을 고정한 상태에서 센서가 끊기면 내장 LiDAR로 자동 전환하지 않고 `WAITING`으로
남는 것이 정상입니다.

### go2-nav

1. 관리 가능한 PGM/YAML 묶음과 revision을 확인합니다.
2. 초기 위치와 목표를 보내지 않은 채 Nav2 readiness까지만 먼저 확인합니다.
3. 실제 목표 시험은 사람이 없는 제한 구역에서 물리 리모컨을 든 상태로 수행합니다.
4. `CANCEL`, `STOP`, 네트워크 단절 시 정지 경로를 각각 검증합니다.

## 7. 다음 단계

- 오류가 있으면 [문제 해결](TROUBLESHOOTING.md)을 확인합니다.
- 운영 업데이트 전에는 [업데이트와 롤백](UPDATE_ROLLBACK.md)을 확인합니다.
- 두 대 이상의 호스트를 쓰면 [토폴로지](TOPOLOGY.md)의 서비스 배치를 따릅니다.
