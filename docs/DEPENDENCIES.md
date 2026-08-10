# 의존성 및 재현 가능한 배포 기록

Robot Scope 저장소만으로 웹 UI와 Generic 계층을 구성할 수 있지만, Go2·XT16·FAST-LIO
전체 경로는 외부 ROS workspace와 현장별 설정을 사용합니다. 외부 구성의 출처와 버전을
기록하지 않으면 다른 호스트에서 같은 동작을 재현할 수 없습니다.

## 기본 운영체제 패키지

Ubuntu 22.04에서 설치 모드에 따라 다음 범주가 필요합니다.

| 범주 | 대표 패키지 | 적용 모드 |
|---|---|---|
| 기본 도구 | `git`, `python3`, `python3-venv`, `python3-pip`, `curl` | 전체 |
| 네트워크/프로세스 | `iproute2`, `iputils-ping`, `procps`, `coreutils` | 전체 |
| ROS | ROS 2 Humble, `rmw-cyclonedds-cpp` | 전체 |
| 카메라 | GStreamer tools, good/bad/libav plugins | `go2` 이상 |
| 내비게이션 | `ros-humble-navigation2`, `ros-humble-nav2-bringup` | `go2-nav` |
| 개발 검증 | Node.js, Python test dependencies | contributor/CI |

사용자 영역 설치는 `scripts/install_ubuntu.sh --mode MODE --apply`에 맡기고, 문서의
목록을 무조건 한 번에 설치하지 마세요. System package는
`--install-system-packages`를 함께 명시했을 때만 installer가 sudo로 설치합니다. 제조사
workspace와 운영체제 패키지는 pinned revision의 지침 및 승인 기록과 함께 관리합니다.

## 저장소 내부 Python 의존성

`requirements.txt`에는 FastAPI, NumPy, PyYAML, Uvicorn, WebSockets의 호환 범위가
기록되어 있습니다. 현재 범위 지정은 보안 패치 수용에는 유리하지만 byte-for-byte
재현 가능한 lockfile은 아닙니다.

운영 release를 만들 때는 다음 정보를 함께 보관하는 것을 권장합니다.

- Robot Scope tag와 commit SHA
- Python 버전과 아키텍처
- 실제 설치된 Python 패키지 목록
- ROS 배포판과 RMW 구현
- 아래 외부 구성 manifest

## 외부 구성 manifest

외부 ROS 저장소의 설치 기준 URL, commit, 라이선스와 target은 단일 source of truth인
`config/ros_dependencies_humble.json`에 고정되어 있습니다. Bootstrap은 이 manifest를
따라야 하며 branch의 최신 HEAD로 임의 이동하면 안 됩니다. 현장별 비공개 artifact가
추가되면 내부 artifact ID와 SHA-256을 별도 inventory에 기록합니다.

아래 경로는 `ROBOT_SCOPE_WORKSPACE_ROOT`가 비어 있을 때의 기본값입니다. 일반
`robot-scope.env`에 절대 경로를 지정하면 installer, bootstrap, doctor와
runtime runner가 같은 root를 사용합니다.

| 구성 요소 | 기본 탐색 위치/인터페이스 | 필수 기록 | 저장소 포함 여부 |
|---|---|---|---|
| Unitree ROS 2/Cyclone DDS | `~/unitree_ros2` | manifest URL/commit, 라이선스 | 미포함 |
| Go2 환경 helper | `scripts/setup_go2_ros2_humble.sh` | Robot Scope commit, NIC/CIDR 계약 | 포함 |
| Hesai ROS 2 driver/SDK | `~/ws/hesai_ws` | manifest URL/commit | 미포함 |
| Hesai XT16 config | `config/hesai_xt16.yaml` | Robot Scope commit과 driver pin | 포함 |
| Livox SDK2 | `~/ws/livox/sdk2_install` | manifest URL/commit, 라이선스 | 미포함 |
| FAST-LIO ROS 2 | `~/ws/fastlio_ws` | manifest URL/commit | 미포함 |
| FAST-LIO XT16 config | `config/fastlio_xt16.yaml` | Robot Scope commit과 FAST-LIO pin | 포함 |
| Livox message overlay | `~/ws/livox/ws_livox` | manifest URL/commit | 미포함 |
| XT16 bridge | `scripts/xt16_fastlio_bridge.py` | Robot Scope commit과 테스트 결과 | 포함 |
| Laser map saver | `scripts/save_map.py` | Robot Scope commit과 테스트 결과 | 포함 |
| PCD→2D converter | `scripts/convert_pcd_to_occupancy.py` | Robot Scope commit과 테스트 결과 | 포함 |
| 로봇 모델 assets | `robot_dashboard/static/assets` | 하위 manifest와 라이선스 | 포함 |

내장 bridge, saver와 converter는 핵심 매핑 기능에 필요합니다. Installer와 doctor는 현재
checkout의 파일을 검사해야 하며 홈 디렉터리의 오래된 prototype이나 외부 `pcd2pgm`을
우선하지 않습니다.

