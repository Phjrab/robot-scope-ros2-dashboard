# 운영 3D 위치추정 현장 인계

**2026-10-29 최신 인계:** [정밀 도착 두 실행 보고서](GOAL_PRECISION_TWO_TRIALS_20261029.md).
실제 배포는 `b15099cd8c40326b810e6c39a136f94944443cb9`로 갱신됐다.
이후 초기 위치는 **Navigation의 INITIAL POSE/SEND POSE**에서 입력한다.
동일 URDF 미리보기와 실제 정지 초기 정합 확인을 거쳐 Goal을 허용한다.
0.10m/0.10rad 두 비교 목표는 모두 CANCELED, 정밀 방향 정렬은 미해결이다.
Nav2 idle·제어권 해제 후 사용자가 장비를 종료했다. **정밀 후보 저장값의 baseline
복원은 미완료**이므로 다음 기동 후 주행 전에 확인한다. 과거 목표를 자동 재전송하지 않는다.
이하 내용은 10월 28일의 기존 검증·인계 기록이다.

2026-10-28 KST. 실제 3D 정합·TF·body odom·Nav2 연결을 통한 단일 목표 이동과
도착 후 정지를 확인했다. 사용자가 실제 이동과 지도 표시 위치 일치를 확인했다.
코드/배포 SHA는 `e680aa34bbaccff22d4206e391fdb9e879f6d048`, release는
`/home/unitree/robot-scope-releases/robot-scope-e680aa34bbac`다.
Python 3,098개/JavaScript 689개와 해당 배포 SHA 원격 CI PASS.
초기 위치 HTTP는 실제 runtime 적용 영수증을 확인하며 새 평면 seed를 지원한다.

**정밀 Goal Pose 일치는 미해결**이다. 도착 후 약 31cm/27도 차이를 별도
[GOAL_FINAL_POSE_MISMATCH_20261028.md](GOAL_FINAL_POSE_MISMATCH_20261028.md)에
goal ID·실측 source pose·지도 pin·복구 절차와 함께 기록했다. 사용자가 기록 후
작업 종료를 요청했으므로 추가 주행·튜닝은 진행하지 않았다.

사용자는 장애물 외 전 영역을 이동 가능으로 만들고 현재 이동한 위치에서 자동
정합할 것을 요청했다. 새 운영자 자유공간 지도는 9a382e3eb990fb02fe1a3569이며
자세한 pin·셀 보존 결과는 PROGRESS.md에 있다. raw scan·반경 검사는 유지한다.
사용자가 이전 고고씽 목표 주석을 삭제했으므로 복원하지 않는다. GOAL POSE 활성화
후 사용자가 직접 입력한 단일 목표의 실제 이동은 확인했다. 현장 녹색 버튼
stop-and-go와 경사로 위치추정은 NOT_RUN이며 전체 완료로 기록하지 않는다.

Unitree LowState의 실제 스틱 입력으로 단발 감시기의 STOP·Nav2 종료·bridge 종료를
확인했다. 감시기는 양도 후 종료되며 상시 기능이나 즉시 하드웨어 양도 보장이 아니다.
그 STOP 잠금으로 생긴 HTTP 423은 중립 3초 확인 뒤 정상 해제했다. 실제 주행 전
현재 감독·정지 수단을 유지하고 감시기를 명시적으로 다시 시작한다.

종료 시 Nav2 idle, lease/active mission/motion 없음, command zero를 확인했다.
두 번째 10분 시험 guard는 TRIAL_DEADLINE으로 STOP·Nav2/bridge 종료를 요청하고
종료했으며 recorder도 종료됐다. SOFTWARE STOP은 잠긴 채 유지한다. 다음 시작은
현재 현장·중립 확인 후 기존 잠금 해제와 bridge 시작을 거쳐 새 위치 정합을 한다.
Dashboard 서비스는 실행 중이다. `final-session-closeout.json`에 readback을 보존했다.

## 장비 연결 후

1. 현재 실제 SSH 주소로 접속해 service ExecStart, PID/cwd, source manifest/SHA와
   dirty/untracked 사용자 변경을 읽는다. 과거 `unitree@192.168.50.30`,
   `/home/unitree/robot-scope[-releases|-data]`는 탐색 후보이며 현재값으로 단정하지 않는다.
