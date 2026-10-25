# Maps 관측기 시작·종료 연결

Maps의 기존 **저장 지도 · 실험 관측**에서 관측 FAST-LIO를 시작하고,
신선한 입력이 준비되면 현재 pose를 지도 기준점에 연결한다.
2026-10-24에 장비 적용과 실제 대시보드 시작→입력 준비→기준점 연결→지역 정합→종료를
확인했다. 마지막 검증 후 관측기는 정지했다. 아래 실제 결과와 정확도 한계를 구분한다.

## 사용 순서

1. 사용할 저장 3D 지도를 선택한다.
2. **관측 시작 (30분)**을 누른다. 새 실행은 이전 기준점과 정합 결과를 해제한다.
3. **입력 준비 완료** 후 고급 관측 옵션을 먼저 정한다. 이 장비처럼 ROS가 메시지별
   publisher 정보를 제공하지 않으면 설명을 확인하고 **출처 미검증 관측 후보 허용**을
   선택한다. 필요하면 **근사 연속 관측**도 선택한다. 모드를 바꾸면 기준점을 다시 연결해야 한다.
4. **2. 기준점 설정**에서 **초기 위치 자동 추정 → 제안값으로 채우기**를 누르거나
   프리셋/직접 입력으로 근사값을 준비한다. 값을 확인·수정하고 정지 상태 확인을 체크한 뒤
   **현재 pose를 기준점에 연결**을 누른다. 기본값 0은 검증된 위치가 아니다.
5. 고급 관측 옵션의 **지도 정합 반복 계산**을 켠다.
6. 정합 상태·잔차·overlap과 pose를 확인한다. **입력 준비 완료**는 지도 정합
   성공을 의미하지 않는다. 원래 5cm/잠정 10cm 잔차 기준은 그대로다.
7. 종료하려면 **관측 종료**를 누른다. 30분이 지나도 자동 종료되며 자동 연장하지 않는다.

실제 입력은 `/Odometry` (`camera_init → body`, FAST-LIO IMU)와
`/cloud_registered` (`camera_init`)다. 시작 후 발견된 해당 토픽을 선택한다.
본체 중심 교정과 절대 위치 정확도를 이 기능이 검증하지 않는다.
재시작 후 현재 위치를 모르면 임의로 원점에 연결하지 않는다.

## 초기값 프리셋

**2. 기준점 설정**에서 XYZ(m)·roll/pitch/yaw(°)와 이름을 입력하고
**입력값 저장**을 누르면 서버에 저장한다. 다음에는 목록에서 선택한 뒤
**초기값 불러오기**로 값을 채우고, 필요하면 수정하여 정지 상태를 확인한 후
**현재 pose를 기준점에 연결**한다. 이후 **지도 정합 반복 계산**으로 보완한다.
같은 이름은 덮어쓰지 않으며 수정한 값은 새 이름으로 저장한다.

저장 위치는 `--navigation-runtime-dir` 아래
`observation-anchors/<map_id>/presets.json`이다. 브라우저 새로고침과 서버
재시작 이후에도 유지되며 지도별 최대 64개를 저장한다. 저장 시각은 서버 UTC다.
지도 ID·revision·좌표계가 모두 일치하는 프리셋만 목록에 표시하고,
FAST-LIO IMU와 본체 기준이 다른 값은 현재 pose에 연결하지 않는다.

**현재 보정 위치로 채우기**는 신선한 지도 보정 pose가 있을 때 그 값을
입력란에 복사한다. 입력값은 수정·저장할 수 있으며 다시 확인해야 연결된다.
프리셋 불러오기와 값 채우기는 기존 기준점·반복 정합을 해제한다. 저장된 값은
근사 prior이며 이전 세션의 `T_map_odom`이나 timestamp를 복원하지 않는다.
관측 시작이나 기준점 연결을 자동 실행하지 않는다. 위치를 모르는 상태에서
지도 전체를 탐색하는 새 자동 제안 경로는 아래와 구분한다.

프리셋 소프트웨어 검증: 전체 Python 2,698개(4 skip), JavaScript 662개, 관련 브라우저
18개 통과. 저장·재조회·화면 재로딩, 지도/기준 프레임 불일치, 중복 이름,
저장 실패 시 자동 재시도 방지를 확인했다. 마지막 프레임 기준 보완 후 관련 브라우저
3개를 다시 통과했으며 실제 적용 결과는 아래와 같다.

