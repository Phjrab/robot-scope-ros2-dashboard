# 최종 방향 정렬 후속 현장 측정 — 2026-10-30

[10월 29일 현장 기록](GOAL_HEADING_FIELD_CHECK_20261029.md)과
[version-pinned Shim 수정](GOAL_HEADING_FIX_20261029.md)의 후속이다.
이번 두 시험의 **정밀 도착 완료 기준은 충족하지 못했다.**
첫 시험은 최종 제자리 회전을 수행해 Nav2 SUCCEEDED였지만 정지 후 yaw가 .10rad를
벗어났다. 두 번째는 XY 10cm에 들어가기 전 접근 정체로 CANCELED였다.
이 두 결과를 같은 최종 회전 실패로 합산하지 않는다.

## 승인 범위와 실행본

사용자가 새 현장 준비·정지 수단을 확인하고 새 목표 최대 2건, 각 30초 이내 시험을
승인했다. Navigation에서 새 Initial Pose를 입력했고 실제 저장 PCD 정합을 확인했다.
첫 목표는 사용자의 요청으로 화면에서 현재 위치 약 1cm 이내·약 20도 좌회전으로
지정했으며 사용자가 전송했다. 두 번째는 사용자가 직접 지정·전송한 약 .80m 목표다.
두 번 모두 같은 세션·같은 파라미터를 사용했다. 시험을 마친 후 Nav2를 종료했다.

| 항목 | 확인값 |
| --- | --- |
| 시험 코드 / 실제 배포 SHA | `5154761bba6fa4f171881e61f986901e2b415ed9` |
| 실행 release | `robot-scope-5154761bba6f`, source 2,200개 hash 검증 |
| 이전 release | `robot-scope-5c1ffe3ba3c0`, 복구용 보존 |
| Nav2 job | `069bb6aa7daf4b70a8e5aef0d7decc5b` |
| Shim | Nav2 1.1.20 + 공통 유효 TF 시각 + 별도 최종 회전 충돌 sweep 수정 |
| 실제 controller에 로드된 .so SHA256 | `95c6ee9b0294651c182092031eb4926291946eb8e72be5cf1bfb976219f1754d` |
| 보존된 `/opt/ros` 원본 .so SHA256 | `1cd261a56261e20b10e1d3cc6da3ff14423b467bef23238c8dbc84235f6f0965` |
| 파라미터 revision | `71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387` |
| 생성 YAML SHA256 | `69804bc0a5dacf1122fe52e2a1aa313c8c65576525c2262f10eeea6783c50ccc` |

실제 controller의 `/proc/<pid>/maps`에서 overlay 라이브러리 로드를 확인했다.
dirty Jetson 사용자 checkout을 수정하지 않았고 지도·프리셋·브리지 기본 시작 설정을
보존했다. bridge 종료 전환 중 배포 준비 검사가 두 번 차단됐으며 이전 release 복구와
idle 확인 후 재시도했다. 이 검사를 우회하지 않았다.

이번 배포에는 현재 정합 로봇의 공식 Go2 URDF 표시와 전송한 Goal 표시 유지 수정도
포함됐다. 실제 Navigation에서 현재 로봇과 전송 전 목표 모델을 확인해 private
스크린샷을 보존했다. 모델·지도 좌표 변환·Goal 전송 정책을 새로 만들지 않았다.
이 보고서 게시 commit은 시험 실행본과 구분한다. 측정 뒤 controller 코드나 설정을
추가 변경·배포하지 않았다.

## 저장 / 생성 / live 설정과 지도

새 Initial Pose 정합 뒤 live readback은 current, 관련 lifecycle은 active(3), 필수 누락은
없었다. 비활성 plugin 필드의 NOT_APPLICABLE을 필수 누락과 구분했다.

| 항목 | 첫 시험 / 두 번째 시험 |
| --- | --- |
| XY / yaw 허용오차 | .10m / .10rad — 저장·생성·live 일치 |
| controller / primary | RotationShim / RPP |
| 선속도 / 주기 | .25m/s / 10Hz |
| goal checker | SimpleGoalChecker, stateful=true |
| progress checker | SimpleProgressChecker, .20m / 10s |
| Shim rotate_to_goal_heading / RPP use_rotate_to_heading | true / false |
| 회전속도 / 각가속도 / closed_loop | .50rad/s / 1.20rad/s² / false |
| NavFn tolerance / 반경 / inflation | .50m / .22m / .25m |
| RPP approach 거리 / 최소 접근 속도 | live .60m / .05m/s; 생성 YAML에 생략된 upstream 기본값 |

