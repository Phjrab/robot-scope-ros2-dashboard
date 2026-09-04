# 설치 가이드

이 문서는 새 Ubuntu 호스트에 Robot Scope를 설치하는 기준 절차입니다. Robot Scope의
웹 애플리케이션 자체는 `x86_64`와 `arm64`에서 실행할 수 있지만, 실제 로봇·LiDAR
기능은 설치한 ROS 드라이버와 제조사 SDK가 해당 아키텍처를 지원해야 합니다.

## 지원 기준

| 항목 | 지원 범위 | 검증 수준 |
|---|---|---|
| 운영체제 | Ubuntu 22.04 LTS, Ubuntu 24.04 LTS | mode별 필수 기준 |
| 아키텍처 | `x86_64`, `arm64` | 웹/Generic 계층 지원 |
| ROS | 22.04: ROS 2 Humble, 24.04: ROS 2 Jazzy | OS와 고정 pair |
| 참조 장비 | Jetson Orin Nano (`arm64`) | Go2 + XT16 전체 경로 검증 |
| 브라우저 | 최신 Chromium 계열 | 주 검증 대상 |

Ubuntu 24.04 + ROS 2 Jazzy는 `observer`/Generic 웹 계층까지만 지원합니다. Go2,
제어, XT16과 Nav2 전체 경로는 Ubuntu 22.04 + ROS 2 Humble에서만 지원하며 installer와
doctor가 다른 조합을 fail-closed로 거부합니다.

완전 무선 대회 구성의 예외는 Ubuntu 20.04/ROS 2 Foxy 탑재 Jetson에서 실행하는 최소
`Go2ControlBridge` 프로세스뿐입니다. 웹, Mission, Nav2 또는 전체 Robot Scope를 그
호스트로 옮기지 않습니다. 이 경로는 portable installer 대상이 아니며
[무선 제어 ADR](ADR_WIRELESS_CONTROL_TRANSPORT.md)의 고정 서비스와 검증 절차만 사용합니다.

## 설치 모드

`scripts/install_ubuntu.sh`는 다음 모드 이름을 사용합니다. 모드는 필요한 구성 요소를
선택하는 프리셋입니다. Dry-run은 제어 설정을 바꾸지 않지만, 명시적으로
`go2-control` 또는 `go2-nav`에 `--apply`를 사용하면 signed bridge 구성이 활성화됩니다.
어떤 모드도 서비스를 시작하거나 로봇을 ARM하거나 주행 명령을 보내지는 않습니다.

| 모드 | 대상 | 포함 범위 | 별도 준비 |
|---|---|---|---|
| `observer` | ROS 센서/지도 관측 | 웹 앱, Generic 실행 환경 | Humble 또는 Jazzy(OS pair 준수) |
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

- Ubuntu가 `22.04` 또는 `24.04`인지 확인하고 각각 Humble 또는 Jazzy를 사용합니다.
- 관리용 LAN과 로봇/센서 전용 LAN을 구분합니다.
- Go2 또는 XT16을 사용할 호스트는 전용 NIC 이름과 고정 CIDR을 기록합니다.
- 로봇 제어 시험 전에는 충분한 공간과 물리 리모컨을 준비합니다.
- 지도, 환경 파일, 키와 토큰은 Git 저장소 밖에 보관합니다.

권장 배선은 [토폴로지 문서](TOPOLOGY.md)를 참고하세요.

### 운영체제와 ROS 패키지

Installer는 기본적으로 사용자 영역만 다룹니다. 운영체제 패키지도 함께 준비하려면 target
사용자로 실행하면서 `--apply --install-system-packages`를 명시합니다. 이 조합에서만
checksum으로 검증한 공식 ROS apt source와 manifest package를 설치하기 위해 `sudo`를
사용합니다. 정확한 목록은 OS에 따라 `config/ros_dependencies_humble.json` 또는
`config/ros_dependencies_jazzy.json`이 기준입니다.

