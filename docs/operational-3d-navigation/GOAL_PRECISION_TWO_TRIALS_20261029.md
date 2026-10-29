# Goal Pose 방향 정렬 — 두 차례 실제 주행 보고서

2026-10-29 KST. **정밀 도착 미통과. 두 목표 모두 CANCELED이며 SUCCEEDED가 아니다.**
사용자가 관찰한 “위치는 얼추 따라가는데 방향 정렬에서 문제가 있다”는 현상이
두 번째 시험에서 수치로 재현됐다. 취소 결과 수신 부근 XY 오차는 3.18cm지만
yaw 오차는 -43.70°였다. 기존 2D/3D 지도 기반 이동 검증을 취소하거나 재개발하는 결과가 아니다.

이 보고서는 [기존 27° 잔차 기록](GOAL_FINAL_POSE_MISMATCH_20261028.md) 및
[정밀 후보·계측 구현 기록](GOAL_PRECISION_FOLLOWUP.md)의 후속이다.
과거 SUCCEEDED 사례의 원인을 이번 CANCELED 사례로 소급 확정하지 않는다.

## 실행본과 지도

- 두 시험의 코드 및 실제 배포 SHA: `b15099cd8c40326b810e6c39a136f94944443cb9`.
  배포 시 아카이브와 실행 릴리스의 소스 2,167개 hash를 확인했다.
- 실제 릴리스: `/home/unitree/robot-scope-releases/robot-scope-b15099cd8c40`.
  설치 Nav2 관련 패키지 버전: 1.1.20. 기존 RotationShim/RPP를 사용했다.
- 해당 SHA의 [CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40808485416):
  completed / success. 이 보고서의 커밋은 별개이며 실행 코드를 재배포하지 않는다.
- 공통 Nav2 job: `5860751d7f654f57aa49ffdf027b6359`.
  bundle generation: `8da6dadd4c1e4cc4bc3ea7ba69a88f37`.
- 3D: `map_20261027_125427_course_localization_20261028`,
  ID `e1dd40cc6911404dbdfc073b`, revision
  `c7d7ce7e04b2fb80519854cc71465f61af9fff210ac72e299105502497401ad5`.
  PCD SHA256 `6ec38aa876ffcfe505ee81204d94fa84e1c3cb438ae706a6a6b7fc0048970b5a`.
- 2D: `map_20261027_125427_operator_free_20261028`,
  ID `9a382e3eb990fb02fe1a3569`, revision
  `d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552`.
  3D/2D 좌표 관계는 identity. 255×210, 0.05m, origin
  `[-5.78482151031, -5.90532827377, 0]`.
  free 영역은 운영자 지정 공간이며 모든 셀의 센서 검증을 의미하지 않는다.
- 실제 위치 source: `STORED_PCD_FASTLIO`, 같은 source stamp의
  `/cloud_registered` + `/Odometry` → 저장 PCD 정합 → `map→odom→base_link`.
  controller odometry: `/robot_scope/nav/controller_odom_fastlio`.
  `ALL_DIRECTION_BASELINE` 유지. 후방 가중치나 장애물 입력 제외를 추가하지 않았다.

## 실제 적용 파라미터

저장 설정, job 생성 YAML, 실행 중 선언된 파라미터를 각각 확인했다.
실행 readback은 같은 job의 `/controller_server`, `/planner_server`에서
ListParameters → GetParameters를 읽기 전용으로 수행했고 노드별 고유 발행자를 확인했다.

| 항목 | 시험 전 저장 baseline | 두 시험의 saved / generated / live |
| --- | --- | --- |
| XY tolerance | 0.35m | 0.10m / 0.10m / 0.10m |
| yaw tolerance | 0.45rad | 0.10rad / 0.10rad / 0.10rad |
| 선속도 / 제어주기 | 0.25m/s / 10Hz | 동일 |
| controller | RotationShim + RPP | 동일 |
| goal checker | SimpleGoalChecker, stateful=true | 동일 |
| rotate_to_goal_heading / use_rotate_to_heading | true / false | 동일 |
| closed_loop | false | 동일 |
| 회전속도 / 각가속도 | 0.5rad/s / 1.2rad/s² | 동일 |
| progress radius / time allowance | 0.2m / 10s | 동일 |
| NavFn tolerance / use_astar / allow_unknown | 0.5m / true / true | 동일 |
| robot_radius / inflation_radius | 0.22m / 0.25m | 저장값·생성 YAML 유지; 전체 costmap live batch는 아래 제약 참조 |