PoseProgressChecker를 선택하지 않았다. 측정 후 yaw .05rad 비교 후보를 Mac private
폴더에서만 생성·검증했으며 장비 프리셋 저장·적용·주행은 하지 않았다.
사용자 프리셋과 복구 프리셋을 보존하고 장비 저장값은 .10m/.10rad로 남겼다.

- 3D: `map_20261027_125427_course_localization_20261028`,
  ID `e1dd40cc6911404dbdfc073b`, revision
  `c7d7ce7e04b2fb80519854cc71465f61af9fff210ac72e299105502497401ad5`.
- 2D: `map_20261027_125427_operator_free_20261028`,
  ID `9a382e3eb990fb02fe1a3569`, revision
  `d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552`.
- 실제 source: `STORED_PCD_FASTLIO`, `MAP_TRACKING`, `ALL_DIRECTION_BASELINE`.
  reference 13,546점, SHA256
  `6ec38aa876ffcfe505ee81204d94fa84e1c3cb438ae706a6a6b7fc0048970b5a`.

## 목표별 결과

private 디렉터리의 trial-three / trial-four는 과거 기록과 겹치지 않기 위한 이름이다.
아래 첫째·둘째는 **오늘의** 두 시험이다. yaw 오차 부호는 실제 pose−요청 goal이다.

| 측정 | 첫째: 가까운 위치에서 약 20도 회전 | 둘째: 사용자 지정 접근 목표 |
| --- | ---: | ---: |
| goal ID | `e9c8144ae30bc9d144e1d354844ca261` | `9818fa865039f59e7b124909c80e51c2` |
| 요청 x / y / yaw(rad) | -.426711 / .185561 / -.059928 | .396119 / -.102309 / .794653 |
| action 결과 | SUCCEEDED | CANCELED |
| feedback 주행시간 / dispatch→결과 수신 | 2.081s / 2.211s | 26.190s / 26.337s |
| recovery | 0 | 3 |
| 결과 수신 부근 XY / yaw | 4.37cm / -.082416rad (−4.72°) | 13.85cm / -1.774442rad (−101.67°) |
| 첫 측정 정지 후 XY / yaw | 7.85cm / -.119902rad (−6.87°) | 14.52cm / -1.683844rad (−96.48°) |
| 결과 수신→첫 정지 확인 | 2.522s | 6.900s |
| 보존된 active pose 최소 XY / 10cm 내부 표본 | .738cm / 7개 중 7개 | 12.93cm / 98개 중 0개 |
| raw 명령 / 순수 회전 표본 | 22 / 21 | 259 / 0 |
| planner endpoint | 3개 모두 요청과 일치 | 26개 모두 요청과 일치 |
| active 구간 TF extrapolation / collision 오류 | 0 / 0 | 0 / 0 |
| native progress abort / missed-rate 경고 | 0 / 0 | 2 / 4 |
| 정밀 도착 완료 판정 | 실패: 정지 후 yaw 초과 | 실패: 취소·XY/yaw 초과 |

결과 수신 부근은 Nav2 내부 success 발생 순간과 동일한 시각이 아니다. source stamp는
결과 수신보다 각각 +8.796ms / +42.253ms이고 수신 당시 pose age는 68.726ms / 51.487ms다.
첫 정지 표본의 source stamp는 결과 수신 +2.408777s / +6.842052s,
age는 113.762ms / 59.492ms다. pose frame은 `map`, 몸체는 `base_link`다.
원시 action success timestamp를 생성하지 않았다. `distance_remaining=0`을 실제 XY/yaw
오차 0으로 해석하지 않았다.

### 첫째: 최종 회전은 동작, 정지 후 방향 잔차는 남음