2. 실제 catalogue에서 최신 3D 지도와 연결할 기존 2D 지도를 선택한다. 원본/편집본
   ID/revision, full PCD hash·parent, 2D geometry/lineage를 보존한다. 기존 큰 백업의
   유효성을 먼저 확인하고 이번 selector/config/사용자 변경만 필요한 만큼 추가 백업한다.
3. 검증 profile의 effective controller/속도/odom topic, `camera_init→body`,
   IMU→실제 base 장착 변환, 3D→2D 정렬, `/tf`·`/tf_static` 발행자 및 기존 정지 경로를
   읽는다. 관측 namespace와 운영 namespace를 섞지 않는다. AMCL 등 동일 edge를
   발행하는 기존 producer가 있다면 idle에서 명시적으로 정리하고 기존 설정을 기록한다.
4. 새 source release를 별도 디렉터리에 설치하고 file manifest를 대조한다. 기존
   checkout·지도·DB·환경을 reset/일괄 복원하지 않는다. 기존 launcher selector와
   venv/ROS workspace를 재사용한다. 필요한 Dashboard 재시작만 수행한다.

## 장비에서 확인할 calibration 계약

navigation runtime directory의 private `operational-calibration.json`만 서버가 읽는다.
HTTP 요청으로 verified/extrinsic/quality 기준을 주입할 수 없다. 다음 값은 실제
readback과 정지 baseline 근거로 작성하고, 사용자에게 임의 값을 추측하게 하지 않는다.

- `verified: true`, `evidence`: 실제 구성·TF·지도 정렬을 확인한 기록의 식별자.
- `localization_root`: 확인한 원본 PCD의 `map_id`, `revision`, `sha256`, `frame_id`,
  `units`. frame 이름이 같은 다른 mapping session은 이 정렬을 재사용할 수 없다.
  기존 편집 저장소가 검증한 동일 원본의 편집 사본만 같은 정렬을 재사용한다.
- `localization_frame`, `navigation_map_id`, `navigation_map_revision`,
  `controller_odom_topic`, `navigation_profile`: 선택 지도와 effective profile의 정확한 pin.
- `T_nav_map_from_localization_map`, `T_imu_base`: 검증한 proper 4×4 SE(3).
  identity도 일치 근거가 있어야 한다. 2D YAML origin을 두 번 적용하지 않는다.
- `tf_publishers`: `/tf`와 `/tf_static` 각각 기존 발행자의
  `{node_name, node_namespace}` 배열. 새 navigation runtime 자신은 제외한다.
- `policy`: `max_rmse_m`, `max_correction_age_s`, `max_translation_step_m`,
  `max_rotation_step_rad`, `compute_budget_s`, `max_propagation_m`, `evidence`.
  각 값은 단위가 이름에 명시돼 있고 parser에 유한한 상한이 있다. 현재 정지 baseline은
  약 10Hz LIO, RMSE 0.0421m, Jetson 최초 포함 정합 p95 약 114ms다.

이 파일이 없으면 source 선택은 `DEVICE_BODY_MAP_ALIGNMENT_READBACK_REQUIRED`다.
이는 3D 활성화에 필요한 한 가지 실제 좌표 계약이며 YOLO·앞발·C3·VSLAM을
추가 선행조건으로 삼지 않는다. 현재 calibration은 기존 장착 convention과
회전하지 않은 시험 지도에 고정돼 있다. 과거 회전 2D 편집본의 identity 계보는
틀린 것으로 확인됐으므로 재사용하지 않는다. 현재 지도 pin은 PROGRESS.md 참조.

## 화면에서 할 일

1. 저장 3D 지도 → 기존 3D 점 편집 → 영역·높이 선택 → 제외/undo/redo →
   **위치추정용 사본 저장**. 새 ID/revision을 재조회하고 원본 hash 보존을 확인한다.
2. 새 사본에서 기존 지도 클릭 seed·방향·높이·코스 가중 정합 → 관측 후보 적용.
3. **3D 위치추정을 주행에 사용**을 열어 연결할 검증된 2D 지도를 선택하고
   **이 3D 지도로 위치추정 준비**를 누른다. 이 단계는 다음 Nav2 시작의 bundle 선택이다.