실행 기본값도 별도로 관측했다: RPP `approach_velocity_scaling_dist=0.6`,
`min_approach_linear_velocity=0.05`, NavFn `use_final_approach_orientation=false`.
생성 YAML에 없는 기본값을 YAML에서 확인한 것처럼 표시하지 않는다.

baseline revision:
`194c9c18648f9201df464802884022184095422d1b0b91e6d9a75917c9519d77`.
candidate revision:
`71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387`.
전체 저장값 비교에서 차이는 XY/yaw 두 값뿐이다. 두 시험 사이 설정 변경은 없었다.
job YAML SHA256:
`69804bc0a5dacf1122fe52e2a1aa313c8c65576525c2262f10eeea6783c50ccc`.

## 두 실행의 결과

목표는 사용자가 Navigation에서 새로 전송했다. 에이전트는 목표를 재전송하지 않았다.
각도는 `wrap(actual_yaw - requested_yaw)`이며 위치·방향 기준은 `map`의 `base_link`다.

| 항목 | 시험 1 | 시험 2: 짧은 목표 |
| --- | --- | --- |
| 시작(KST, 전송 stamp) | 12:34:47.085 | 12:43:06.742 |
| goal ID | `827259fb30ab17ccced2ee4bcba079ab` | `af5703640d68c78b8363e0b7647f35ff` |
| 요청 X / Y / yaw | 0.905567 / 0.873017 / 1.204162 | 0.481921 / -0.222297 / 1.178633 |
| 초기 경로 거리(feedback) | 1.845m | 1.045m |
| 주행 시간(feedback) / recoveries | 110.34s / 20 | 72.24s / 7 |
| Nav2 결과 | CANCELED | CANCELED |
| 결과 수신 부근 XY / yaw 오차 | 0.294045m / +2.455783rad (+140.71°) | 0.031793m / -0.762743rad (-43.70°) |
| 첫 실측 정지 후 XY / yaw 오차 | 0.288405m / +2.468470rad (+141.43°) | 0.046048m / -0.785372rad (-45.00°) |
| 실제 정지 판정 | 2초 이상 측정 조건 충족 | 2초 이상 측정 조건 충족 |
| 정밀 도착 성공 | 미통과 | 미통과 |

시험 1의 큰 최종 방향 오차에는 중간 recovery spin이 포함된다. 원래의 27° 미회전과
같은 수치로 해석하지 않는다. 시험 2는 10cm 안에서도 방향 정렬이 끝나지 않는 문제를 분리한다.

결과 수신 부근 표본은 시험 1에서 수신 -20.251ms, 시험 2에서 +18.200ms다.
source stamp는 각각 `1793244997582219362`, `1793245459166617393`ns이며
수신 시 source age는 66.54ms / 56.59ms다. 성공 순간 표본은 **없다**.
첫 정지 표본 stamp는 `1793245006383067131`, `1793245481566592216`ns,
수신 시 age는 57.56ms / 52.85ms다.

정지 판정은 신선한 동일 시각 map/body·odom/body 쌍에서 2초 이상
0.03m/s·0.05rad/s 이하를 요구한다. 이 연속 조건을 처음 만족하는 표본이
취소 수신 약 8.78s / 22.42s 뒤에 잡혔다. 이것을 그 시간 내내 실제로 이동했다는 뜻으로
해석하지 않는다. 명령 ZERO, 측정 정지, 외부 독립 계측은 서로 다르다.
ZERO 발행 기록과 실제 정지는 확인했지만 해당 발행에 대응하는 bridge ACK는 미관측이다.

동일 시각 SE(3) 쌍의 결과 수신 부근 → 첫 정지 표본 변화:

| 구분 | 시험 1 | 시험 2 |
| --- | ---: | ---: |
| odom 안의 본체 3D 병진 / 회전 | 0.01198m / 0.00978rad | 0.01535m / 0.01187rad |
| map→odom 3D 보정 변화 / 회전 | 0.01235m / 0.00571rad | 0.02673m / 0.01410rad |

두 벡터의 크기를 단순 합산해 최종 XY 오차라고 하지 않는다. 이 작은 사후 변화만으로
시험 2의 43.7° 미정렬을 설명할 수 없다. source generation 변경도 관측되지 않았다.

## 확인된 원인과 실행 순서

### 1. 목표 전달 오류는 관측되지 않음; 첫 시험의 경로 끝점은 실제로 변경됨

두 목표 모두 요청 → NavigateToPose 전송 오차는 XY 0, yaw 약 2.2e-16rad였다.
시험 1 초기 `/plan` 끝점은 요청과 일치했지만 이후 0.36056m, 0.20616m 등
이동한 끝점이 관측됐고 마지막에는 요청에서 0.32016m 떨어진
`(1.155567, 0.673017, 1.204162)`였다. NavFn의 실제 tolerance는 0.5m다.
이것은 controller 도착 tolerance 0.1m와 별개인 대체 끝점 선택이다.
어떤 장애물 셀이 최초 대체 선택을 유발했는지는 첫 시험의 costmap 연속 기록이 없어 미확정이다.

시험 2는 보존된 `/plan` 47개와 API 표본에서 경로 끝점이 요청과 일치했다.
따라서 두 번째 방향 실패를 goal 전달·대체 경로 끝점만으로 설명할 수 없다.
`/plan`에는 action UUID가 없으므로 이 연관은 단일 활성 goal의 시간상 관측이다.

### 2. 최종 회전 경로에서 TF 시각 불일치가 반복됨

| 활성 goal 구간의 원본 controller 로그 | 시험 1 | 시험 2 |
| --- | ---: | ---: |
| RotationShim `Failed to transform pose to base frame!` | 54 | 68 |
| TF future extrapolation | 55 | 68 |
| RotationShim collision ahead | 18 | 0 |
| RPP collision ahead | 13 | 0 |
| Nav2 `Failed to make progress` | 0 | 4 |
| 10Hz 제어주기 미준수 경고 | 131 | 305 |

설치 버전과 같은 공식 RotationShim 1.1.20 소스에서 `getSampledPathGoal()`은
목표의 stamp를 `clock_->now()`로 만든 뒤 현재 pose의 frame으로 변환한다.
반면 운영 3D TF는 측정 source stamp를 보존한다. 실제 로그는 그 요청 시각보다
버퍼의 최신 map/odom TF가 뒤에 있어 변환에 실패했음을 보여준다.
요청 시각과 실패 당시 최신 TF의 차이는 시험 1 0.10–51.42ms(중앙 23.12ms),
시험 2 7.21–54.61ms(중앙 38.78ms)다. 이 값은 전체 센서 지연이나 네트워크 지연이 아니다.

RotationShim은 이 예외를 잡고 primary controller로 넘어갈 수 있다.
이 실행의 RPP `use_rotate_to_heading=false`이므로 최종 yaw 정렬을 계속 보장하지 못한다.
방향 정렬 명령과 접근 명령이 섞이는 실제 표본도 보존했다.
**최종 회전 요청과 실제 TF 공급의 시간 계약 불일치는 확인된 결함 경로**다.
다만 센서 처리·TF 발행·callback 대기 각각의 지연 기여율은 현재 로그만으로 분리할 수 없다.
기존 RPP `transform_tolerance=0.3`을 RotationShim의 해당 조회에도 그대로 적용된 값으로
가정하거나, stale 허용을 늘리는 해결책으로 삼지 않는다.

### 3. 짧은 시험에서 Nav2 병진 진행 검사가 실제로 회전을 중단시킴

실행된 `SimpleProgressChecker`는 10초 동안 기준점에서 0.2m를 넘는 **병진 이동**을
요구한다. 회전 자체는 기준점을 갱신하지 않는다. 시험 2에서 실제 abort는 다음과 같다.
시각은 전송 기준이며 오차는 가장 가까운 API 표본으로, 오류와 완전 동기화된 측정은 아니다.