병진 0·양의 각속도 명령으로 최종 방향을 맞췄고 raw 최대 각속도는 .50rad/s였다.
같은 시각 TF 패치가 적용된 실행에서 최종 회전과 action 성공을 실제 확인했다.
TF·충돌·진행 실패나 recovery는 이 짧은 구간에서 관측되지 않았다.
하지만 성공 부근 −4.72°였던 yaw가 정지 후 −6.87°가 돼 최종 기준 ±5.73°를 벗어났다.
이를 완전 해결 또는 정밀 도착 성공으로 표시하지 않는다.

결과 수신 부근→첫 정지 사이 body odom yaw는 −1.917°,
map→odom yaw 보정은 −.228°였다. 몸체가 추가로 반대 방향으로 변한 추정량이
대부분을 설명하지만, body odom은 외부 ground truth가 아니며 기구·보행 제어기의
물리적 원인을 이 기록만으로 확정하지 않는다. 이후 정지 표본도 약 −7.07°였다.

마지막 관측에서는 기존 2초 body-motion 정지 조건을 충족한 182.50초의 정지 window를
확인했다. 이는 첫 정지 확인 이후 모든 순간에 정지가 연속 유지됐다는 뜻이 아니다.
중간 정지 window가 다시 시작된 구간이 있고 최종 정밀 기준은 계속 미충족이다.

### 둘째: 최종 회전 이전 접근 정체

native progress abort는 dispatch 후 15.423s / 25.644s에 발생했다.
가까운 source 표본의 XY는 각각 17.12cm / 16.82cm이며 시간 차이는 −44ms / −65ms다.
보존한 active 표본에 XY 10cm 내부 진입도, 병진 0인 최종 회전 명령도 없다.
따라서 정상 최종 회전을 translation-only checker가 끊은 사례로 세지 않는다.

10.079→25.479s 사이 body odom XY 순변위는 1.587cm, yaw 변화는 −.753°였다.
후기 bridge accepted 선속도 표본은 .050~.07248m/s였다. 낮은 접근 명령은 실제 bridge까지
전달됐지만 추정 몸체 진행이 작았다. Go2 저속 응답·현장 조건·곡률·정합 보정의 기여는
아직 분리하지 못했다. 최소속도 강제 증가나 .20m/10s 진행 기준 완화를 적용하지 않았다.

private guard는 `REPEATED_PROGRESS_ABORT`로 현재 goal ID를 지정해 Cancel했고 정상 결과를
수신했다. 사용자 수동 취소나 observation loss로 기록하지 않는다. 최종 snapshot의
recovery는 3이다. 두 번째 abort를 감지한 뒤 취소가 반영되는 사이까지 포함한 수치이며,
guard가 recovery를 두 번 이하로 보장했다고 표현하지 않는다.

## 결과 수신 뒤 몸체 이동과 map 보정

같은 source stamp의 SE(3) 표본을 연결했다. XY 평면 이동과 Z 이동을 구분한다.

| 결과 수신 부근→첫 정지 변화 | 첫째 | 둘째 |
| --- | ---: | ---: |
| body odom XY / yaw | 1.215cm / −1.917° | 1.873cm / +5.181° |
| map→odom XY / yaw | 7.887cm / −.228° | 1.187cm / +.006° |
| map→odom Z | −3.751cm | −3.609cm |
| map-body yaw | −2.148° | +5.191° |

첫째의 XY 변화에는 지도 보정의 기여가 크다. 둘째의 방향 변화에는 body odom 변화가
주로 나타난다. transform translation의 XY 크기는 로봇 위치의 XY 이동과 동일한 양이
아니므로 각 열을 단순 합산하지 않는다. ZERO 발행 사실만으로 물리 정지를 판정하지 않는다.

## 별도로 재현한 대시보드 진행률 결함

둘째 goal의 `initial_distance=.042m`는 첫 goal 마지막 raw 거리 `.0416856m`와 대응한다.
둘째 첫 active pose의 실제 목표 XY는 약 .801m였고 이후 raw path 거리는
.838→.681→.581→.531→.515→.490m로 줄었다. 그런데 대시보드 진행률은 계속 0이었다.
3.057초의 첫 nonready 이유는 `GOAL_PROGRESS_TOO_LOW`였다.