다음 수동 APT 명령은 Ubuntu 22.04/Humble 하드웨어 host에서 별도 관리자 절차를 원하는
경우의 대안입니다. Ubuntu 24.04/Jazzy observer는 installer가 `ros-jazzy-*` manifest를
선택하도록 두고 Humble package를 섞지 마세요.

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

ROS 2 APT repository 자체를 아직 설정하지 않았다면 해당 OS pair의 공식 설치 절차를
따릅니다. 다른 ROS 배포판의 package를 섞지 마세요.

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

### 로봇 탑재 RealSense relay의 host별 주소

Relay 실행 파일과 service를 설치한 뒤 예제 설정을 사용자별 파일로 복사합니다. 실제 주소는
Git에 커밋하지 않습니다.

~~~bash
install -d -m 700 "$HOME/.config/robot-scope"
install -m 600 deploy/robot-scope-realsense-camera.env.example \
  "$HOME/.config/robot-scope/realsense-camera.env"
~~~

참조 배선이 아니라면 탑재 Jetson에서 `ROBOT_SCOPE_REALSENSE_BIND_HOST`를 그 호스트가 실제
소유한 관리 주소로, `ROBOT_SCOPE_REALSENSE_DASHBOARD_HOST`를 dashboard host 주소로
설정합니다. Dashboard host의 `robot-scope.env` 또는 `control.env`에는 같은 relay 주소를
`ROBOT_SCOPE_REALSENSE_RELAY_HOST`로 설정합니다. 이 값은 Go2 본체 주소가 아니므로
`ROBOT_SCOPE_ROBOT_IP`를 함께 변경하지 않습니다.

수동 운영 정책에서는 service를 `disabled`로 유지하고 필요할 때만 `start`합니다.

~~~bash
sudo systemctl disable robot-scope-realsense-camera.service
sudo systemctl start robot-scope-realsense-camera.service
~~~

잘못된 bind 주소로 인한 영구 재시작을 막기 위해 service는 60초 동안 5회 실패하면 추가
재시작을 중단합니다. 주소를 수정한 뒤 `reset-failed`하고 다시 수동 시작하세요.

### 완전 무선 Go2 내장 카메라 relay

이 절차는 탑재 Jetson이 `eth0=192.168.123.18`, `wlan0=192.168.50.30`을 소유하고 외부
dashboard가 `192.168.50.10`을 소유하는 검증된 배선에만 적용합니다. 주소를 일반화하거나
환경 파일로 바꾸지 않습니다. 다른 배선은 코드와 packet contract를 별도 review해야 합니다.

탑재 Jetson의 검증된 checkout에서 실행 파일과 unit을 root-owned 고정 경로에 설치합니다.
설치는 service를 자동 시작하거나 다음 부팅에 enable하지 않습니다.

~~~bash
sudo install -d -o root -g root -m 0755 /usr/local/libexec/robot-scope
sudo install -o root -g root -m 0755 scripts/go2_camera_rtp_relay.py \
  /usr/local/libexec/robot-scope/go2_camera_rtp_relay.py
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-go2-camera-relay.service.example \
  /etc/systemd/system/robot-scope-go2-camera-relay.service
sudo systemctl daemon-reload
sudo systemctl disable robot-scope-go2-camera-relay.service
sudo systemctl start robot-scope-go2-camera-relay.service
systemctl is-enabled robot-scope-go2-camera-relay.service
systemctl is-active robot-scope-go2-camera-relay.service
~~~

기대값은 `disabled`와 `active`입니다. Sensors에서 Go2 panel을 열어 실제 `LIVE`, JPEG frame,
FPS를 확인한 뒤 viewer를 닫습니다. Relay는 원본 RTP를 재인코딩하지 않으며 dashboard의
기존 고정 Go2 GStreamer receiver를 그대로 사용합니다. service 로그의 `accepted`,
`forwarded`, `rejected`, sequence loss를 함께 확인하세요. `send_errors`는 dashboard에서
viewer가 없어 UDP port가 닫힌 동안 발생할 수 있으므로 패널이 열린 구간의 실제 LIVE와
연속 sequence를 성공 기준으로 사용합니다.

