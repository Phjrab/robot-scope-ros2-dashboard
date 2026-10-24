# Maps 관측기 시작·종료 연결

Maps의 기존 **저장 지도 · 실험 관측**에서 관측 FAST-LIO를 시작하고,
신선한 입력이 준비되면 현재 pose를 지도 기준점에 연결한다.
소프트웨어 구현과 로봇 설치·실행은 별도이며, 이 문서 작성 시 장비 적용은 대기 중이다.

## 사용 순서

1. 사용할 저장 3D 지도를 선택한다.
2. **관측 시작 (30분)**을 누른다. 새 실행은 이전 기준점과 정합 결과를 해제한다.
3. **입력 준비 완료**가 되면 **2. 기준점 설정**을 누른다.
4. 현재 위치·방향의 근사값을 입력하고 정지 상태 확인을 체크한 뒤
   **현재 pose를 기준점에 연결**을 누른다. 기본값 0은 검증된 위치가 아니다.
5. 고급 관측 옵션의 **지도 정합 반복 계산**을 켠다. ROS 환경에서 메시지별
   publisher 정보를 제공하지 않을 때에는 설명을 확인하고 기존
   **출처 미검증 관측 후보 허용**을 명시적으로 선택해야 한다.
6. 정합 상태·잔차·overlap과 pose를 확인한다. **입력 준비 완료**는 지도 정합
   성공을 의미하지 않는다. 원래 5cm/잠정 10cm 잔차 기준은 그대로다.
7. 종료하려면 **관측 종료**를 누른다. 30분이 지나도 자동 종료되며 자동 연장하지 않는다.

실제 입력은 `/Odometry` (`camera_init → body`, FAST-LIO IMU)와
`/cloud_registered` (`camera_init`)다. 시작 후 발견된 해당 토픽을 선택한다.
본체 중심 교정, 절대 위치 정확도, 전역 자동 위치 찾기를 이 기능이 검증하지 않는다.
재시작 후 현재 위치를 모르면 임의로 원점에 연결하지 않는다.

## 실행 계약

`GET /api/v1/observations/fastlio`는 캐시되지 않는 상태 조회다.
같은 출처의 `POST .../start`는 `{ "confirmed": true }`, `POST .../stop`은
여기에 화면이 확인한 32자리 `session_id`를 더한다. 오래된 화면의 종료 요청은
현재 systemd InvocationID와 다르면 거부한다. 명령 실행 결과가 불명확해도
POST를 자동 재시도하지 않는다. 별도 관리자가 동시에 unit을 재시작하는 경우의
조회→명령 사이 원자성은 보장하지 않으므로 장비 작업을 겹치지 않는다.

서버의 monotonic 시계로 실행 잔여 시간을 계산한다. 브라우저는 수신 이후
경과 시간만 차감하고 다음 조회로 갱신하며, 브라우저 벽시계와 서버 벽시계를 비교하지 않는다.
READY에는 이번 실행 이후 받은 1초 이내 pose·비어 있지 않은 점군과
최근 3초 이내 단일 publisher graph 정보가 필요하다. 이는 메시지별 출처 검증이 아니다.

시작 시 mapping/navigation/control/dataset 등의 소유권과 bridge inactive를 확인한다.
관측 중에는 기존 lifecycle 진입점이 충돌 작업 시작을 거부하고 bridge STOP은 유지한다.
상태 조회 실패·잠금 경합은 idle로 간주하지 않는다. launcher도 `/proc`의 기존
FAST-LIO를 검사한다. 임의의 외부 ROS 실행과 공유하는 전역 잠금은 아니다.

## 설치와 복구

장비별 경로와 기존 설치 해시를 확인하고 사용자 승인 후 적용한다.
기존 설치 전체를 git pull/reset하지 않는다.

- 소스 13개: app, application의 runtime/observation_runtime/lifecycle_coordinator/
  ownership_readback/fastlio_observation, observation_service, API의 observations/
  fastlio_observation, Maps의 live_observation.js/css 및 observation_session.js,
  scripts/start_observation_fastlio.py.
- `deploy/robot-scope-observation.service.example`을
  `/etc/systemd/system/robot-scope-observation.service`에 설치한다.
- `deploy/robot-scope-observation.sudoers.example`을 `visudo -cf`로 검사하고
  `/etc/sudoers.d/robot-scope-observation`에 root 소유 0440으로 설치한다.
  고정 unit의 start/stop 두 명령만 허용한다.
- `/var/lib/robot-scope-observation/{log,pcd}`를 unitree 소유로 먼저 만든다.
  이 디렉터리만 FAST-LIO의 컴파일된 Log/PCD 경로에 private bind한다.
  launcher는 mount를 검사하고 이전 관측 출력은 sessions 아래에 보존한다.
- dashboard drop-in `60-observation-runtime.conf`에 `[Service]`와
  `Environment=ROBOT_SCOPE_OBSERVATION_RUNTIME_ENABLED=1`을 추가한다.
  기본값은 비활성이다. 기존 환경 파일·drop-in은 덮어쓰지 않는다.
- unit 검증 및 daemon-reload 후 승인된 dashboard 재시작 1회를 수행한다.
  service 소유 LiDAR preview 복구를 확인한다. 관측 unit은 boot enable하지 않는다.

관측 unit은 30분 한도, control-group 종료, dashboard BindsTo/PartOf를 갖는다.
기존 observation-only launcher를 사용해 TF/map/path 출력을 분리하고 PCD 저장을 끈다.
로봇 이동·자세 명령, control bridge 활성화, Nav2, 운영 TF 적용은 포함하지 않는다.

백업에는 기존 8개 소스와 기존 root 대상 파일의 존재 여부·권한·해시를 기록한다.
실패 시 이 관측 unit을 종료한 후 변경된 해시가 배포 후보와 일치하는 파일만
원복한다. 새 파일은 후보와 일치할 때만 제거한다. daemon-reload 및 dashboard
복구 후 preview·원본 지도/설정/로그 보존을 확인한다. 새 관측 로그는 삭제하지 않는다.

## 이번 검증 결과 (2026-10-24)

전체 Python 2,664개(4 skip), JavaScript 656개, 관련 브라우저 14개 통과.
새 기능의 시작·종료, 중복 실행, 실행 세대 변경, stale/잘못된 입력, 통신 실패,
새 기준점 요구를 합성 입력으로 확인했다. 실제 장비의 systemd 249와 visudo로
설치하지 않은 임시 후보 문법을 검사했고 16개 파일의 로컬 설치·원복 리허설을 통과했다.
실제 장비의 버튼 시작·입력 준비·정합·종료 검증은 승인 후 진행할 단계다.