`send_goal()`은 progress 상태를 초기화한다. 문제는
`_record_navigation_goal_progress_locked()`가 처음 들어온 **양의** 거리 값을 즉시
best baseline으로 확정하는 데 있다. 작은 첫 값 이후 더 큰 값에서 접근해도 작은
baseline보다 가까워지지 않아 진행으로 세지 않는다. 기존 zero-only 방어로는 막지 못한다.

실제 `NavigationRosGateway`와 기존 health classifier를 오프라인으로 호출해 재현했다.
현장 rounded 거리 순서를 사용하되 시간 간격을 합성한 재현이며 원시 callback 시각의
완전한 replay는 아니다.

| 동일 구현에 입력한 비교 | 3.1초 health | 마지막 진행률 |
| --- | --- | ---: |
| .0416856→.838→…→.490 | DEGRADED / GOAL_PROGRESS_TOO_LOW | 0 |
| 작은 첫 값 없이 .838→…→.490 | READY / HEALTHY | .05556m/s |
| 계속 .838인 실제 정체 대조 | DEGRADED / GOAL_PROGRESS_TOO_LOW | 0 |

[Nav2 1.1.20 navigate_to_pose.cpp](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_bt_navigator/src/navigators/navigate_to_pose.cpp)의
`initializeGoalPose()`는 recovery와 goal을 갱신하지만 path blackboard를 비우지 않으며,
`onLoop()`는 그 path에서 거리를 계산한다. 이전 path가 새 goal 초기에 보고될 수 있는
구조와 관측값이 일치한다. 다만 당시 blackboard 내부 전환 자체를 계측하지는 않았다.

이 대시보드 표시 결함은 native SimpleProgressChecker의 15/25초 abort와 별개다.
실제 bridge 명령 수신이 계속됐으므로 표시 오류가 접근을 중단시켰다고 주장하지 않는다.
새 goal에 속한 plan/feedback을 식별하는 검증 없이 baseline을 반복 재설정하면 실제
정체·진동도 진행으로 보일 수 있어, 이번 측정 후 임의 reset이나 timeout 완화를 넣지 않았다.
이 항목은 **SOFTWARE_REPRODUCED / 수정 미적용**으로 남긴다.

## 계측·검사·증거 한계

개선한 private observer를 이번 장비에서 검증했다. Navigation 2Hz 수집은 보조 1Hz 조회와
파일 쓰기에서 분리됐고 queue64 / record512KiB / file48MiB 상한, 2.5초 observation-loss
검사, 30초 창의 27초 Cancel 예약을 유지했다. 새 명령 publisher는 없다.

- fake HTTP 검사 7개 통과. 장비 idle 읽기 probe 20초·101 GET 중 오류 0,
  Navigation 41회 최대 응답 .333s / 성공 간격 .688s. 첫 목표 대기 중 Navigation 66회도
  오류 0 / 최대 간격 .5002s였다. 두 실험 모두 API observation 오류 0이었다.
- 서비스 private sink에 두 goal의 dispatch / accepted / result / first_measured_stop가
  각각 저장됐다. 마지막 누적 written=124, dropped=0, errors=0, pending=0이다.
- raw 명령 관측 간격 median/p95/max는 첫째 100.007/100.319/101.472ms,
  둘째 99.995/101.974/201.814ms다. 이는 관측 수신 간격이며 controller 함수 실행시간이나
  missed-rate 비율이 아니다. native 경고 0/4건과 구분한다.
- Python 전체 3,132개 실행, 실패 0, skip 3. JavaScript 전체 700개 통과.
  이번 검사에 기존 private 의존성 경로를 사용했다. 양의 첫 feedback 재현의 최초 실행은
  의존성 경로 누락으로 실패했고 해당 경로를 지정한 재실행에서 위 세 대조를 확인했다.
- 배포 SHA `5154761`의 [CI 40838551921](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40838551921)은
  Ubuntu 22.04 / 24.04 및 competition-offline-integration 3개 job 모두 성공이다.
  보고서 후속 commit의 CI와 구분한다. 이전 44개 native 검사는 이번에 재실행하지 않았다.
- Nav2 stop 후 job cleanup으로 원래 생성 YAML·bundle 파일이 삭제돼 이 파일들의 추가
  원본 archive는 확보하지 못했다. API/sink의 generated SHA·값, 선택 지도·live readback은
  보존했다. native ROS 로그 6개는 별도로 회수했다. 없는 job archive를 있다고 기록하지 않는다.

