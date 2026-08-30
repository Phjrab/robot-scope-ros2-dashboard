# 문제 해결

먼저 로봇에 명령을 보내지 않는 검사부터 수행합니다. 오류를 해결하기 위해 방화벽, sudoers,
relay packet filter 또는 제어 graph gate를 무작정 완화하지 마세요.

## 공통 진단 순서

브라우저에 접속할 수 있다면 먼저 Settings의 **Export diagnostics**를 사용합니다. 이
기능은 제어·매핑·Navigation·데이터셋을 중지하지 않고, 고정된 공개 상태와 최근 bounded
event만 `robot-scope-diagnostics-<timestamp>.zip`으로 내려받습니다. 키, credential,
Authorization, 전체 environment, raw child argv/output, 절대 경로와 raw ROS message는
포함하지 않습니다. browser session ID는 요청 상관관계용이며 실제 사용자 신원이 아닙니다.

ZIP 생성도 실패하거나 대시보드에 접속할 수 없을 때만 아래 읽기 전용 명령으로
진행합니다.

~~~bash
python3 scripts/robot_scope_doctor.py --mode observer
systemctl status robot-scope.service --no-pager
journalctl -u robot-scope.service -n 150 --no-pager
curl -fsS http://127.0.0.1:8088/api/v1/health
ip -br -4 address
ip route
~~~

SSH operator helper를 설치한 호스트에서는 고정된 안전 속성과 최근 로그를 다음처럼 볼 수
있습니다. `status`는 allowlist 속성만 출력하고, `logs`는 environment를 직접 조회하지 않는
일반 journal 출력입니다. 로그를 타인에게 공유하기 전에는 비밀값과 운영 주소를 검토해
마스킹합니다.

~~~bash
robot-scope-dashboard status
robot-scope-dashboard logs
~~~

`start`, `stop`, `restart`가 blocker 또는 transition timeout으로 실패하면 즉시 반복하지
말고 위 두 명령과 대시보드 작업 상태를 확인합니다. timeout은 systemd 작업이 아직 진행
중일 수 있다는 뜻입니다.

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

- XT16 bridge는 저장소의 `ros2/robot_scope_xt16_bridge`를 현재 checkout에서 Release로
  빌드한 실행 파일이어야 합니다. 실행 파일이 없으면
  `scripts/build_xt16_bridge_humble.sh`를 실행하고, Python contract reference나 홈
  디렉터리의 이전 prototype을 runtime으로 사용하지 않습니다.
- Laser map 저장은 `scripts/save_map.py`, 2D 변환은
  `scripts/convert_pcd_to_occupancy.py`를 사용합니다.
- 홈 디렉터리의 이전 prototype이 실행되고 있지 않은지 확인합니다.
- FAST-LIO가 참조하는 `xt16.yaml`과 실제 bridge field layout을 함께 확인합니다.
- `/Laser_map`은 publisher 존재만이 아니라 비어 있지 않은 새 sample이어야 합니다.
- 매핑을 중지한 뒤에도 `/lidar_points`와 `/velodyne_points`는 정상적으로 계속 발행됩니다.
  둘 다 사라졌다면 mapping start를 반복하기 전에 mapping control의 `preview` 상태와
  `hesai_preview.log`, `xt16_preview_bridge.log`를 확인합니다.
- `/velodyne_points`는 LIVE인데 `/Laser_map`만 없다면 원시 미리보기는 정상이고 FAST-LIO
  매핑 세션만 중지된 상태일 수 있습니다.
- `/lidar_points`는 10 Hz인데 bridge 로그에 `callback backlog residual`이 반복되면
  `python3 scripts/robot_scope_doctor.py --mode go2-xt16`의
  `xt16.dds_receive_buffer`를 확인합니다. timestamp/freshness 한계를 임의로 완화하지 말고
  `docs/DEPENDENCIES.md`의 고정 sysctl 파일을 적용한 뒤 DDS socket drop과 동일
  acceptance를 다시 측정합니다.

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

외부 dashboard가 Go2 전용 `192.168.123.0/24` NIC를 소유하지 않는 완전 무선 구성에서는
범용 route나 multicast bridge를 추가하지 말고 고정 카메라 relay를 확인합니다.

~~~bash
systemctl status robot-scope-go2-camera-relay.service --no-pager
systemctl is-enabled robot-scope-go2-camera-relay.service
systemctl is-active robot-scope-go2-camera-relay.service
journalctl -u robot-scope-go2-camera-relay.service -n 80 --no-pager
~~~

