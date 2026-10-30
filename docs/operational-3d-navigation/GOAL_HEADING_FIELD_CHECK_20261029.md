# 방향 정렬 후보: 승인된 두 번의 현장 측정과 표시 수정

후속: [2026-10-30 배포 및 두 번의 현장 측정](GOAL_HEADING_FIELD_CHECK_20261030.md).
아래는 10월 29일 시점의 기록이며, 후속 UI 배포·실제 회전 성공·정지 후 잔차와 구분한다.

2026-10-29 KST. [후보 재현·패치 보고서](GOAL_HEADING_FIX_20261029.md)의 후속 기록이다.
사용자가 현장 준비와 새 목표 최대 2건, 각각 30초 이내를 승인했고 Navigation에서 직접
초기 위치와 두 목표를 입력했다. **두 실행 모두 CANCELED이며 정밀 도착은 미검증이다.**
사용자가 전원을 종료하겠다고 알려 Nav2를 종료하고 원본을 Mac private 폴더에 보존했다.
이후의 화면 수정과 검사는 장비 없이 수행했다. 추가 목표는 보내지 않았다.

## 실행 코드·라이브러리·설정

| 항목 | 실제 확인값 |
| --- | --- |
| 두 실행의 코드 / 실제 배포 SHA | `5c1ffe3ba3c070e67e143d39b65650cc8dba5f2e` |
| 배포 방식 | 별도 immutable release, 2,199개 source file hash 확인; dirty 사용자 checkout 보존 |
| Nav2 job | `e1363c4663a449fa82b2e16d7ee8e960` |
| Shim | Nav2 1.1.20 + 같은 시각 goal/body 조회 + 별도로 검증한 최종 회전 충돌 검사 패치 |
| 실제 controller에 로드된 .so SHA256 | `95c6ee9b0294651c182092031eb4926291946eb8e72be5cf1bfb976219f1754d` |
| 보존된 `/opt/ros` 원본 .so SHA256 | `1cd261a56261e20b10e1d3cc6da3ff14423b467bef23238c8dbc84235f6f0965` |
| 설정 revision | `71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387` |
| generated YAML SHA256 | `69804bc0a5dacf1122fe52e2a1aa313c8c65576525c2262f10eeea6783c50ccc` |

controller 프로세스의 `/proc/<pid>/maps`에서 후보 라이브러리의 실제 경로를 확인했다.
첫 배포의 standalone ament setup 경로 결함은 goal 전송 전에 발견해 `5c1ffe3`에서
고쳤다. package별 setup과 실제 .so 로드 검사를 통과한 뒤 이 세션을 시작했다.

| 설정 | 저장값 / 생성 YAML / 초기 정합 후 live readback |
| --- | --- |
| XY / yaw 허용오차 | .10m / .10rad, 모두 일치 |
| controller / primary | RotationShim / 기존 RPP |
| 선속도 / 주기 | .25m/s / 10Hz |
| goal checker | SimpleGoalChecker, stateful=true |
| 진행 검사 | SimpleProgressChecker, .20m / 10s |
| rotate_to_goal_heading / RPP use_rotate_to_heading | true / false |
| 회전속도 / 각가속도 / closed_loop | .50rad/s / 1.20rad/s² / false |
| NavFn tolerance / robot radius / inflation | .50m / .22m / .25m |
| RPP 접근 감속 거리 / 최소 접근 속도 | live .60m / .05m/s; generated YAML에는 생략된 upstream 기본값 |

초기 위치 입력 전 `map→odom`이 없을 때 planner activation과 live 조회가 대기했다.
사용자 Initial Pose를 접수해 실제 3D 정합이 끝난 뒤 readback은 `current`, lifecycle은
모두 active(3), missing_required는 모두 빈 목록이었다. 비활성 plugin 필드만
NOT_APPLICABLE로 처리됐다. 과거 조회나 생성 YAML을 live 값으로 대신하지 않았다.
PoseProgressChecker는 선택하지 않았으며 baseline으로도 자동 복구하지 않았다.

지도는 기존 묶음을 유지했다.

- 3D `map_20261027_125427_course_localization_20261028`, ID `e1dd40cc6911404dbdfc073b`,
  revision `c7d7ce7e04b2fb80519854cc71465f61af9fff210ac72e299105502497401ad5`.
- 2D `map_20261027_125427_operator_free_20261028`, ID `9a382e3eb990fb02fe1a3569`,
  revision `d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552`.
