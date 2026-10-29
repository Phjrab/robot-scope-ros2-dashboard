# Goal Pose 정밀 도착 후속 — 현장 비교 대기

2026-10-29 KST. [원본 현장 기록](GOAL_FINAL_POSE_MISMATCH_20261028.md)은 보존한다.
사용자는 이번 대화에서 **“처음부터 덜 돌아간게 맞아”**라고 확인했다. 이는 최종 방향까지
덜 회전한 채 멈춘 현장 관찰이다. 성공 순간의 동기화 측정으로 확대하지 않는다.
기존 Nav2 이동과 저장 3D 지도상의 현재 위치 일치는 이미 사용자가 확인했다.

## 확인된 내용과 남은 원인

- 저장값과 기존 생성 YAML은 XY 0.35m/yaw 0.45rad, RotationShim/RPP,
  0.25m/s, 10Hz다. Jetson의 Nav2 관련 설치 패키지는 1.1.20이다.
  시작 시 Nav2가 idle이므로 **실행 ROS 파라미터는 아직 미관측**이다.
- 공식 Nav2 1.1.20의 RotationShim `computeVelocityCommands`는 goal checker의
  XY tolerance를 가져와 범위 안에서 `rotate_to_goal_heading`으로 전환한다.
  따라서 **35cm 안에서 위치 접근을 끝내고 방향 정렬로 전환할 수 있음**은 확인됐다.
  원본의 도착 후 0.309m 차이는 이 범위 안이다. 당시 실제 전환 순간은 기록이 없다.
- `SimpleGoalChecker::isGoalReached`, `stateful=true`는 XY를 한 번 만족하면
  `check_xy_=false`로 두고 재설정까지 yaw만 검사한다. 마지막 회전 중 XY 재검사 없음.
  yaw 조건은 절대 차이 <0.45rad(25.78°)다. 넓은 방향 허용범위는 현장 관찰과
  부합하지만, 도착 후 27.06°는 이보다 약1.28° 크므로 그것만으로 완전히 설명하지 않는다.
- controller는 planner 경로 마지막 pose를 최종 목표로 사용한다. NavFn tolerance 0.5m는
  정확한 목표점이 도달 불가능할 때 주변 끝점을 찾는 범위다. 정확한 점을 먼저 시도한다.
  과거 경로 끝점 기록이 없어 대체 목표 선택 여부는 **미확인**이다. 허용오차를 합산하지 않는다.
- Nav2 `SimpleProgressChecker`는 병진 이동(.2m/10초)으로 진행을 판정한다.
  제자리 최종 회전은 그 기준을 갱신하지 못한다. 이전 recovery1의 구체 원인은 미확인이다.
- Robot Scope `GOAL_PROGRESS_TOO_LOW`는 거리 감소가 적은 경우의 별도 진단이다.
  readiness/후속 goal admission에 사용되지만, 활성 속도 전달의
  `_navigation_sensor_interlock_reason`은 센서·runtime freshness/ready를 검사한다.
  해당 분류 하나가 주행을 정지시켰다고 단정할 근거는 없다. 진행 검사 변경 없음.
- `closed_loop=false`는 RotationShim의 가속도 제한에 직전 명령 각속도를 쓰는 의미다.
  pose feedback이 없다는 의미가 아니다. RPP의 접근 감속과 최소 접근 속도는 별도이며,
  regulated minimum speed를 모든 상황의 최저 속도로 해석하지 않는다.
- 성공 뒤 몸체 이동, map→odom 보정 변화, 성공 시각과 표본 시각 차이는 과거 자료만으로
  분리할 수 없다. 사용자 관찰상 처음부터 덜 회전했지만 수치 원인은 새 기록으로 확인해야 한다.

공식 소스: [RotationShim](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_rotation_shim_controller/src/nav2_rotation_shim_controller.cpp),
[goal checker](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_controller/plugins/simple_goal_checker.cpp),
[progress checker](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_controller/plugins/simple_progress_checker.cpp),
[controller server](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_controller/src/controller_server.cpp),
[NavFn](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_navfn_planner/src/navfn_planner.cpp).
설치 패키지 버전과 같은 공식 태그를 대조했으며 배포 바이너리의 자체 재빌드를 주장하지 않는다.

## 최소 수정