4. 기존 주행 시작으로 그 2D map/profile을 실행한다. 정지 상태에서
   **현재 정지 위치 확인 · 정합 시작**을 누른다. 새로고침으로 reference hash,
   correction sequence/age, TF authority와 실제 Nav2 소비 pose/controller odom을 확인한다.
   브라우저를 닫아도 worker와 correction이 계속되는지 정지 상태에서 확인한다.
5. 기존 미션의 ready run을 선택하고 **정지점 녹색 버튼 시험 설정**을 누른다.
   이는 `NAV_STOP_POINT_TEST`이며 full competition-native/앞발 판정 모드는 활성화하지 않는다.

## 같은 현장 승인 시험창

실제 이동 직전에 운영자, 기존 비상정지·수동 회수 수단, 비어 있는 제한 구간,
현재 active goal·제어 owner를 한 번 확인한다. 충전 연결을 사용자가 안전하게
해제하고 준비가 확인된 뒤 기존 ARM/lease 절차를 사용한다.

짧은 Nav2 목표 → 도달·실제 정지 확인 → 2초 dwell → 시험용 녹색 버튼 1회 →
다음 goal 1개 → 도달·정지 순서로 진행한다. 두 번째 정지점에서 이전 버튼
허가가 재사용되지 않는지도 같은 시험창에서 확인한다. 명령 ZERO/정지 ACK,
odometry 정지 증거, 눈으로 확인한 실제 정지를 구분해 기록한다.

경사로는 전체 점군으로 평지·진입·상승·정상·하강을 먼저 기록한다. raw/LIO/정합/
TF/scan-costmap/browser를 구분하고 source age·correction age·RMSE·overlap·
geometry·body sectors·pitch·연산시간을 남긴다. 필요하면 같은 기록에서 후방·측면
정책을 비교한 뒤 채택한다. 현재 rear 우선 채택과 정확도 향상 증거는 없다.

## 중단·복구

- 현재 미션 ABORT → 기존 Nav2 cancel/STOP → 정지 ACK와 실제 정지 → owner 반환 확인.
- 주행을 idle로 종료한 뒤 화면의 **기존 2D 위치 모드 선택**으로 selection을 해제한다.
  다음 기존 Nav2 시작은 원래 동작을 사용한다. Dashboard 재시작도 selection을 복원하지 않는다.
- 큰 jump/source 변경은 정지 후 같은 3D seed를 새로 확인한다. TF authority graph가
  바뀐 경우 기존 job을 종료하고 확인한 topology로 새 job을 시작한다.
- release 문제는 백업한 기존 launcher selector/profile로 복귀한다. 생성한 PCD 사본과
  사용자 지도/DB는 그대로 보존한다. 기존 검증 controller·속도는 복구 기준이다.

최종 현장 기록에는 코드/배포 SHA·PID/cwd, 선택 지도 묶음, 실제 위치 source와
TF/odom consumer, 실제 PCD 저장, goal/stop/dwell/OPERATOR_TEST/departure,
경사로 baseline·복구 결과를 각각 기록한다. 현재 단일 목표 실제 이동은 확인됐고,
정밀 도착은 OPEN, 현장 녹색 버튼 재출발·경사로는 NOT_RUN이다.

## 유선 Jetson의 본체 odometry 연결

실제 장비는 `go2-onboard` + `enP8p1s0`이며 wireless launcher의 `eno1` 설정을
적용하지 않는다. 서버가 읽는 robot profile의 `navigation_odometry_source`를
`fastlio_body`로 선택하면 mapping transport/profile은 그대로 유지하고 기존
sidecar가 발행하는 `/robot_scope/nav/controller_odom_fastlio`를 controller,
BT navigator 및 설정된 smoother에 고정한다. 이 설정은 HTTP 튜닝 필드가 아니다.
3D bundle 사용 시 TF와 이 odometry가 같은 `T_odom_imu × T_imu_base`, 원본 stamp,
연속 본체 pose로부터 계산한 body-frame 속도를 사용한다. 기존 RPP/RotationShim,
속도와 goal/STOP 경로는 유지한다. 10Hz LIO의 기존 9.5/9.0Hz readiness dwell도
동일하게 재사용한다. 설정을 생략하면 기존 profile 기본값을 사용하며, 소스 전환
전후에 저장된 튜닝값을 보존한다. 원래 vendor odom 연결로 완전히 복구하려면
idle에서 해당 profile 필드를 제거하고 기존 서비스 재시작 절차를 사용한다.