| 경과 | 로그 | 가까운 XY / yaw 표본 |
| --- | --- | --- |
| 15.69s | Failed to make progress → FollowPath abort | 0.220m / -1.924rad |
| 25.77s | 동일 | 0.126m / -1.990rad |
| 46.17s | 동일 | 0.071m / -1.394rad |
| 56.37s | 동일 | 0.045m / -0.820rad |

마지막 두 구간은 XY 10cm 안에서도 방향 오차가 남은 상태였다. 50.10s → 54.52s의
yaw 오차가 약 -1.438 → -0.813rad로 줄어도 병진 검사에서는 진행으로 인정하지 않는다.
즉, 최종 회전/지연과 기존 병진 진행 검사 사이의 충돌이 실제 기록에 있다.
Robot Scope의 별도 `GOAL_PROGRESS_TOO_LOW` 분류가 그 자체로 중단 명령을 냈다고
주장하지 않는다. 이 abort는 Nav2 controller 원본 로그로 확인했다.

### 4. 충돌은 첫 시험의 추가 원인; 두 번째 실패의 공통 원인은 아님

시험 1 최초 회전 충돌 예측은 시작 약 14.24초 뒤다. RPP 충돌 abort와 costmap clear,
spin/wait/backup recovery가 이어졌다. 어떤 실제 물체·발·바닥 점이 해당 셀을 만들었는지는
미확정이다. 이를 false positive로 단정하거나 장애물 검사를 끄지 않는다.

시험 2에서는 위 두 controller의 충돌 오류가 없었다. 활성 구간에서 보존한 global
costmap 59표본의 요청 goal 셀 값은 모두 0이었고 local 66표본의 본체 중심 셀도 0이었다.
이 표본은 연속 swept footprint 충돌 검증이나 실제 공간 안전 인증은 아니다.
그럼에도 충돌 오류 없는 짧은 실행에서 방향 실패가 재현돼 시간 계약·진행 검사를
먼저 다룰 근거가 생겼다.

## 관측 한계와 별도 계측 결함

- 첫 시험의 초기 구간에는 API 연속 표본이 없다. 원본 ROS 로그, 초기/결과 snapshot,
  후반 polling을 결합했다. 두 번째 시험은 API 186행(해당 goal 139행),
  raw command 364개, scan 179개, local/global costmap 159/145개, plan 47개를 보존했다.
  이 수치는 준비·정지 구간을 포함하며 모든 ROS 메시지를 lossless 기록한 bag은 아니다.
- Dashboard 전체 live parameter batch는 선언되지 않은 선택 costmap 필드
  `keepout_filter.plugin`, `static_layer.plugin` 때문에 `POLICY_PARTIAL_READBACK`이었다.
  선언된 controller/planner만 별도 읽어 실제 값은 확보했다. 정책 admission을 완화하지 않았다.
- 추가한 metrology `LOGGER.info`는 기본 로그 설정에서 journal에 남지 않았다.
  “브라우저 없이 journal 보존 완료”라는 이전 구현 의도와 실제 배포 동작이 달랐다.
  따라서 이번 보고서는 존재하지 않는 journal trace를 증거로 사용하지 않는다.
  선택 파라미터 읽기와 명시적인 계측 로그 설정은 다음 코드 수정에 포함해야 한다.
- 독립 외부 위치·방향 계측은 없다. 수치는 저장 지도 위치추정 기준이며 사용자의 현장
  관찰과 구분한다. 정상적인 회전 자체의 물리적 응답 지연은 추가 분석 가능성이 남는다.

## 종료·복구 상태와 다음 한 작업

두 번째 실행의 반복 recovery를 확인하고 기존 Cancel을 요청했다.
첫 호출은 필수 goal_id 누락으로 HTTP 422였으며 주행을 취소하지 못했다.
현재 goal_id를 명시한 후속 호출로 CANCELED와 ZERO, 실제 측정 정지를 확인했다.
그 뒤 기존 Nav2 stop으로 **pipeline idle, active lease=false, command zero**를 확인했다.
사용자는 로봇을 종료했다. 새 SOFTWARE STOP 잠금이나 잠금 해제는 수행하지 않았다.