### 완전 무선 Control Bridge 설치

이 절차는 외부 Orin `192.168.50.10`, 탑재 Jetson `192.168.50.30`, 탑재 Jetson의 Go2
전용 `eth0=192.168.123.18/24`가 먼저 검증된 구성에만 적용합니다. 서비스 설치 중에는
로봇을 움직이지 않으며 두 Control Bridge unit을 모두 stopped 상태로 유지합니다.

탑재 Jetson에는 검증된 commit을 `/home/unitree/project/robot-scope`에 배포하고 다음 예제의
private copy를 만듭니다. Dashboard의 기존 Bridge key와 정확히 같은 값을 안전한 채널로
복사하되 터미널 출력, 명령 인자, 로그 또는 Git에 남기지 않습니다.

~~~bash
install -d -m 700 /home/unitree/.config/robot-scope
install -m 600 deploy/robot-scope-control-bridge-robot-side.env.example \
  /home/unitree/.config/robot-scope/control-bridge.env
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-control-bridge-robot-side.service.example \
  /etc/systemd/system/robot-scope-control-bridge.service
sudo systemctl daemon-reload
sudo systemctl disable robot-scope-control-bridge.service
~~~

탑재 Jetson의 remote lifecycle 권한은 별도로 설치합니다. 두 파일 모두 root-owned인지
확인하고 sudoers 문법 검사를 통과해야 합니다.

~~~bash
sudo install -d -o root -g root -m 0755 /usr/local/libexec/robot-scope
sudo install -o root -g root -m 0755 \
  scripts/robot_scope_control_bridge_ssh_command.py \
  /usr/local/libexec/robot-scope/control-bridge-lifecycle-ssh
sudo install -o root -g root -m 0440 \
  deploy/robot-scope-control-bridge-remote.sudoers.example \
  /etc/sudoers.d/.robot-scope-control-bridge-remote.new
sudo visudo -cf /etc/sudoers.d/.robot-scope-control-bridge-remote.new
sudo mv /etc/sudoers.d/.robot-scope-control-bridge-remote.new \
  /etc/sudoers.d/robot-scope-control-bridge-remote
sudo visudo -cf /etc/sudoers.d/robot-scope-control-bridge-remote
~~~

외부 Orin의 Robot Scope service 사용자로 별도 ED25519 키를 생성합니다. 기존 일반 관리
키를 재사용하지 않습니다. 공개키만 탑재 Jetson의 `authorized_keys`에 다음 강제 명령
형식으로 등록합니다.

~~~text
restrict,command="/usr/local/libexec/robot-scope/control-bridge-lifecycle-ssh" ssh-ed25519 PUBLIC_KEY_MATERIAL robot-scope-control-lifecycle
~~~

외부 Orin의 private `control.env`에는 ADR의 dashboard-side UDP 및 SSH lifecycle 값을
추가합니다. Identity는 mode 0600 regular file이어야 하고 known-hosts 파일은
`192.168.50.30`의 실제 host key를 strict matching해야 합니다. 설정 후 dashboard만
재시작합니다. 탑재 Bridge는 자동으로 시작하지 않습니다.

배포 직후 첫 검증은 Controls 페이지에서 확인 체크 → START → signed status 확인 → STOP
순서입니다. ARM, deadman, drive, action, navigation 또는 mapping 입력을 사용하지 않습니다.
START 후 authenticated status, LowState freshness와 graph cardinality를 모두 확인하기 전에는
제어 가능 상태로 판정하지 않습니다.

### 전용 appliance 부팅 자동 시작 opt-in

공용 개발 호스트와 일반 설치에서는 모든 Robot Scope unit을 계속 `disabled`/수동 시작으로
유지합니다. `scripts/install_ubuntu.sh`도 service를 설치할 수는 있지만 enable하거나
시작하지 않습니다. 아래 정책은 고정 네트워크, 서비스별 private 환경 파일, strict SSH
host key와 무동작 검증이 끝난 전용 Robot Scope appliance에서 관리자가 별도로 승인한 경우에만
적용합니다.

