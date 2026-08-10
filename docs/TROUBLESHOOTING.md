# 문제 해결

먼저 로봇에 명령을 보내지 않는 검사부터 수행합니다. 오류를 해결하기 위해 방화벽, sudoers,
relay packet filter 또는 제어 graph gate를 무작정 완화하지 마세요.

## 공통 진단 순서

~~~bash
python3 scripts/robot_scope_doctor.py --mode observer
systemctl status robot-scope.service --no-pager
journalctl -u robot-scope.service -n 150 --no-pager
curl -fsS http://127.0.0.1:8088/api/v1/health
ip -br -4 address
ip route
~~~

실제 설치 mode로 doctor를 한 번 더 실행합니다. 출력에는 토큰이나 키를 넣지 말고, 지원을
요청할 때도 비밀값과 운영 주소를 제거합니다.

## 브라우저에서 접속할 수 없음

1. Robot Scope가 실행되는 Ubuntu ROS host 자체에서 health API가 응답하는지 확인합니다.
2. `robot-scope.service`가 active인지 확인합니다.
3. 브라우저 URL의 호스트와 포트가 실제 관리 LAN 주소인지 확인합니다.
4. 서버가 `0.0.0.0:8088`에 bind했는지 로그에서 확인합니다.
5. 인터넷 공유를 위해 Go2 전용 NIC의 주소를 바꾸지 않았는지 확인합니다.

공용망에 노출하기 위해 방화벽을 전체 해제하지 마세요. 필요한 경우 TLS와 접근 제어가
있는 reverse proxy를 사용합니다.

## Robot Link는 ONLINE인데 ROS/DDS는 오프라인

Robot Link의 ping과 ROS participant의 DDS interface는 별도 상태입니다. 실행 중에
전용 케이블을 연결해도 이미 생성된 participant는 자동으로 다른 interface로 이동하지
않습니다.

~~~bash
python3 scripts/robot_scope_doctor.py --mode go2
ip -br -4 address
ros2 topic list --types
~~~

전용 NIC와 CIDR을 고친 뒤 dashboard와 control bridge를 정상 재시작합니다. DDS domain,
RMW와 interface가 같은지 확인하기 전에는 제어를 활성화하지 않습니다.

## 센서 토픽 일부만 보임

~~~bash
ros2 topic list --types
ros2 topic info /lowstate --verbose
~~~

- 같은 이름의 다른 message type이 있는지 확인합니다.
- publisher 수만 보지 말고 dashboard의 freshness와 실제 sample을 확인합니다.
- Go2 profile에서 의도적으로 비활성화한 ROS 카메라는 직접 multicast 카메라와 혼동하지
  마세요.
- Settings의 선택 소스가 `PINNED`라면 sensor가 offline일 때 다른 토픽으로 자동 변경되지
  않습니다.

## XT16 raw 데이터가 없음

~~~bash
python3 scripts/robot_scope_doctor.py --mode go2-xt16
ros2 topic info /lidar_points --verbose
ros2 topic hz /lidar_points
~~~

1. XT16이 dashboard host로 직접 송신하는지, relay host로 송신하는지 토폴로지를 확인합니다.
2. Hesai config의 UDP source filter와 실제 packet source가 맞는지 확인합니다.
3. 두 호스트 구성이라면 relay service와 고정 packet counter를 relay host에서 확인합니다.
4. relay counter만 증가하고 `/lidar_points`가 새 데이터가 아니면 성공으로 판정하지 않습니다.

로봇이 꺼져 있거나 충전 중이면 relay/driver를 고치기 위해 센서 설정을 변경하지 말고 다음
실기 세션에 검증합니다.

## `/lidar_points`는 있지만 변환 또는 FAST-LIO가 없음

~~~bash
ros2 topic hz /lidar_points
ros2 topic hz /velodyne_points
ros2 topic hz /Laser_map
ros2 topic hz /Odometry
~~~

- XT16 bridge는 저장소의 `scripts/xt16_fastlio_bridge.py`를 사용해야 합니다.
- Laser map 저장은 `scripts/save_map.py`, 2D 변환은
  `scripts/convert_pcd_to_occupancy.py`를 사용합니다.
- 홈 디렉터리의 이전 prototype이 실행되고 있지 않은지 확인합니다.
- FAST-LIO가 참조하는 `xt16.yaml`과 실제 bridge field layout을 함께 확인합니다.
- `/Laser_map`은 publisher 존재만이 아니라 비어 있지 않은 새 sample이어야 합니다.

## Live Mapping이 끊기거나 지연됨