- 실제 source `STORED_PCD_FASTLIO`, `MAP_TRACKING`, `ALL_DIRECTION_BASELINE`.
  reference 13,546점, SHA256 `6ec38aa876ffcfe505ee81204d94fa84e1c3cb438ae706a6a6b7fc0048970b5a`.

## 두 실행 결과

| 항목 | 첫 실행 | 두 번째 실행 |
| --- | ---: | ---: |
| goal ID | `36ead6719c21db1152afb0e3a83068ac` | `b86cc8afa7c04477cfed0847adafdca5` |
| 요청 x / y / yaw(rad) | .636748 / .162612 / 1.198529 | 1.269368 / 1.341229 / -.503134 |
| 최종 action 결과 | CANCELED | CANCELED |
| feedback 주행시간 / recovery | 27.32s / 1 | 3.12s / 0 |
| 취소 원인 | 승인 기한을 지키기 위한 27초 Cancel 요청 | private 감시기의 navigation 조회 공백 감지 |
| 결과 수신 부근 XY / yaw | .216938m / -.541622rad (-31.03°) | 1.058093m / 1.788244rad (+102.46°) |
| 첫 측정 정지 후 XY / yaw | .238879m / -.636700rad (-36.48°) | 1.055811m / 1.862414rad (+106.71°) |
| TF future 오류 / progress abort | 4 / 1 | 0 / 0 |
| controller missed-rate 경고 / 충돌 오류 | 5 / 0 | 0 / 0 |

위 표는 성공 시각의 오차가 아니다. 두 번 모두 성공하지 않았고 Nav2 내부 success stamp도
없다. `near_result`의 source stamp는 결과 수신보다 각각 +34.672ms / +37.744ms이며,
pose는 map→base_link, 수신 당시 age는 83.283ms / 66.344ms였다.
첫 정지 표본의 source stamp는 결과 수신 +7.733s / +4.438s, age는
85.009ms / 54.552ms였다. 각각 기존 odom body 기반 2초 측정 정지 조건을 충족한
첫 표본이며, 한 번 충족한 사실과 이후 계속 유지되는지는 구분한다.

### 첫 실행: 최종 회전 진입 전의 접근 정체

보존된 map/body 표본 61개에서 최소 XY는 .189340m이고, .10m 내부 표본은 없다.
raw command 270개에서도 병진 0인 순수 회전은 관측하지 못했다. 따라서 이번 실행은
수정된 최종 회전의 성공 또는 실패를 검증한 표본이 아니다.
요청/전송 pose와 27개 planner 경로 끝점의 XY/yaw는 일치했다.

TF future 오류 4개는 시작 후 약 .126 / 1.229 / 2.234 / 3.235초에 발생했다.
±300ms 이내 연결되는 source pose의 XY는 .953 / .879 / .696 / .553m로 모두 접근 단계다.
같은 시각 goal 조회 패치 이외에 기존 sampled-path/접근 처리의 TF 조회가 남아 있다.
이 로그에는 실행 branch ID가 없어 어느 호출에서 발생했는지를 확정하지 않는다.
과거 68개와 시간·목표가 다르므로 단순 오류 감소율을 성능 개선으로 주장하지 않는다.

17.439초의 progress abort에 연결되는 XY도 약 .212m다. 이번 abort를 목표 10cm 안의
정상 최종 회전이 잘못 중단된 사례로 세지 않는다. RPP의 낮은 접근 명령이 전달되는 동안
몸체 진행이 작았다는 관측은 남지만, Go2 저속 응답·현장 조건·정합 보정의 기여를
분리하기 전 최소 속도나 진행 기준을 임의로 완화하지 않는다.
10.33→25.79초의 body odom 순변위는 XY 4.39cm, yaw +10.19°였다. 후기
.064~.083m/s·약 .10~.16rad/s 명령이 bridge에도 수신된 표본이 있다.

### 두 번째 실행: 계측 감시가 종료한 짧은 접근 표본

취소 사유는 private guard의 `NAVIGATION_OBSERVATION_LOST`다. navigation/control/source를
한 thread에서 차례로 조회했고, Navigation GET timeout 1건과 다른 조회 시간이 겹쳐 navigation
성공 조회 간격이 guard의 2.5초 경계를 넘었다. guard는 현재 goal ID를 고정해 기존 Cancel
API를 호출했다. 이를 실제 센서 상실, controller 방향 정렬 실패 또는 사용자 수동 취소로
표현하지 않는다. 이 3.12초 표본으로 최종 정밀 도착을 판단할 수 없다.