부팅 자동 시작 allowlist는 다음 세 unit으로 고정합니다.

| Host | 부팅 자동 시작 허용 unit |
| --- | --- |
| 외부 dashboard Orin `192.168.50.10` | `robot-scope.service` |
| 탑재 Jetson `192.168.50.30` | `robot-scope-control-bridge.service` |
| 탑재 Jetson `192.168.50.30` | `robot-scope-xt16-wireless-relay.service` |

먼저 두 호스트에서 unit의 root-owned 설치본, `network-online.target`, NetworkManager 자동 연결,
DHCP 예약 주소와 `is-active` 수동 검증을 확인합니다. NetworkManager profile의
`connection.autoconnect=yes`만으로는 `network-online.target`이 고정 주소 준비를 기다렸다는
증거가 아닙니다. `NetworkManager-wait-online.service` 또는 동등한 bounded interface waiter와
실제 cold boot 결과를 확인하기 전에는 enable 상태만으로 자동 시작을 신뢰하거나 PASS로
기록하지 않습니다. 특히 탑재 Jetson의 `wlan0`이
`192.168.50.30/24`, `eth0`이 `192.168.123.18/24`를 소유하기 전에 Bridge와 relay가 시작되면
restart limit에 도달할 수 있으므로 cold boot 검증 전에는 정책을 완료로 판정하지 않습니다.
승인 후 관리자가 각 호스트에서 다음 exact 명령만 실행합니다. `--now`를 사용하지 않으므로
현재 실행 상태와 다음 부팅 정책을 섞지 않습니다.

외부 dashboard Orin:

~~~bash
sudo install -d -o root -g root -m 0755 \
  /usr/local/libexec/robot-scope \
  /etc/systemd/system/robot-scope.service.d
sudo install -o root -g root -m 0755 \
  deploy/robot-scope-dashboard-appliance-network-ready.py.example \
  /usr/local/libexec/robot-scope/robot_scope_dashboard_appliance_network_ready.py
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-dashboard-release-symlink.conf.example \
  /etc/systemd/system/robot-scope.service.d/release.conf
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-dashboard-appliance.conf.example \
  /etc/systemd/system/robot-scope.service.d/10-appliance-network-ready.conf
sudo systemctl daemon-reload
sudo systemctl enable robot-scope.service
~~~

`release.conf`는 검토된 `/home/jetson_orin_nano/robot-scope` release symlink만 사용합니다. 이전
commit의 절대 release 디렉터리를 가리키는 기존 drop-in을 둔 채 enable하지 않으며, 설치 후
`systemctl cat robot-scope.service`와 symlink 대상을 다시 확인합니다. 별도 appliance drop-in은
disabled인 `NetworkManager-wait-online.service`를 boot transaction에 포함한 뒤, root 권한이나
shell 없이 `eno1=192.168.50.10/24`와 link UP/RUNNING을 시도당 최대 60초 동안 읽기 전용으로
확인합니다. 주소, link, route 또는 NetworkManager 상태는 변경하지 않습니다. 또한 전용
appliance에서만 `ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER=1`을 명시해, 실패한 관측 전용 XT16
preview의 bounded 복구를 허용합니다. 이 값은 Mapping/Nav/Mission/Control을 시작하거나 이전
작업을 복구하지 않습니다. 두 drop-in은 서로 분리하며 기존 restart/start-limit 값은
덮어쓰지 않습니다. 이 절차는 현재 dashboard process를 자동으로 restart하지 않습니다.

탑재 Jetson:

~~~bash
sudo install -d -o root -g root -m 0755 \
  /usr/local/libexec/robot-scope \
  /etc/systemd/system/robot-scope-control-bridge.service.d \
  /etc/systemd/system/robot-scope-xt16-wireless-relay.service.d