### 프리셋 장비 적용 확인 (2026-10-24 22:00~22:04 KST)

`3c09bca`의 기능 8파일을 사용자 승인 후 설치했다. 기존 설치의 다른 변경은
유지하고 5파일 원본을 백업했으며, 새 3파일을 포함한 해시 검사와 중간 실패 시
원복 리허설을 통과했다. 장비 checkout HEAD는 `d7807de8`이고 이 변경은 선택
파일 overlay다. 백업은 `/home/unitree/robot-scope-validation/anchor-presets-20261024`다.

사용자가 직접 시작했던 관측을 화면에서 종료하고 대시보드를 22:00:18 KST에
1회 재시작했다. 서비스 소유 XT16 preview 복구, 관측 STOPPED, bridge inactive,
지도·설정·기존 로그 12개 해시 보존을 확인했다. 추가 FAST-LIO 실행은 하지 않았다.

승인된 과거 IMU 위치 XYZ(0.376, 0.439, 0.044)m / RPY(0.6, −0.5, 12.4)°를
**10/24 21:27 과거 위치 · IMU 근사**로 실제 화면에서 저장했다. 서버 저장 시각은
22:02:07 KST이며 실제 파일은 `/home/unitree/robot-scope-data/runtime/state/navigation/`
`observation-anchors/b9087113da92a1f2b477e932/presets.json`(0600)이다.
불러오기와 브라우저 새로고침 후 동일 6개 값 재로드를 확인했다. 확인 체크와
반복 정합은 꺼져 있고 현재 기준점에는 연결하지 않았다. 과거 위치를 현재 위치로
검증한 결과가 아니다. private `anchor-presets-20261024`에 설치 해시·서버/브라우저
readback·보존 검사·`installed-presets.png`를 저장했다.

## 자동 초기값 제안

관측 FAST-LIO를 실행하고 새 pose·점군이 준비되면 **기준점 설정 → 초기 위치
자동 추정**을 누른다. 숫자 초기값은 필요하지 않다. 실제 메시지별 publisher
정보를 제공하지 않는 장비에서는 기존 **출처 미검증 관측 후보 허용**을 명시적으로
선택해야 한다. 계산 중에는 정지하고 완료 후 **제안값으로 채우기**를 누른다.
제안된 6개 값은 수정·프리셋 저장할 수 있다. 모호한 후보는 그 사실을 표시하며
확인 체크 없이 자동 연결하지 않는다. 위치 확인 후 기준점을 연결하고 **지도 정합
반복 계산**을 켜면 기존 지역 정합으로 보완한다. 별도 전역 관측 패널의 과거 raw
LiDAR 후보를 IMU 값으로 직접 복사하지 않는다.

기존 global-jobs POST에 `input_kind=fastlio_imu`와 기존 출처 모드를 전달한다.
동일 worker 슬롯·취소·120초 한도·고정 backend를 재사용한다. 새 ROS 노드나 TF를
시작하지 않는다. `/cloud_registered`(camera_init)와 같은 stamp의 `/Odometry`
(camera_init→body, IMU)를 연결하고 `inverse(T_O_I(t0))`로 수신 캐시 점군을
캡처 IMU frame에 표현한다. 고정 LiDAR 외부변환은 사용하지 않는다. 캐시의 수신
모집단·샘플링 여부를 기록하며 원본 raw 전체점군이라고 주장하지 않는다.

전역 결과는 여전히 캡처 시점의 과거 기록이다. 새 read-only
`GET /api/v1/observations/global-jobs/{job_id}/anchor-proposal`은 지도 revision·frame,
pose/cloud epoch, 출처 허용 모드·subscription session/graph, 원본 stamp의 역행,
서버 monotonic 기준 1초 입력 신선도를 검사한다. 통과하면
`T_M_I(now) = T_M_I(t0) × inverse(T_O_I(t0)) × T_O_I(now)`를 6개 편집값으로 돌려준다.
원본 stamp를 보존하고 현재 시각으로 바꾸지 않는다. 새 세대에서는 다시 계산해야 한다.
UI도 늦은 응답·지도/출처 변경을 무효화하고 확인 체크와 반복 정합을 해제한다.
이 제안은 근사 prior다. 잔차는 절대 정확도가 아니고, 기존 지역 정합의 원래 5cm/
잠정 10cm 문턱을 변경하지 않는다. 승인 후 실제 장비 적용 결과는 아래와 같다.