`go2-safe`와 사용자 프리셋을 보존한다. `go2-precision-10cm` 후보는 **현재 저장값**을
복제하고 XY/yaw 두 필드만 0.10으로 바꾼다. 프리셋 저장은 적용과 별개이며 기존 CAS와
idle 상태 제한을 거친다. stateful, controller, 속도, 주기, costmap, watchdog 변경 없음.

| 항목 | 기존 저장값 / 기존 생성 YAML | 첫 비교 후보 |
|---|---:|---:|
| XY tolerance | 0.35m | 0.10m |
| yaw tolerance | 0.45rad | 0.10rad |
| 선속도 / 제어주기 | 0.25m/s / 10Hz | 유지 |
| 회전속도 / 각가속도 | 0.5rad/s / 1.2rad/s² | 유지 |
| RotationShim / RPP / stateful | 유지 / 유지 / true | 유지 |
| progress radius / time | 0.2m / 10초 | 유지 |

목표 상세에서 Nav2 결과, 현재 실제 XY/yaw 차이, 결과 수신 부근 표본, 2초 실측 정지 후
첫 표본, source timestamp/frame/age를 별도로 표시한다. `distance_remaining=0` API는
보존하고 화면은 남은 **경로** 거리로 표시한다. 목표 좌표로 pose를 덮어쓰지 않는다.
요청/전송 pose, action UUID(확보 시), job/map/parameter revision도 남긴다.
`/plan`은 action UUID를 포함하지 않으므로 끝점의 시간상 관측과 정확한 goal 연관을 구분한다.

Nav2 action 결과에는 원시 성공 timestamp가 없으므로 **결과 수신 시각**과 가장 가까운
신선한 표본(±0.5초), 그 시간차를 기록한다. 정확한 성공 순간이라고 표시하지 않는다.
정지는 명령 ZERO와 별개로 동일 source timestamp의 map/body + odom/body, 신선한
연속 odom에서 2초 이상 0.03m/s·0.05rad/s 이하를 관측한 경우만 표시한다.
source generation 변경·stale·frame 불일치는 현재 정지/정밀 충족을 인정하지 않는다.
본체 이동과 map 보정 차이는 exact-stamp SE3 쌍이 있을 때만 분리한다.
bridge ACK는 별도 현장 수집 전까지 미관측으로 남긴다.

읽기 전용 기록기는 기존 callback과 결과/STOP 경로에 연결한다. 기록 실패는 별도로
격리해 기존 제어/STOP을 방해하지 않는다. browser polling 없이 journal에 dispatch/result,
첫 실측 정지와 제한된 표본(최대2Hz,600개,종료 후15초)을 보존한다. 새 cmd_vel 발행,
성공 후 보정 이동, 자동 goal 반복 없음. 테스트의 합성 정지는 실장비 검증과 구분한다.

## 배포·검증 상태

작업 시작 main `a95ddac6ba3c7f7ccc6f091be374d0623dbb6620`, 실제 실행 릴리스
`e680aa34bbaccff22d4206e391fdb9e879f6d048`. Jetson dirty checkout은 건드리지 않는다.
저장 revision `194c9c18648f9201df464802884022184095422d1b0b91e6d9a75917c9519d77`,
기존 generated YAML SHA256 `f9bb2943a482c79e489a004ef67f2b71e42268c1324a3a41a8b85163ac93ee67`.
과거 job의 자체 YAML은 정리돼 남아 있지 않다. 현재 남은 generated/previous를 백업했다.

현재 구현의 테스트·최종 코드 SHA·배포 영수증·live readback은 아래 후속 절에 추가한다.
실장비 정밀 후보 주행, 성공 부근/정지 후 오차, 정지 유지, recovery/부작용은 **NOT_RUN**.
기존 관측은 XY0.308926m/yaw-0.472324rad, SUCCEEDED, recovery1, 정지 확인이다.

## 복구와 다음 작업

기존 저장값 전체를 별도 복구 프리셋과 private JSON으로 보존한다. Nav2를 정상 정지한 뒤
최신 revision으로 baseline 값을 CAS 저장하고 새 세션에서 ROS readback한다.
코드 복구는 배포 전 selector 백업으로 이전 검증 릴리스를 다시 선택해 dashboard를 재시작한다.
원본 지도와 사용자 변경은 복구 대상으로 덮어쓰지 않는다. SOFTWARE STOP은 임의 해제하지 않는다.

