# Goal Pose와 최종 정지 위치 불일치 — OPEN

2026-10-28 KST. 실제 3D 지도 기반 Nav2 이동은 확인됐으나, 사용자가 지정한
Goal Pose와 최종 위치·방향의 정밀 일치는 확인되지 않았다. 이 항목은 별도 후속
해결 대상으로 남긴다. 사용자의 기록 후 종료 요청에 따라 이번에는 튜닝·재주행하지 않았다.

사용자 확인:

> 이동했으며 현재 지도에 찍힌 위치가 실제 위치와 동일함.

> 근데 가긴 했는데 마지막에 찍힌 위치처럼 goal pose와 완전히 일치되지는 않았으니 해당 기록 남겨서 따로 문제해결할수 있도록 해줘

## 재현 기준과 관측

- 코드/실제 배포: `e680aa34bbaccff22d4206e391fdb9e879f6d048`.
- Nav2 job: `afb62e67de15442c88dbcfd22c0a4f8c`.
- 사용자 입력 goal: `3845be684fa7ee75bd6a8d0b4a3e9b1c`.
- 기존 `go2-onboard`, RotationShim/RPP, 0.25m/s, 10Hz 유지.
- 기존 위치 허용오차 0.35m, 방향 허용오차 0.45rad(약 25.8도).
- 도착 후 표본 시각: 20:58:43.233 KST. 기준은 `map`의 본체 `base_link`다.

| 값 | 사용자 Goal Pose | 도착 후 위치추정 readback |
| --- | ---: | ---: |
| X (m) | 0.433322 | 0.182285 |
| Y (m) | -0.175039 | 0.005004 |
| yaw (rad) | 1.073490 | 0.601166 |

평면 거리 차이는 **0.308926m**, 방향 차이는 **-0.472324rad(-27.06도)**다.
5개 도착 후 표본 중 첫 표본도 약 0.312m/-26.96도였다. 이 값은 action 성공 순간과
동기화한 pose나 외부 실측 절대오차가 아니다. 지도 표시 위치의 실제 일치는 사용자의
현장 확인이며, 앞발 접촉점 또는 독립 계측에 의한 정밀 도착 판정을 의미하지 않는다.

Nav2 결과는 `SUCCEEDED`, 초기 거리 1.022m, navigation time 15.461초,
recovery 1회였다. `distance_remaining=0`은 종료 상태의 값이며 좌표 오차 0의 증거가
아니다. 기존 35cm 위치 허용오차 안에서 성공할 수 있지만, 방향은 도착 후 표본에서
0.45rad보다 약간 크다. 따라서 허용오차만으로 전체 원인을 확정하지 않는다.

`first_nonready_health`에는 남은 거리 약 0.31m에서 `GOAL_PROGRESS_TOO_LOW`가
남았다. 해당 표본의 source/frame error는 없고 odometry는 약 10Hz, jump는 0회였다.
종료 후 source는 `STORED_PCD_FASTLIO / MAP_TRACKING`, RMSE 0.052058m,
overlap 1.0, correction sequence 458, correction age 0.445초였다. 정합 RMSE를
goal 오차 또는 독립 위치 정확도로 해석하지 않는다.

도착 후 명령과 bridge accepted command는 0, 마지막 sport API는 StopMove(1003),
motion run은 inactive, 측정된 정지 지속 시간은 14.345초였다. bridge process 누적
nonzero Move는 299회, 최대 선속도 0.25m/s, 각속도 0.5rad/s다. 첫 주행 전체의
연속 기록은 없으며, 후속 recorder는 도착 뒤 시작했으므로 전체 궤적으로 취급하지 않는다.

## 지도·source 고정

3D `map_20261027_125427_course_localization_20261028`:

- ID `e1dd40cc6911404dbdfc073b`
- revision `c7d7ce7e04b2fb80519854cc71465f61af9fff210ac72e299105502497401ad5`
- PCD SHA-256 `6ec38aa876ffcfe505ee81204d94fa84e1c3cb438ae706a6a6b7fc0048970b5a`
- 원본 22,529점 보존, 사용자 코스 제외 사본 13,546점. query에도 같은 제외 적용.

2D `map_20261027_125427_operator_free_20261028`:

- ID `9a382e3eb990fb02fe1a3569`
- revision `d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552`
- 255×210, 0.05m, origin `[-5.78482151031,-5.90532827377,0]`, 좌표 변환 identity.
- 장애물 3,625셀 보존, unknown 49,411셀을 사용자 요청으로 free 지정.
  센서로 관측한 빈 공간이라는 의미는 아니다. 실시간 `/scan`과 costmap 유지.

실제 `/cloud_registered` + 같은 stamp의 `/Odometry`를 저장 PCD에 정합한
보정이 운영 `map→odom→base_link`, `/amcl_pose`와 기존 controller odometry
`/robot_scope/nav/controller_odom_fastlio`로 연결됐다. `ALL_DIRECTION_BASELINE`
유지, 후방 가중치 채택 없음. 기존 signed bridge와 명령 경로를 사용했다.

## 다음 해결 작업

1. 현재 장비·지도 revision을 확인하고 원래 goal checker의 실제 effective 설정,
   stateful 동작 및 RotationShim의 최종 방향 처리부터 읽는다.
2. 같은 사용자 지정 단거리 목표에서 action 결과 시각, goal feedback 원본,
   TF/body pose, controller 명령·bridge ACK, 정합 보정, progress recovery를
   하나의 시간축에 수집한다. 성공 직전과 실제 정지 직후의 오차를 별도로 계산한다.
3. 35cm 허용오차에 따른 조기 성공, 최종 회전·정지 잔류, 성공 이후 정합 보정,
   progress recovery의 영향을 분리한다. 현재 자료로 원인을 단정하지 않는다.
4. 필요한 도착 허용오차를 정한 뒤 기존 controller에서 필요한 항목만 조정한다.
   단순히 성공 표기를 바꾸거나 전체 기존 주행을 다시 개발하지 않는다.
5. 현장 재시험에서 위치·방향·정지를 함께 충족한 뒤에만 이 항목을 닫는다.

## 보존 증거와 종료 상태

Jetson private root: `/home/unitree/robot-scope-backups/operational-3d-20261028`.
로컬 private root: `/Users/hajoonpark/자율설계/robot-scope-integration-private-20261027/operational-3d-20261028`.
원본 도착·정지 JSON은 두 위치에 보존했다. 계산 요약·hash와 최종 브리지 readback을
추가한 종료 기록은 로컬 사본을 기준으로 한다.

- `first-user-goal-arrival-and-stop.json`: 도착 후 5개 source/Nav2/control 표본.
- `first-user-goal-arrival-body-poses.json`: 종료 전 실제 본체 pose 표본.
- `first-user-goal-verified-stop.json`: 기존 Nav2 stop 응답.
- `goal-final-pose-mismatch-summary.json`: 좌표 차이 계산과 사용자 확인.
- `goal-final-pose-evidence-sha256.json`: 위 증거와 종료 기록의 파일 hash.
- `final-session-closeout.json`: Nav2 idle, active mission/lease/motion 없음,
  command zero, 시험 guard/recorder 프로세스 없음.

10분 시험 guard는 `TRIAL_DEADLINE`으로 기존 STOP·Nav2 종료·bridge 종료를
요청한 뒤 종료했다. SOFTWARE STOP은 잠긴 채 유지한다. 다음 시작 때 현장과
중립을 확인한 후 기존 해제·bridge 시작·Nav2 초기화 절차를 사용한다. 이전 pose를
현재 위치로 자동 재사용하지 않는다. Dashboard는 계속 실행된다.

**시험용 녹색 버튼의 실제 stop-and-go와 경사로 위치추정은 NOT_RUN**이다.
OPERATOR_TEST의 소프트웨어 검증과 실제 현장 검증을 구분한다. YOLO GREEN을
위조하지 않았으며 경사로 baseline 전 후방·측면 가중치 개선을 주장하지 않는다.

## 2026-10-29 후속

사용자는 “처음부터 덜 돌아간게 맞아”라고 현장 관찰을 추가했다. 성공 순간과 동기화한
수치 측정으로 해석하지 않는다. [정밀 도착 후속 진단·구현](GOAL_PRECISION_FOLLOWUP.md)에서
원본 결과를 보존한 채 두 tolerance만 바꾸는 후보와 시각별 오차 기록을 진행한다.