자동 제안 소프트웨어 검증: 전체 Python 2,707개(4 skip), JavaScript 664개,
관련 브라우저 28개 통과. 최종 안내 문구 변경 후 자동 제안·늦은 응답 거부 브라우저
2개를 다시 통과했다. Python 검사는 Mac의 심볼릭 링크를 제거한 사용자 임시
경로에서 실행했고, 로컬 소켓을 사용하는 테스트는 sandbox 밖에서 실행했다.
정확한 stamp의 3D 재표현, 현재 pose 전파, 입력 신선도·세대·지도 변경,
선택 후보 부적격·취소, 명시적 출처 허용, 편집·확인 후 연결 경로를 확인했다.
배포 후보 7파일(기존 5/새 2)의 설치·부분 실패 원복·전체 원복과 동시 변경 보존을
로컬에서 검증했다. 이 소프트웨어 검사와 다음 실장비 측정을 구분한다.

### 자동 초기값 제안 장비 확인 (2026-10-24 22:40~22:48 KST)

사용자가 7파일 적용·재시작 1회·FAST-LIO 관측 1회(30분 한도)·전역 초기 추정
1회(120초 한도)를 승인하고 서서 정지·다른 장비 작업 없음으로 확인했다.
`e29808e`의 Python 3파일·UI 4파일을 설치했다. 장비 checkout HEAD는 `d7807de8`이며
선택 파일 overlay다. 기존 5파일 백업과 신규 2파일 제거 복구 자료는
`/home/unitree/robot-scope-validation/anchor-proposal-20261024/bundle`에 있다.
7파일 해시를 확인하고 대시보드를 22:40:20 KST에 1회 재시작했다. 서비스 소유
XT16 preview가 복구됐으며 부팅 ID는 실행 전후 동일했다. 다른 설치 변경은 보존했다.

고정 지도는 `b9087113da92a1f2b477e932`, `map_20261023_135003.pcd`, 41,073점,
저장 시각 2026-10-23 13:50:05 KST, revision
`58991300bd1aac8c872fd45cafdda6f3eaf2026e4e578d411a4cdba439d31f6a`다.
실제 대시보드에서 관측 시작 → 출처 미검증 관측 후보 허용·근사 연속 관측 →
초기 위치 자동 추정 → 제안값 채우기 → 확인·기준점 연결 → 지도 정합 반복 계산을
수행했다. 초기 좌표 입력과 과거 프리셋 불러오기는 하지 않았다.

전역 작업 `1f0a9c76334978a3257572de`는 11.508초에 완료됐다. 캡처는
`/cloud_registered`의 캐시 371점 전부이며 같은 원본 stamp
`1792849391905087709`의 `/Odometry`와 연결했다. `camera_init → body`는 FAST-LIO
IMU 기준이다. 선택 후보 잔차는 0.075287m, overlap 1.0이었다. 기존 서버 설정의
모호성 허용이 적용됐고 `AMBIGUOUS_ALTERNATIVES`는 해소되지 않았다. 화면에도
**모호한 후보 · 다른 위치일 수 있습니다**를 표시했다. 고유한 실제 위치를 확정한
결과가 아니며 원래 5cm 잔차 기준은 미통과다.

제안값을 누른 시점의 편집값은 XYZ `(0.211933, 0.444489, 0.035440)`m,
RPY `(0.581050, -0.009458, 6.399325)`°였다. 확인 후 연결한 지역 정합에서
`MAP_CORRECTED_ESTIMATE_ACCURACY_UNVERIFIED`와 현재 IMU pose·지도 마커·12관절
표시를 확인했다. 확인한 화면 표본의 지역 잔차는 약 0.0728~0.0758m, overlap 100%,
처리시간 약 75~117ms였다. 잠정 10cm 정책 적용이며 원본 5cm `HIGH_RESIDUAL` 판정은
화면에 남겼다. 보정 사이에는 `MAP_CORRECTION_UNAVAILABLE_ODOMETRY_CONTINUING`으로
odometry를 유지했다. UI 표본이므로 전체 실행의 성공률·지연 분포를 뜻하지 않는다.