1. POINTS를 10K 또는 30K로 낮춥니다.
2. 사용하지 않는 Sensors 카메라 화면을 닫습니다.
3. 브라우저 개발자 도구에서 WebSocket이 binary 경로인지 확인합니다.
4. Wi-Fi RTT/jitter를 확인하고 가능하면 관리용 유선 NIC를 사용합니다.
5. Go2/XT16 전용 NIC를 브라우저 접속용 LAN으로 바꾸지 않습니다.

LAN에서 부드럽고 Wi-Fi에서만 끊기면 ROS publisher보다 관리망 지연을 먼저 의심합니다.

## 지도 저장 버튼이 비활성화됨

다음 조건을 확인합니다.

- 매핑 pipeline이 `RUNNING`인지
- 현재 세션에서 `/Laser_map` readiness가 확인됐는지
- start/stop/save/convert/navigation 작업이 전환 중이 아닌지
- 로봇과 XT16이 실제 데이터를 보내는지

이전 세션의 캐시가 화면에 남아 있어도 새 세션의 Laser map이 준비되지 않으면 저장 버튼이
꺼지는 것이 정상입니다. 버튼을 강제로 활성화하지 말고 원인 토픽을 복구합니다.

## 새 세션에서 Go2 내장 LiDAR로 보임

Settings의 LiDAR source와 `PINNED` 상태를 확인합니다. Go2 profile에서 XT16을 명시적으로
선택하면 상태 파일에 보존되고, publisher가 사라져도 해당 토픽이 `WAITING`으로 남아야
합니다.

~~~bash
curl -fsS http://127.0.0.1:8088/api/v1/sources
~~~

상태 파일을 직접 편집하지 마세요. Settings에서 허용된 소스를 선택하고 다시 조회합니다.

## 카메라 화면이 없음

~~~bash
python3 scripts/robot_scope_doctor.py --mode go2
gst-inspect-1.0 rtpjitterbuffer
gst-inspect-1.0 avdec_h264
~~~

- Sensors 메뉴를 열어 실제 viewer가 연결된 상태에서 확인합니다.
- 카메라 interface allowlist와 Go2 전용 NIC 이름이 같은지 확인합니다.
- GStreamer good/bad/libav plugins가 설치되어 있는지 확인합니다.
- multicast 경로가 관리 LAN으로 잘못 라우팅되지 않았는지 확인합니다.

## ARM 직후 DISARM됨

Control은 다음 조건이 하나라도 사라지면 fail-closed 합니다.

- control bridge의 최신 상태와 서명 키 일치
- 최신 LowState
- 고정된 publisher/subscriber graph 수
- 활성 브라우저 lease와 WebSocket heartbeat
- Shift 또는 선택 입력 장치의 deadman

로그를 확인하되 watchdog timeout과 graph gate를 늘려서 증상을 숨기지 마세요. 실제 로봇
시험 전에는 읽기 전용 `/api/v1/control` 상태만 점검합니다.

## Navigation이 시작되지 않음

- 관리 가능한 P5/255 PGM + YAML 묶음인지 확인합니다.
- map/parameter revision이 화면을 연 뒤 바뀌지 않았는지 확인합니다.
- XT16, `/Odometry`, `/scan`, TF와 signed bridge readiness를 확인합니다.
- 매핑 save/convert나 pipeline start/stop이 진행 중이지 않은지 확인합니다.
- 현재 지도 또는 Nav2 파라미터를 원본 파일에서 직접 수정하지 않습니다.

## 서비스 재시작/중지 버튼이 거부됨

서비스 lifecycle은 기본 비활성이고 다음을 모두 요구합니다.

- same-origin 요청
- 16자 이상의 관리 토큰과 일치하는 SHA-256
- 정확한 sudoers allowlist
- control, navigation, mapping과 저장 작업이 모두 idle

관리 토큰은 HTTP 요청에 포함되므로 신뢰 LAN 밖에서는 사용하지 않습니다. 문제 해결을 위해
sudoers에 wildcard, reboot 또는 다른 unit을 추가하지 마세요.

## 지원 요청에 포함할 정보

- Robot Scope commit SHA와 설치 mode
- Ubuntu/아키텍처/Python/ROS/RMW 버전
- doctor의 비밀값 제거 결과
- 관련 service의 최근 로그
- 토픽 이름, type, publisher 수와 freshness
- 문제 발생 시각과 로봇/센서 전원 상태

비밀번호, control bridge key, 관리 토큰, SSH 개인키, 전체 `.env`와 실제 경기장 지도는
첨부하지 않습니다.