수동 정책의 기대값은 `disabled`와 카메라 사용 중 `active`입니다. 로그에서 source가
`192.168.123.161`, 입력이 `230.1.1.1:1720`, 고정 목적지가 `192.168.50.10:1720`인지
확인합니다. `captured=accepted`이고 sequence loss와 rejection이 0인데 Dashboard가
`WAITING`이면 외부 host에서 UDP 1720 listener, `ROBOT_SCOPE_CAMERA_INTERFACE=eno1`, 방화벽
및 동일 포트를 먼저 확인합니다. relay 검사를 위해 Go2 본체 IP, DDS interface 또는 control
target을 `.50.30`으로 바꾸지 않습니다.

RealSense만 보이지 않으면 로봇 탑재 Jetson에서 다음을 확인합니다.

~~~bash
realsense_relay_host=192.168.123.18
python3 scripts/robot_scope_doctor.py --mode observer \
  --realsense-relay-env-file "$HOME/.config/robot-scope/realsense-camera.env"
systemctl status robot-scope-realsense-camera.service --no-pager
systemctl is-enabled robot-scope-realsense-camera.service
systemctl is-active robot-scope-realsense-camera.service
ls -l /dev/v4l/by-path/*-video-index0
curl -fsS "http://${realsense_relay_host}:8090/health"
journalctl -u robot-scope-realsense-camera.service -n 80 --no-pager
~~~

Doctor는 env 존재·형식·mode `0600` 권한·주소 쌍·bounded capture profile과 로컬 bind 주소를
읽기 전용으로 검사합니다. 원격 host를 수정하거나 Wi-Fi 설정, route, service 상태를
변경하지 않습니다. `INVALID_CONFIG`, `BIND_ADDRESS_MISSING`,
`DASHBOARD_ADDRESS_REJECTED`, `DEVICE_NOT_FOUND`, `ENCODER_UNAVAILABLE`,
`SOURCE_STALE` 중 하나가 service 로그에 나오면 해당 원인을 해결하며 public bind나 넓은
client allowlist로 우회하지 않습니다.

WP01 설정 계약을 rollback해야 하면 Git history를 재작성하지 말고 WP01 commit을
`git revert`합니다. 배포 host에서는 그 revert로 복원한 relay script와 service example을
검토한 뒤, 기존 reference 두 주소만 사용하던 env를 복구합니다. WP01 직전 repository
기준선은 `de69843`입니다. 실제 unit 교체나 restart는 별도 승인된 유지보수 시간에만 하고,
rollback 중에도 `0.0.0.0` bind 또는 dashboard 이외 client 허용은 사용하지 않습니다.

`Cannot assign requested address`가 반복되면 service를 먼저 중지하고
`~/.config/robot-scope/realsense-camera.env`의 bind 주소가 `ip -br -4 address`에 실제로
존재하는지 확인합니다. Dashboard 쪽 `ROBOT_SCOPE_REALSENSE_RELAY_HOST`도 같은 relay
주소여야 합니다. Go2 본체의 `ROBOT_SCOPE_ROBOT_IP`는 이 문제를 해결하기 위해 바꾸지
마세요. 수동 운영 host에서는 `disable --now`로 재시작 반복을 멈춘 후 설정과 unit을
검증하고 `start`만 사용합니다.

relay는 by-path 후보 중 sysfs vendor `8086`, product `0b3a`, USB color interface `03`,
V4L index `0`을 모두 만족하는 D435i RGB 장치가 정확히 하나일 때만 시작합니다. D435i의
depth와 color interface가 동일한 by-id `video-index0` 이름을 주장할 수 있으므로 by-id
symlink만으로 color 장치를 판정하지 않습니다. USB 재연결 뒤에도 검증 장치 수가 예상과
다르면 조건을 넓히지 말고 실제 모델의 V4L2 인터페이스 역할을 확인하세요. `is-enabled`는 부팅 정책(`enabled` 자동 시작,
`disabled` 수동 실행), `is-active`는 현재 프로세스 상태이므로 둘을 따로 판정합니다.

`/health`가 `idle`인 것은 viewer가 없는 정상 상태일 수 있지만 JPEG 생성 검증은 아닙니다.
다음 검사는 반드시 `/stream` 접근이 허용된 dashboard host에서 실행합니다.

~~~bash
realsense_relay_host=192.168.123.18
relay_capture=/tmp/robot-scope-realsense-stream.mjpeg
curl -fsS --max-time 5 "http://${realsense_relay_host}:8090/stream" -o "$relay_capture"
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

지속 스트림을 제한 시간에 끊은 curl 코드 28만 예외로 허용합니다. 완전한 JPEG를 받았는데도
Dashboard에 프레임이 없으면 `.18:8090` TCP 경로는 통과한 것이므로 Sensors 화면을 연
상태에서 Dashboard camera WebSocket, `realsense_color` 상태와 service 로그를 확인합니다.
새 relay 파일을 설치했는데 PID나 동작이 그대로라면 `enable --now`를 반복하지 말고 enable
상태를 보존한 채 `sudo systemctl restart robot-scope-realsense-camera.service`를 실행합니다.

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
- Settings 확인 체크와 브라우저 확인 대화상자
- strict `confirmed=true`
- 정확한 sudoers allowlist
- control, navigation, mapping과 저장 작업이 모두 idle

별도 사용자 인증은 제공하지 않으므로 신뢰 LAN 밖에서는 활성화하지 않습니다. 문제 해결을
위해 sudoers에 wildcard, reboot 또는 다른 unit을 추가하지 마세요.

## Cockpit panel 또는 센서 상태가 복구되지 않음

1. Safety HUD의 Robot Link, Bridge, LowState와 control source를 먼저 확인합니다.
2. Camera/LiDAR가 이전 영상이나 점군을 보여도 `LIVE`가 아니면 현재 sensor 증거로
   사용하지 않습니다.
3. 해당 panel을 compact했다가 다시 열기보다 닫고 다시 열어 viewer/polling demand가 하나로
   복구되는지 확인합니다.
4. Cockpit에서 Overview로 이동한 뒤 다시 들어와 PointCloud owner가 하나인지 diagnostics를
   확인합니다. route 왕복으로 socket 수가 계속 증가하면 motion을 시작하지 않습니다.
5. corrupted layout은 Layout Edit의 recovery/default preset으로 복구합니다. localStorage를
   개발자 도구에서 임의 수정하거나 safety state를 layout에 넣지 않습니다.

Browser reload, BFCache 복귀 또는 relay restart 뒤에도 stale frame이 LIVE로 바뀌거나
자동 ARM되면 안전 실패입니다. SOFTWARE STOP 또는 물리 정지 수단을 사용하고 diagnostics를
보존한 뒤 재현 절차를 기록합니다.

## Manual Takeover가 READY_TO_ARM이 되지 않음

Mission panel에서 active Mission이 `PAUSED` 또는 terminal `ABORTED`인지, Navigation goal이
terminal인지, pipeline이 inactive인지, navigation lease가 released인지 순서대로 확인합니다.
cleanup timeout을 늘리거나 control gate를 우회하지 않습니다. `RETRY CLEANUP`도 실패하면
Navigation STOP을 확인하고 물리적으로 stationary인 상태에서 private service 로그를
조사합니다. READY_TO_ARM은 ARM이 아니므로 Controls에서 별도 ARM 전에는 움직이지 않아야
합니다.

## Mission이 PAUSED 또는 FAILED에서 진행되지 않음

- PAUSED의 `operator_confirmation`은 운영자의 명시적 Resume이 필요한 정상 상태입니다.
- map/annotation revision이 달라졌다면 기존 Mission을 수정하지 말고 현재 revision으로 새로
  생성합니다.
- FAILED에서는 log의 bounded reason과 Navigation 상태를 확인한 뒤 Retry 또는 Skip을 한 번만
  누릅니다. 자동 반복 click이나 무한 retry를 사용하지 않습니다.
- server restart 후 `interrupted` Mission은 자동 resume되지 않는 것이 정상입니다.
- Abort가 goal cleanup을 확인하지 못하면 manual command를 보내지 말고 Navigation STOP과
  물리 정지 수단을 사용합니다.

실제 장비 문제와 browser-only 문제를 분리할 때는
[Cockpit Acceptance](COCKPIT_ACCEPTANCE.md)의 status 표와
[Cockpit 운영자 가이드](COCKPIT_OPERATOR_GUIDE.md)를 사용합니다.

## 지원 요청에 포함할 정보

- Robot Scope commit SHA와 설치 mode
- Ubuntu/아키텍처/Python/ROS/RMW 버전
- doctor의 비밀값 제거 결과
- 관련 service의 최근 로그
- 토픽 이름, type, publisher 수와 freshness
- 문제 발생 시각과 로봇/센서 전원 상태

비밀번호, control bridge key, SSH 개인키, 전체 `.env`와 실제 경기장 지도는
첨부하지 않습니다.