22:43:02~22:47:23 KST의 읽기 기록에서 FAST-LIO pose 80개는 같은 observer/epoch와
증가하는 원본 stamp를 유지했다. 전체 상태 조회 91회에서 HTTP 오류는 없었다.
이는 센서부터 화면까지 지연이나 절대 정확도 측정이 아니다. 이번에는 정지 상태만
검증했으며 자동 제안 후 수동 이동 추적 검증은 하지 않았다.

검증 후 화면에서 관측 종료를 눌러 22:47:27 KST까지 STOPPED를 확인했다. 이전
지도 pose·잔차와 자동 초기값 연결은 해제됐다. 마지막 상태는 dashboard active,
preview running, global active 없음, sensor WAITING_GLOBAL, bridge inactive다.
지도·설정·기존 로그 12개 해시와 설치 7파일 해시를 다시 확인했다. 운영 TF·Nav2·
이동·자세 명령은 실행하지 않았고 프리셋도 추가·덮어쓰지 않았다.
private `anchor-proposal-20261024`에 `VALIDATION.json`, 원본 작업 결과,
서버/브라우저 기록, `map-with-auto-pose.png`, `map-corrected-status.png`,
종료 화면과 보존 검사 결과를 저장했다.

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

## 최초 소프트웨어 검증 (2026-10-24)

전체 Python 2,664개(4 skip), JavaScript 656개, 관련 브라우저 14개 통과.
새 기능의 시작·종료, 중복 실행, 실행 세대 변경, stale/잘못된 입력, 통신 실패,
새 기준점 요구를 합성 입력으로 확인했다. 실제 장비의 systemd 249와 visudo로
설치하지 않은 임시 후보 문법을 검사했고 16개 파일의 로컬 설치·원복 리허설을 통과했다.
이 시점에는 실제 장비 버튼 검증 전이었으며 최종 결과는 아래에 기록한다.

## 장비 적용·재부팅 후 검증 (2026-10-24)

사용자가 소스 13개와 systemd/sudoers/env 3개, dashboard 재시작 1회,
관측 1회(최대 30분)를 승인했다. `ebce05c`의 16파일을 백업·해시 검사 후 적용하고
16:22:43 KST에 dashboard를 재시작했다. 사용자 전원 종료로 첫 실행은 보류했다.
재부팅 후 같은 위치·방향에서 서서 정지했다고 다시 확인받았다.

21:02:56 KST에 고정 관측 unit 1개를 시작했고 화면에서 입력 준비와 12관절 수신을
확인했다. 최초 브라우저 시작 클릭에서는 실행되지 않았으며 이후 시작 API
1회 호출이 202로 수락됐다. 상태 조회 중 버튼을 비활성화하는 UI 경합을 확인해
GET을 취소하고 명시적 클릭을 우선하는 수정과 늦은 응답 무시를 추가했다.
실패 사유는 다음 GET 성공으로 지워지지 않는다. 수정 후 Python 2,664개(4 skip),
JS 656개, 관련 브라우저 15개가 통과했다. 당시 보완 파일은 추가 장비 적용 전이었다.

과거 지도 보정과 같은 과거 세대의 마지막 pose로 복원한 지도 위치를 **새 근사
초기값**으로 입력했다: XYZ(0.584183, 0.350412, 0.074929)m,
RPY(0.875887, −0.072668, 13.855244)°. 과거 T_map_odom 자체를 새 세대에 넘기지 않았다.
새 pose·registered cloud를 연결한 뒤 화면에서 지도 보정 상태와
XYZ(0.352, 0.432, 0.050)m / RPY(0.6, −0.5, 12.4)°를 관측했다.
해당 결과의 RMSE 0.06920m, overlap 1.0, 처리 139.6ms:
잠정 10cm 통과 / 원래 5cm 미통과이며 절대 위치 정확도는 미측정이다.
일시적인 STALE·상태 요청 timeout도 관측해 무중단 추적으로 보고하지 않는다.

21:09:06 KST에 장비가 다시 부팅되어 실행이 종료됐다. 사용자도 **자동 재부팅**을
확인했으며 Codex가 reboot/restart/stop 명령을 보낸 결과가 아니다.
부팅 식별자 변경, 새 dashboard PID와 inactive 관측기를 확인했다.
이전 부팅 journal이 영구 저장되지 않았고 pstore도 비어 있어 원인은 미확정이다.
현재 메모리·디스크 여유만으로 재부팅 직전의 전원·열·메모리 원인을 배제하지 않는다.
화면의 실제 종료 버튼 검증은 이 재부팅 때문에 미실시다. 승인된 실행 1회는 사용했고
추가 실행은 요청문 7항에 따라 별도 범위 확인 후 수행한다. 원본 지도·설정·기존
FAST-LIO 로그는 재부팅 후에도 12개 보존 대상 해시가 모두 일치했다. 관측기 inactive와
bridge inactive/disabled도 다시 확인했다.