복구 프리셋 `정밀시험 전 복구 20261029` 및 candidate
`Go2 정밀 도착 10cm 20261029`, 기존 `홍재` 프리셋을 보존했다.
**baseline 복원을 요청하기 전 장비가 꺼져 SSH 연결이 실패했다. 복원 완료가 아니다.**
마지막 확인된 저장 설정은 0.10m / 0.10rad 후보다. 다음 전원 인가 후 주행 전에 idle에서
최신 revision을 읽고 복구 프리셋을 CAS 저장해 baseline revision과 대조한다.
그 후 필요한 새 세션에서 generated/live readback을 다시 구분한다. 과거 goal은 재사용하지 않는다.

다음 한 작업은 **기존 RotationShim의 최종 방향 조회를 실제 controller pose/TF 시각과
맞추는 최소 수정 및 기록 재현 검사**다. 원본 source stamp를 현재 시각으로 덮어쓰거나
TF·충돌·진행 검사를 일괄 완화하지 않는다. 이 경로가 안정된 뒤에도 정상 yaw 진행을
10초 병진 검사로 중단하는 문제가 남는지 분리한다. 새 controller/미션 FSM,
성공 후 cmd_vel 보정, 자동 goal 반복은 도입하지 않는다.
현재 장비 없이 가능한 분석은 계속할 수 있지만 수정 후 실제 yaw 정렬 성공은 아직 검증되지 않았다.

## 증거 보존과 공개 범위

원본은 Jetson private backup `goal-precision-20261029`와 작업 PC private
`robot-scope-integration-private-20261027/goal-precision-20261029`에 보존했다.
공개 저장소에는 보고서만 올린다. 원시 지도·PCD·환경파일·로봇 로그는 커밋하지 않는다.

| private 상대 파일 | SHA256 |
| --- | --- |
| `reboot-effective-parameters.json` | `2dd8b183cf37586fbc2d01b1f7e127845317f3d982aa62a0ab3018fffbff4680` |
| `diagnosis-current-navigation.json` | `2d5b51ad6315956aca843abd8ce477d28f9903f9ee21b8f5baa7b818f8a2d991` |
| `trial-one-native-logs/ros/controller_server_5590_1793244793116.log` | `a4302f276b1aa8c93b03b20d983e278ac7b9da7045968e7a6c2b7a5878a30761` |
| `trial-two/after-cancel-navigation.json` | `e28a2e80ba52b45d8d6a2fa6fcf44b0bf06c6d8fe1c68d78a8790e06a0e6888d` |
| `trial-two/api.jsonl` | `c0a8b714ededb85a6bba52149d5cf7df1d3fb4e61d203db69ba8aa3b7bd9f09c` |
| `trial-two/ros.jsonl` | `a91a971347d557caf17b33e54e2316c6a6e10e3506778822c6f4ce132cd31a1b` |
| `trial-two/native-logs/controller_server_5590_1793244793116.log` | `d3eb5adff402fee74f12375672f979cb7bf85f6b7021a000072f6a6d490d0dba` |
| `trial-two/session-stopped.json` | `3f9c1f5a7b54b6d8f41c9644a9a82c2e1172fc8b6bea6609f35e33ac34fc1bdf` |

관련 코드·공식 설치 버전 소스:
[운영 TF source stamp](../../robot_dashboard/navigation_runtime.py),
[RotationShim 1.1.20](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_rotation_shim_controller/src/nav2_rotation_shim_controller.cpp),
[SimpleProgressChecker 1.1.20](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_controller/plugins/simple_progress_checker.cpp).

보고서 게시 전 저장소 회귀: Python 3,116개 실행 통과(3개 skip), JavaScript 694개 통과.
이번 게시 변경은 보고서와 기존 인계 문서의 최신 상태 연결뿐이다.
실행 코드·파라미터·지도·사용자 CSS 두 파일은 게시 변경에 포함하지 않는다.