현재 pinned 외부 source는 다음과 같습니다. 값이 바뀌면 코드와 현장 검증을 다시
수행하고 manifest 변경을 review해야 합니다.

| 구성 | Repository | Commit | License |
|---|---|---|---|
| Unitree ROS 2 | `unitreerobotics/unitree_ros2` | `668d1ec5a05d1c38d3306bdca7d59f2ba3581a88` | BSD-3-Clause |
| Hesai ROS 2 | `HesaiTechnology/HesaiLidar_ROS_2.0` | `e7e112f0809f0eed5e3c81c55a1a0376474db234` | BSD-3-Clause |
| Hesai SDK submodule | `HesaiTechnology/HesaiLidar_SDK_2.0` | `9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168` | upstream license 확인 |
| Livox SDK2 | `Livox-SDK/Livox-SDK2` | `08f523c930b2f0ba1e98a6afaa8d7476bf479908` | MIT |
| Livox ROS driver 2 | `Livox-SDK/livox_ros_driver2` | `4a1def929e5b59c7a8122d19fce6efba581ce9f7` | MIT |
| FAST-LIO ROS 2 | `Ericsii/FAST_LIO` (`ros2`) | `2fffc570a25d0df172720bac034fbdb6a13d2162` | GPL-2.0-only |

### Pinned source bootstrap

다음 명령은 변경 없이 수행 계획만 보여 줍니다.

~~~bash
./scripts/bootstrap_ros_dependencies.sh --mode go2-xt16
~~~

Ubuntu/ROS build package를 먼저 설치한 뒤 target 사용자로 적용합니다. Root로 실행하지
마세요.

~~~bash
./scripts/bootstrap_ros_dependencies.sh --mode go2-xt16 --apply
~~~

기존 target이 있으면 bootstrap은 origin, exact commit, tracked clean 상태를 확인하고
하나라도 다르면 종료합니다. 사용자의 workspace를 reset, pull 또는 덮어쓰지 않습니다.

## 모드별 최소 의존성

### observer

- Ubuntu 22.04 (`x86_64` 또는 `arm64`)
- ROS 2 Humble과 Python `rclpy`
- `requirements.txt`의 Python 패키지

### go2

- `observer` 전체
- 검증된 Unitree ROS 2/Cyclone DDS workspace
- 저장소의 Go2 전용 NIC 설정 helper
- 직접 카메라를 쓸 경우 GStreamer plugins

### go2-control

- `go2` 전체
- 독립 control bridge service
- 32바이트 이상의 무작위 bridge key
- 현장별 publisher/subscriber 수 검증

### go2-xt16

- `go2` 전체
- Hesai driver, Livox SDK2, FAST-LIO와 Livox message overlay
- 저장소의 XT16 bridge, Laser map saver와 PCD→2D converter
- 직접 수신 또는 [허용된 릴레이 토폴로지](TOPOLOGY.md)

### go2-nav

- `go2-control`과 `go2-xt16` 전체
- ROS 2 Humble Nav2
- 검증된 PGM/YAML 지도
- 저장소의 고정 navigation runtime과 parameter base

## 라이선스와 재배포

Robot Scope 본체와 저장소에 포함된 모델 assets의 고지는
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)에 정리되어 있습니다. 외부
workspace와 현장별 추가 artifact는 이 저장소 배포물에 포함되지 않으므로 그 라이선스가
자동으로 정리되지 않습니다.

다른 사용자에게 source archive, 설치 이미지 또는 완성된 Jetson 이미지를 전달할 때는
그 이미지에 포함된 모든 외부 구성의 라이선스와 NOTICE 의무를 별도로 확인하세요. 단순히
Robot Scope가 MIT라는 이유로 전체 ROS 이미지가 MIT가 되는 것은 아닙니다.

특히 현재 pinned FAST-LIO는 `GPL-2.0-only`입니다. FAST-LIO가 포함된 완성 이미지나
배포물을 전달하기 전에는 해당 라이선스의 source 제공·고지 의무를 검토하고 충족해야
합니다. Robot Scope 저장소만 공개하는 것과 외부 ROS workspace까지 포함한 시스템
이미지를 배포하는 것은 라이선스 범위가 다릅니다.

## 배포 기록 예시

비밀번호, 토큰, SSH 키와 실제 운영 주소를 제외하고 다음 형식으로 기록합니다.

~~~text
Robot Scope: <tag>, <commit>
Platform: Ubuntu 22.04, <x86_64|arm64>, Python <version>
ROS: Humble, <RMW>, ROS_DOMAIN_ID=<non-secret value>
Mode: <observer|go2|go2-control|go2-xt16|go2-nav>
Unitree workspace: <repository/artifact>, <commit>, <sha256 if artifact>
Hesai workspace/config: <repository>, <commit>, <config sha256>
FAST-LIO workspace/config: <repository>, <commit>, <config sha256>
Repository bridge/saver/converter: <Robot Scope commit>
Installer/doctor result: <date>, <pass/fail>, <non-secret report location>
~~~