## 버튼 보완 적용·실제 시작/종료 확인 (2026-10-24 21:24~21:28 KST)

사용자가 `observation_session.js` 1파일 적용·새로고침·추가 관측 1회(최대 30분)를
승인했다. `ace55b0` 수정과 다른 작업의 원격 main을 `5d78fcb`로 병합·push했다.
통합 상태에서 Python 2,691개(4 skip), JS 660개, 관측 브라우저 15개가 통과했다.
다른 작업의 로컬 CSS 2파일은 보존하고 커밋·장비 적용에 포함하지 않았다.

장비 checkout HEAD는 `d7807de8`이며 이번 연결 설치는 `ebce05c`의 선택 16파일,
버튼 보완은 `ace55b0`의 선택 1파일이다. 원격의 미션/VM 변경은 장비에 배포하지 않았다.
보완 파일 SHA-256은 `cacc5f08f4f267f5d2bf7e571cbfe1d0349ced22af0fea3ca6e68ba272b8e594`다.
원본 백업·부팅 ID/PID/해시 검사를 거쳐 적용했고 서비스 재시작은 하지 않았다.

고정 지도는 ID `b9087113da92a1f2b477e932`, `map_20261023_135003.pcd`,
2026-10-23 13:50:05 KST 저장, 41,073점이다. revision은
`58991300bd1aac8c872fd45cafdda6f3eaf2026e4e578d411a4cdba439d31f6a`다.
위에 기록한 근사 XYZ/RPY를 이번 새 pose에 연결했으며 과거 변환 자체는 재사용하지 않았다.

- 실제 **관측 시작 (30분)** 클릭으로 21:24:44 KST에 unit 1개가 실행됐다.
  InvocationID는 `f90920f914694e95b0fc513a35465b35`이며 새 pose·점군으로 READY를 확인했다.
- 기준점 연결 후 `MAP_CORRECTED_ESTIMATE_ACCURACY_UNVERIFIED`가 표시됐다.
  21:27:09 KST 화면 값은 XYZ(0.376, 0.439, 0.044)m, RPY(0.6, −0.5, 12.4)°,
  RMSE 0.07293m, overlap 100%, 처리 76.5ms였다. 잠정 10cm 통과 / 원본 5cm 미통과,
  절대 위치 정확도 미측정이며 IMU 기준 관측이다. 12관절과 odometry ΔZ −0.001m도 수신했다.
- 실제 **관측 종료** 클릭 후 21:27:11 KST에 unit이 정상 종료됐다. API STOPPED,
  MainPID 0, 남은 `fastlio_mapping` 프로세스 없음, 종료 로그 success를 확인했다.
  이번 실행 중 부팅 ID와 dashboard PID는 유지됐다. 지도·설정·기존 로그 12개 해시 일치,
  bridge inactive/disabled를 확인했다.

Mac에 약 3분간 입력 메타데이터·자원 132회(실행 중 84회)를 기록했다.
실행 중 pose/cloud의 서로 다른 seq가 각각 84개였고 pose age 최대 0.441초였다.
로봇 내부 HTTP 응답 p95는 pose 550ms / cloud 573ms, 샘플 요청 오류는 0이었다.
이는 센서→화면 전체 지연 측정이 아니다. 기록 중 최고 온도 58.843°C,
최소 MemAvailable 14,259MiB였고, 이전 자동 재부팅의 원인을 배제하는 근거로 쓰지 않는다.

증거는 별도 private `dashboard-observation-session-20261024` 디렉터리의
`followup-alignment.png`, `followup-ui-result.json`, `followup-stopped.png`,
`followup-final-readback.json`, `followup-runtime-samples.ndjson` 및 요약 JSON에 보존했다.
현재 기능의 버튼 경로는 실장비 정지 상태에서 확인했다. 이번에는 수동 이동·회전을
실시하지 않았으며 이전 자동 재부팅 원인과 장시간 안정성은 남아 있다.