후속 계측은 navigation 감시와 보조 상태 수집·파일 저장을 분리하는 private 후보로 준비했다.
Navigation 2Hz, 보조 조회 1Hz, queue64/record512KiB/file48MiB 한계를 사용한다.
fake HTTP 오프라인 검사 7개에서 느린 보조 조회와 실제 navigation 조회 상실,
27초 Cancel 기한, 잘못된 상태, goal 교체 시 ID 고정·무재시도, 기록 한계를 확인했다.
센서 freshness, 실제 진행 검사, 승인된 30초 기한을 늘리는 해결은 사용하지 않는다.
이 후보의 ROS·장비 검증과 배포는 수행하지 않았다. 원본 기록기와 측정 자료는 보존했다.

## 취소 이후 몸체 움직임과 지도 보정

아래 값은 결과 수신 부근 표본에서 첫 측정 정지 표본까지의 변화다. 각도 부호는
최종−초기이며, map 보정과 odom body를 같은 source stamp의 SE(3)로 연결했다.

| 구간 변화 | 첫 실행 | 두 번째 실행 |
| --- | ---: | ---: |
| body odom XY / yaw | .038801m / -.103106rad (-5.9075°) | .012892m / +.081323rad (+4.6595°) |
| map→odom XY / yaw | .007810m / +.006378rad (+.3654°) | .009170m / -.007011rad (-.4017°) |
| map에 표시된 몸체 XY / yaw | .041633m / -5.4475° | .021588m / +4.2496° |

body odom은 센서로 추정한 몸체 이동이며 외부 ground truth는 아니다.
map→odom의 Z 변화도 약 +5.07cm / -5.11cm 있었다. 기존 `motion_vs_correction`의
3차원 이동 크기를 그대로 XY 변화라고 인용하면 안 된다. 명령 0 이후 잔여 몸체 변화와
지도 보정이 모두 있으므로 한쪽만으로 최종 오차를 설명하지 않는다.

두 goal의 dispatch/result/first_measured_stop가 실제 서비스 private sink에 각각 저장됐다.
마지막 관측 writer 누적 128 records, dropped=0/errors=0/pending=0이다. ROS raw 명령,
API 최종 명령과 bridge accepted 명령, odom/TF/plan을 함께 보존했다. API 표본은
각각 다른 시각에 조회됐으므로 같은 제어 cycle의 완전한 추적으로 표현하지 않는다.
read-only observer는 raw command를 최대 약 10Hz로 제한하므로 그 수신 간격을
controller 함수 실행시간의 p95 또는 실제 missed-rate 비율로 바꾸어 주장하지 않는다.
관측 수신 간격 median/p95/max는 첫 실행 99.974/108.327/204.942ms,
두 번째 100.106/151.160/177.879ms다. raw yaw 최대 .782/.793rad/s와 별도로
기존 중재·bridge .5rad/s 제한이 적용된 표본을 확인했다.

## 사용자 발견 화면 결함의 최소 수정

1. 정합 완료 후 현재 로봇은 별도의 원/선 marker 경로를 사용했다. 기존
   `drawRobotMapPreview()`와 공식 Go2 asset을 재사용해 녹색 현재 로봇으로 표시한다.
2. 실제 SavedMaps `/data` 응답의 식별자는 `map_id`인데 전송 후 goal overlay는 `id`만
   검사했다. 이에 목표가 사라졌다. 실제 응답 형식과 catalogue metadata를 올바르게
   처리하며 두 alias가 충돌하면 계속 거부한다. 테스트 fixture도 실제 `map_id`로 고쳤다.

전송된 목표는 보라색 모델과 상태 label, 현재 로봇은 녹색 모델과 ROBOT label로
구분한다. 새로고침 및 canceled/succeeded/failed 상태에서도 같은 goal/map revision에
속하는 목표를 유지한다. 다른 map/revision/frame, 잘못된 goal 증거는 숨긴다.
모델 loading/error 시 기존 marker fallback을 유지한다. Goal 전송·Cancel·안전 검사,
좌표 변환, controller·파라미터는 이 표시 수정에서 변경하지 않았다.