sudo install -o root -g root -m 0755 \
  deploy/robot-scope-appliance-network-ready.py.example \
  /usr/local/libexec/robot-scope/robot_scope_appliance_network_ready.py
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-robot-side-appliance-network-ready.conf.example \
  /etc/systemd/system/robot-scope-control-bridge.service.d/10-appliance-network-ready.conf
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-robot-side-appliance-network-ready.conf.example \
  /etc/systemd/system/robot-scope-xt16-wireless-relay.service.d/10-appliance-network-ready.conf
sudo systemctl daemon-reload
sudo systemctl enable robot-scope-control-bridge.service
sudo systemctl enable robot-scope-xt16-wireless-relay.service
~~~

이 opt-in drop-in은 disabled인 `NetworkManager-wait-online.service`를 두 unit의 boot transaction에
직접 포함하고, root 권한이나 shell 없이 고정된 두 interface가 동시에 준비됐는지만 읽습니다.
조건은 `eth0=192.168.123.18/24`, `wlan0=192.168.50.30/24`, link UP/RUNNING이며 한 activation
시도당 최대 60초만 기다립니다. 주소를 추가하거나 link/route/NetworkManager 상태를 변경하지
않습니다. Timeout이면 기존 unit의 `Restart=on-failure`, `RestartSec=3`,
`StartLimitIntervalSec=60`, `StartLimitBurst=5`가 그대로 적용됩니다. Drop-in은 이 restart bound를
제거하거나 완화하지 않습니다. 설치 후 두 unit의 `systemctl cat`에 drop-in이 정확히 한 번씩
합성되는지 확인한 다음 enable합니다.

다른 `robot-scope-*` unit, camera relay, wireless IMU/odometry sender·receiver, FAST-LIO,
Mapping, Navigation 또는 Mission unit을 이 정책에 추가하지 않습니다. Browser API와 제한된
SSH lifecycle helper에도 `enable`/`disable`, wildcard, 임의 unit 이름 또는 host 선택 권한을
추가하지 않습니다. 서로 다른 두 호스트의 unit을 `Requires=`로 결합하지 않습니다.

부팅 시 dashboard는 로봇보다 먼저 올라와도 offline/fail-closed 상태로 대기해야 합니다.
Control Bridge는 startup·watchdog의 exact StopMove만 발행할 수 있으며 signed Stop handoff,
fresh LowState와 graph cardinality가 확인되기 전에는 control-ready가 될 수 없습니다. 자동
시작은 lease를 획득하거나 ARM, deadman, Move/action, 비영점 명령 또는 이전 동작을 복구하는
권한이 아닙니다. XT16 relay는 고정 peer로 센서 payload만 전달하며 Mapping/Nav/Mission,
Dataset Capture 또는 goal을 시작하지 않습니다. 기존 relay가 이미 active이면 preview
lifecycle은 이를 자기 소유로 간주하거나 cleanup에서 중지하면 안 됩니다.

업데이트·롤백 시 enable 상태 보존과 cold-boot 확인은
[업데이트와 롤백](UPDATE_ROLLBACK.md#전용-appliance-enable-상태와-cold-boot-검증)을 따릅니다.

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

Go2 전체 경로는 Ubuntu 22.04/Humble에서 가장 작은 모드부터 순서대로 확인하는 것이 좋습니다.
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
ROBOT_SCOPE_DASHBOARD_ADDRESS=<운영자가_접속할_현재_Jetson_IP>
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
접속 주소를 터미널에 함께 출력합니다. 다중 NIC host에서
`ROBOT_SCOPE_DASHBOARD_ADDRESS`를 설정한 뒤 installer를 적용하면 root 소유 operator
address 설정을 우선 사용합니다. 값이 없을 때만 SSH 세션이 접속한 서버 IP와 local route를
차례로 사용합니다. 설정값은 RFC1918 또는 link-local host IPv4만 허용하며 HTTP listener는
계속 `0.0.0.0:<port>`에서 같은 LAN 접근을 받습니다.

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