다음 한 작업은 **현장에서 새 Initial Pose/Goal Pose를 입력한 짧은 비교 주행**이다.
사용자는 설정 완료 후 Nav2 시작과 주행 화면 열기를 요청했다. 실제 이동 전 현재 현장 준비와
기존 정지 수단을 확인하고 같은 시험창의 하위 단계는 반복 승인 없이 진행한다.

## 로컬 검증 (배포 후보)

- 전체 Python: 3,112개, 통과(기존 skip3). 오차/STOP callback 회귀13개 포함.
- JS: 691개 통과. 관련 브라우저 E2E9개 통과(정밀 오차, 프리셋, 운영3D).
- Ruff, mypy, JS112개 syntax, tracked-source secret scan, diff whitespace 통과.
- 최초 전체 검사의 실패3건은 기존 셸 테스트의 LC_ALL=C와 한글 임시 경로에서 발생했다.
  테스트를 변경하지 않고 소유 그룹이 맞는 영문 canonical 임시 경로로 전체를 재실행해 통과했다.
- Jetson 기존 사용자 프리셋 `홍재` 보존. `정밀시험 전 복구 20261029`,
  `Go2 정밀 도착 10cm 20261029`를 기존 API로 별도 저장했다. 이 단계에서는 활성 설정 불변.
- 사용자 CSS 변경2파일은 수정/커밋/배포 대상에서 제외한다.

## 10월 29일 초기 정합 차단 수정

이번 비교 시험은 아직 목표를 보내기 전에 초기화에서 차단됐다. 새 Navigation 클릭은
접수됐지만 첫 3D 정합에도 추적용 보정 제한(.15m/.10rad)을 적용해
`CORRECTION_JUMP_RESEED_REQUIRED`가 발생했다. 화면은 이 사유를 숨기고 `NEED POSE`만
표시했다. 저장지도에서의 관측 후보 적용과 운영 위치추정의 준비 완료는 서로 다른 상태다.

실제 정지 센서의 동일 시각 cloud/odom 4쌍을 비공개로 보존해 재현했다. 클릭 대비
수평 약 .11m, 높이 포함 .207–.216m, 3D 회전 .0975–.0988rad 보정이 계산됐다.
RMSE .051–.053m, overlap 1.0이며 전체 방향 baseline과 기존 코스 제외를 사용했다.
이는 절대 위치 정확도의 독립 측정이 아니다.

명시적인 Navigation 초기 위치 입력에만 별도의 정지 초기 정합 단계를 둔다.
2초 실측 정지, 원래 정합 품질·기하·시각·출처 조건을 유지하며, 클릭에서 최대 .5m/.3rad
안의 결과를 서로 다른 신선한 센서 표본 3개에서 확인한다. 각 결과는 서로 .05m/.05rad
이내로 일치하고 overlap은 .85 이상이어야 한다. 이전 결과가 오래됐거나 품질이 나쁘면
누적 확인을 버린다. 정지 증거 소실, 범위 초과, 출처 변경은 다시 입력해야 한다.
확인 전에는 map 보정·운영 pose·Goal 준비 상태를 내보내지 않는다.
추적 시작 후에는 원래 .15m/.10rad 제한을 그대로 사용한다. 실제 자료 재생에서
3번째 표본부터 MAP_TRACKING, 다음 보정은 .00415m/.00461rad였다.

Navigation 패널은 초기 입력 대기, 정합 확인 중, 차단 사유, 준비 완료를 구분한다.
Goal 활성화는 기존 서버 판정을 그대로 따른다. 초기 위치 드래그에는 저장지도와 같은
공식 Go2 URDF 파생 메시·관절 구조를 실제 미터 비율로 투영한다. 기본 관절 자세의
입력 미리보기이며 관측 pose나 TF를 바꾸지 않는다. 모델 로드 실패 시 기존 마커를 유지한다.

이 수정은 최종 목표 오차 개선의 현장 성공을 의미하지 않는다. 새 세션의 실행 파라미터
readback과 사용자가 새로 입력한 목표의 성공 부근/정지 후 오차 확인이 남아 있다.

소프트웨어 검증: Python 3,116개 통과(3개 skip), JS 694개 통과, 관련 브라우저
10개 및 URDF 추가를 포함한 목표 상세 3개 통과. 기존 서비스 종료 테스트의 일시적
3초 timeout은 설정이나 테스트 완화 없이 전체 재실행에서 통과했다. Ruff/mypy,
변경 JS 문법, tracked-source secret scan 통과. 현장 이동 결과와 별개다.