화면 수정은 이 보고서와 함께 게시한 후속 commit에 포함되며 **장비에는 아직 미배포**다.
현재 실제 장비 release는 위의 `5c1ffe3`이다. 사용자 CSS 두 파일은 별도 변경으로 보존한다.

## 검사·보존·복구 상태

- 해당 화면과 asset loading/failure, 회전 지도·HiDPI, 새로고침 목표 유지 E2E 및 이전
  CI 실패 항목의 로컬 확인: 5개 통과. 공식 asset을 사용한 synthetic UI 화면이며 현장
  로봇 결과와 구분한다.
- JavaScript 전체: 700개 통과. Python 전체: 3,132개 실행, 실패 0, skip 3.
  처음의 누락 의존성 실행은 별도 실패 로그로 보존하고, 기존 설치 의존성을 모두
  사용하는 환경에서 전체 검사를 다시 통과했다. frontend syntax/diff 검사도 통과했다.
- 배포 SHA `5c1ffe3`의 CI는 390px light 저장지도 레이아웃 비교 1건에서 실패했다
  (top 차이25.5px, 요구<1px; E2E226/227). 동일 항목은 현재 로컬 확인에서 통과했다.
  이를 원인 확정 또는 CI 통과로 표시하지 않으며 후속 commit CI 결과를 별도 보고한다.
- 이전 후보의 44개 native 검사 결과는 [기존 보고서](GOAL_HEADING_FIX_20261029.md)에 있다.
  이번 UI 수정 뒤 새 native 검사를 수행한 것으로 계산하지 않는다.
- private 원본은 기존 `goal-precision-20261029` 아래 `heading-trial-one`,
  `heading-trial-two`, `heading-native-evidence`와 분석 JSON에 보존했다. 원본 로그·지도·PCD·
  환경파일은 공개 Git에 포함하지 않는다.

| private 증거 | SHA256 |
| --- | --- |
| 서비스 events.jsonl | `bb5e23e1f3e0a02bb67afa7e362e11ec626cbd15be9275e4daf214643acf1c1c` |
| 배포 영수증 | `37b49d29144f289f3d47360b314a4d85bf2c70734d4bef83cda3be71c31facbe` |
| 종료 영수증 | `5c7f3f74aa2d3f4eb3670fafd59634d0e42277fb26f3937d051aabede3585b17` |
| 두 실행 분석 JSON | `002f780e8105a1cdf898517ed8624cc9eb2bf219d747f800b69467f0fa96ed31` |
| 개선 계측기 후보(미배포) | `ac614fac9fdfd731e3864089be291639e9299d6af59818f4a97174634726bee7` |

전원 종료 안내 전 pipeline=idle, lease.active=false, 최종 명령 세 성분 0,
SOFTWARE STOP=false를 확인했다. 잠긴 STOP을 해제한 작업은 없다. 첫 실행에서는 최초
정지 확인 뒤 `confirmed_now=false`인 표본도 있어 지속 정지를 주장하지 않는다.
두 번째 실행은 Nav2 stop 직전 fresh pose에서 연속 8.1995초 측정 정지를 확인했다.
source 종료 뒤 stale pose로 인한 false는 종료 전 정지 관측과 구분한다. 제어 브리지 기본 자동 시작
설정은 유지하며, STOP/리모컨 양도 뒤 반복 재기동하는 방식은 아니다.
남겨진 저장값은 .10m/.10rad 정밀 후보이며 사용자/복구 프리셋을 보존했다.
후보 overlay 선택도 유지됐다. 다음 전원 투입이 자동 goal 전송을 뜻하지 않는다.

복구가 필요하면 장비 idle·제어권 해제 확인 후 private selector 백업으로 이전 release와
overlay 선택을 복원한다. `/opt/ros` 원본을 덮어쓰지 않았다. 파라미터 baseline은 별도
복구 프리셋을 최신 revision의 CAS로 적용하고 새 generated/live 값을 확인해야 한다.

다음 한 작업은 수정된 계측을 먼저 검증한 뒤, 새 현장 승인 아래 **현재 위치에서 10cm
이내의 새 목표와 짧은 방향 차이**로 최종 회전 분기 자체를 분리 측정하는 것이다.
요청 목표 기준 SUCCEEDED + 첫 정지 및 정지 유지 구간의 XY≤.10m / |yaw|≤.10rad가
확인되기 전까지 방향 정렬 문제를 해결 완료로 표시하지 않는다.