private 원본은 기존 `goal-precision-20261029`의 `heading-trial-three-20261030`,
`heading-trial-four-20261030`에 보존했다. 지도·PCD·원시 로그·환경파일은 공개 Git에서 제외한다.

| private 증거 | SHA256 |
| --- | --- |
| 배포 검증 영수증 | `a3f654aa16b19e551ff543eb11315895751c1025a710744fbbe9080d861f8d03` |
| 실제 라이브러리 로드 영수증 | `b26bf6c7b3cf5041b21639aa4314268f56ad725617d08e66137f94cb4b3f53b7` |
| 첫째 서비스 events | `18a3061f360a6d2f1a9bfa852d7f996329ad1fd18d6d39f9aca0c51481b17f28` |
| 둘째 서비스 events | `f6472f0fbead9ff37b3bceccc84a3d085cd47dab8c46a8df9461fc64da135694` |
| native ROS 로그 archive | `63e5b01c52ed29fa894f82b1efc09447e294d5c185c32bab29c72d7f5f5a45e3` |
| 두 실험 분석 JSON·원본 hash manifest | `aaf337c627c4780eca0679b9e34ac4abbc278384450cde90c39b54793f7b3b87` |
| 양의 첫 feedback 재현 JSON | `1fbc6dfda778dc87b960bcba8940f54840fa6239d2784f9de3b86ce1a336ca62` |
| Nav2 종료 영수증 | `eb8d6d2f48064900df9205678c88220e84d4d25d8888928bb13d423b7d66f081` |

## 남겨진 상태·복구·다음 한 작업

둘째 종료 뒤 fresh pose에서 연속 6.899초의 측정 정지 window를 확인했다.
Nav2 종료 영수증은 pipeline=idle, lease.active=false, 최종 세 축 명령=0이다.
영수증의 `estop=null`은 잘못 선택한 응답 필드로 실제 latch 상태를 보존하지 못한 것이며
SOFTWARE STOP이 해제됐다는 증거로 사용하지 않는다. STOP 잠금을 해제한 작업은 없다.

저장된 .10m/.10rad 정밀 후보와 Shim overlay, 브리지 기본 시작 설정은 유지됐다.
baseline 자동 복구나 goal 재전송은 하지 않았다. 사용자 CSS 두 파일도 보존했다.
복구하려면 idle·제어권 해제를 확인하고 private selector 백업으로 이전 release/overlay를
선택한다. `/opt/ros` 원본은 보존됐다. `정밀시험 전 복구 20261029` 프리셋은 최신 revision의
CAS로 적용한 뒤 새 generated/live readback을 확인해야 한다. 사용자 `홍재` 프리셋을
과거 값으로 덮어쓰지 않는다.

다음 한 작업은 **최종 회전의 정지 후 방향 잔차를 줄일 단일 후보를 분리 검증**하는 것이다.
현재 첫 시험은 성공 문턱 안에서 ZERO가 된 뒤 약 2도 반대 방향으로 변했다.
기존 속도·주기·controller·progress·XY 기준은 고정하고 별도 yaw .05rad 후보로 정지 여유를
확보하는 비교를 오프라인으로 준비했다. 실제 저장값을 validator와 기존 YAML 생성기에
넣었고 기존 .10rad의 재생성 SHA는 위 실제 job SHA와 일치했다. 후보의 유일한 YAML
차이는 `controller_server.ros__parameters.goal_checker.yaw_goal_tolerance`다.
후보 revision은 `a6ae0abe0e0d98f59e9120c04b66cb28378e8860e94b330f096bd0761041c8a4`,
YAML SHA256은 `6d5f0482fe5611a6842eedebc73e24fed5f563492faa2e825c3ac1a0415d5b34`다.
장비 적용·live readback·현장 비교는 NOT_RUN이다. 이는 아직 적용하지 않은 가설이며,
외부 완료 기준은 .10m/.10rad와 기존 2초 측정 정지로 유지한다. 이번 두 목표 창은 사용했으므로
새 실제 이동은 새 범위 확인 후 진행한다. 접근 정체와 초기 feedback 결함을 이 후보가
해결한다고 주장하지 않는다.
