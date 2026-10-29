# 3D reference → 운영 Nav2 진행 기록

**2026-10-29 후속:** [정밀 도착 두 실행 보고서](GOAL_PRECISION_TWO_TRIALS_20261029.md).
실제 배포 `b15099cd8c40326b810e6c39a136f94944443cb9`, 후보 0.10m/0.10rad로
두 새 목표를 비교했다. 둘 다 CANCELED이며 방향 정렬은 OPEN이다. 짧은 목표의 취소
부근 XY 3.18cm/yaw -43.70°, 정지 후 4.60cm/-45.00°다. Nav2 idle·lease 해제 확인.
장비 종료로 baseline 저장값 복원은 미완료이므로 다음 시작 전에 복구 상태를 확인한다.
이하 10월 28일의 기존 이동 검증과 미실시 항목은 당시 기록으로 보존한다.

2026-10-28 KST. Jetson `e680aa34bbaccff22d4206e391fdb9e879f6d048`에서
사용자 코스 제외 PCD 13,546점으로 실제 Nav2 이동을 확인했다. 사용자가 실제
이동과 지도 표시 위치 일치를 확인했다. 정밀 Goal Pose 일치는 별도 미해결이다.
도착 후 평면 약 31cm/방향 약 27도 차이를
[후속 해결 기록](GOAL_FINAL_POSE_MISMATCH_20261028.md)에 남겼다.
배포 SHA의 [원격 CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40682657164)는 PASS다.
사용자의 기록 후 종료 요청으로 추가 주행 없이 이번 작업을 마무리했다.

사용자가 직접 검증한 기존 2D Nav2 주행과 계단·경사로 보행은 USER_VERIFIED로
인수했다. 검증 controller, 속도, Nav2 command topic과 signed bridge 경로를
유지했다. 사용자가 전원·같은 공간·현장 준비를 확인했다. 실제 주행 경로는
사용자가 Nav2 페이지에서 지정한 웨이포인트를 인수한 뒤 실행한다.

| 구간 | 현재 결과 | 증거/제약 |
| --- | --- | --- |
| 전체 PCD 편집·저장 | FIELD_PASS | 전체 원본 22,529점 보존. 첫 사본 22,517점, 사용자 코스 외부 제외 사본 13,546점 저장·재조회 |
| 3D/2D 지도 묶음 | FIELD_PASS (운영자 지정 공간) | 현재 operator_free 사본. 동일 좌표·장애물 3,625셀 보존, unknown 49,411셀을 사용자 요청으로 free 지정. 센서 관측 공간과 구분 |
| 지속 정합 → TF → Nav2 | FIELD_PASS (실제 이동) | 실제 PCD 보정·운영 TF·canonical body odom을 사용해 사용자 목표로 이동. 사용자 현장 확인 |
| 시험용 녹색 stop/go | SOFTWARE_PASS | 실제 MissionCoordinator의 도착·대기·다음 goal 경로. OPERATOR_TEST와 NAV_STOP_POINT_TEST로 기록 |
| 단일 목표 이동·도착 후 정지 | FIELD_PASS (기존 허용오차) | Nav2 SUCCEEDED, 실제 이동 사용자 확인. 도착 후 command zero·StopMove·측정 정지 확인. 정밀 도착은 아래 미해결 |
| 최종 Goal Pose 정밀 일치 | OPEN | 도착 후 평면 0.308926m, 방향 -27.06도 차이. 기존 위치 허용오차 0.35m. 원인 확정·수정 전 |
| 현장 녹색 버튼 재출발 | NOT_RUN | 기존 초기 미션 사전 거절은 수정했으나 실제 도착·버튼·다음 goal 전체 시험은 미실시 |
| 경사로 전체 방향 baseline | NOT_RUN | 단계별 pitch/섹터/정합 지표 준비. 현재 경사로 기록 없음 |
| 후방·측면 가중치 채택 | NOT_RUN | 전체 방향 baseline 유지. 센서 X를 로봇 뒤로 해석하지 않음 |
| Jetson 배포·정지 검증 | FIELD_PASS | 최신 release 2,159 source hash/61 map geometry 파일 보존 확인. 사용자 checkout·CSS·튜닝 보존. 종료 시 Nav2 idle·lease 해제·SOFTWARE STOP 잠금 |

## 사용자 코스 제외와 좌표 문제

코스 제외 사본의 실제 운영 잔차는 약 0.033~0.037m, overlap 1.0이다.
80개 exact-stamp pair와 161개 지도 pose를 관측한 8초 동안 XYZ 범위는
약 5.5/9.7/10.0mm였다. `/scan`은 양쪽 costmap이 소비하고 전방 최근접
반환은 본체 축 기준 약 1.37m였다. 이는 정지 관측이며 주행 정확도 증명이 아니다.

첫 미션은 ROS action 호출 전 `known_free`의 robot-radius 0.22m 검사에서
거절됐지만 일반 예외로 취급돼 미션이 uncertain에 남았다. 기존 SOFTWARE STOP,
lease 해제와 nonzero Move 0회를 확인하고 미션 기록을 백업했다. 고정 Dashboard
서비스의 정상 종료로 Nav2와 소유 FAST-LIO를 정리한 뒤 idle로 복구했다.
후속 코드는 guarded mission의 사전 NavigationJobError를 명시적 미전송 영수증으로
전달한다. 제출 이후 예외는 계속 uncertain이다. 전역 STOP은 미션 정리가 실패해도
기존 Nav2 정리를 실행하고, 미션 fence를 임의로 해제하지 않은 채 오류를 보고한다.

사용자가 원본 PCD 위에 8각형 외부, Z -1…3m를 localization 제외로 지정했다.
새 사본은 `e1dd40cc6911404dbdfc073b`, revision
`c7d7ce7e04b2fb80519854cc71465f61af9fff210ac72e299105502497401ad5`,
SHA-256 `6ec38aa876ffcfe505ee81204d94fa84e1c3cb438ae706a6a6b7fc0048970b5a`다.
같은 실제 source stamp의 점군으로 비교한 결과, 참조 지도만 제외하면 잔차가
0.248m로 운영 기준을 초과했다. 저장된 localization 제외 주석을 현재 보정/seed로
변환한 관측점에도 적용하면 178점 중 85점을 사용하고 overlap 1.0,
RMSE 0.0350m였다. 기존 전체 방향 baseline은 0.0421m였다. 이는 해당 정지 입력의
정합 잔차이며 독립 위치 정확도나 경사로 성능 증명이 아니다.

후속 구현은 PCD 저장 때와 같은 polygon/Z 판정을 위치추정 query에만 적용한다.
visibility/keepout 주석을 localization 제외로 취급하지 않는다. 남는 점이 60개
미만이면 새 보정을 거절하고 기존 보정 age 한도로 주행 readiness를 내린다.
raw cloud와 Nav2 `/scan`은 전체 센서 경로를 유지한다.

기존 `map_20261027_125427_edited`는 픽셀이 회전했는데 v1 계보가 identity를
주장하는 문제가 발견돼 선택을 해제했다. v1은 회전 변환을 표현하지 못하므로
새 회전 편집본에는 identity 계보를 생성하지 않는다. 과거 회전본의 계보를
자동 검증 완료로 간주해서는 안 된다. 이전 observed_trial 지도는 회전하지 않은 원본에서
생성한 `97790325789687abea274ed6`, revision
`e852388ae426b0bcc8c3e69b1673926488fb0f5a37f014d4c05a3213d238e98c`다.

## 최종 로봇 없는 검사

- 최신 Python 전수: 3,098개 실행, 실패 0, 환경 skip 3. skip은 선택적 rosbags 1개와
  macOS에 없는 Linux `/proc`/fd 검사 2개다. 코스 제외 관련 검사 64개와 지도 저장
  검사 56개도 통과했다.
- JavaScript 단위: 689 PASS. 브라우저: 220 PASS. 별도 기존 미션 real-API
  fixture: 10 PASS. 이 fixture의 신호·로봇 입력은 소프트웨어 시험 데이터다.
  코스 제외 후 JavaScript 689개와 운영 3D 브라우저 7개를 다시 확인했다.
- Ruff, 기존 mypy 4파일, frontend 112개 모듈 syntax, tracked-source credential
  scan, `git diff --check` PASS.
- production gateway의 final guard는 거절 전송 0회, 정상 허가 전송 1회를
  검사했다. 실제 DDS·Nav2 action server·bridge ACK·본체 이동은 검사하지 못했다.

첫 구현 commit `f5cff3f15a90`의 [원격 CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40653640990)는
Ubuntu 24.04/Python 3.12 전체와 별도 offline integration이 PASS였다. Ubuntu
22.04/Python 3.10은 Python·정적 검사 PASS, 브라우저 219 PASS/1 FAIL이었다.
실패 screenshot은 기존 SLAM 정상 조작 fixture가 프레임을 한 번 보낸 뒤 1.5초
freshness 한도를 넘어 따라가기 checkbox가 비활성화된 것을 보여준다. 정확한 게시
소스에서 같은 항목 5회 반복은 PASS였다. 정상 조작 fixture에만 100ms heartbeat를
추가했으며 실제 SLAM 기능·freshness 기준·stale-source 회귀 검사는 유지했다.
보완 후 SLAM·운영 3D 브라우저 33개와 JavaScript 689개 재검사는 PASS였다.
이 후속 변경의 최종 SHA/CI는 최종 인계 응답과 private source-candidate 기록을 따른다.

## 운영 연결

`NavigationJobManager`가 기존 2D map snapshot과 함께 선택한 전체 PCD와
`operational-3d.json`을 한 job 디렉터리에 고정한다. 원본·편집 저장은 active
source를 바꾸지 않는다. source 선택과 기존 2D 모드 복귀는 idle에서만 가능하다.
Dashboard 재시작은 source 선택·seed·시험 허가를 복원하지 않는다.
지도 정렬은 frame 이름뿐 아니라 3D 원본 ID/revision/hash에 고정한다. 검증한
편집 계보의 사본은 허용하며, 같은 frame 이름의 다른 mapping session은 거절한다.

기존 `navigation_runtime`이 유일한 운영 발행자다. `/cloud_registered`는 이미
`camera_init` 좌표의 점이므로 IMU 외부변환을 중복 적용하지 않는다. 같은 source
stamp의 `/Odometry`를 32개 bounded ring에서 찾아 worker에 전달한다. 브라우저
polling 없이 최대 1개 worker가 기존 코스 가중 SE(3) solver로 정합한다.

정합은 `T_M_O`를 계산한다. 현재 본체는
`T_N_B(t) = T_N_M × T_M_O × T_O_I(t) × T_I_B`다.
운영 TF는 full SE(3)의 `map→odom→base_link`이고 `/amcl_pose`에도 동일한 본체
pose를 발행한다. stamp는 입력 odometry 시각을 보존한다. competition_fastlio
controller odom을 쓰는 기존 profile에서는 같은 본체 pose와 본체 좌표계 속도를
기존 canonical odom topic으로 발행한다. 다른 검증 profile의 controller topic은
보존하며 실제 장비에서 그 frame/속도 계약을 확인해야 한다.

초기 seed는 프로세스 시작만으로 자동 실행하지 않는다. 기존 initialpose 경로의
새 본체 XY/yaw를 반영하되, 선택한 본체 높이·기울기와 map/IMU/body 교정을 보존한다.
신선한 odometry에서 2초 정지가 관측돼야 3D 정합을 시작한다. HTTP는 ROS 발행만을
성공으로 처리하지 않고 같은 stamp·runtime·bundle·localization generation의 실제
적용 영수증을 확인한다. 정합 완료 전에는 목표를 허용하지 않는다. 지도·body 교정이
없는 경우 identity를 추측하지 않고 해당 활성화만 차단한다.

보정의 age/전파 거리, 수렴·겹침·geometry·전체 비가중 RMSE와 보정 jump를 검사한다.
I1 관측의 5cm 한도 해제 선택은 유지하고, 운영 한도는 장비에서 확인한 별도 policy를
쓴다. 보정이 오래되면 TF pose를 계속 신선한 지도 정합처럼 표시하지 않고 기존
runtime health/interlock으로 주행을 차단한다. jump/source 변경은 새 초기화를 요구한다.

TF는 장비에서 확인한 `/tf`·`/tf_static` 발행자 목록과 endpoint GID, 사전 보호
edge 검사로 한 권한을 확인한다. 이 Humble 환경은 일반 callback의 per-message
publisher identity를 보장하지 않으므로 상태에 이를 false로 기록한다. 운영 중에는
검증된 topology와 같은 graph를 요구하며 변경 시 권한을 폐기한다.

## 출발 허가

기존 미션을 ready 상태에서 시험 설정하면 각 도착점은 최소 2초 dwell 후
`after_arrival_confirmation`에서 대기한다. UI에서는 시험용 녹색 버튼으로 표시한다.
Nav2 SUCCEEDED와, 신선한 LIO 본체 pose 변화로 계산한 정지 증거를 모두 요구한다.
이는 앞발 접촉·대회 채점 또는 독립적인 실제 정지 계측을 대신하지 않는다.

허가는 현재 run/visit/stop generation, map bundle/localization/runtime generation,
server 발급 시각과 2초 만료에 묶인다. 접근·dwell 중에는 예약하지 않는다.
중복 요청은 같은 영수증만 반환한다. source 상실을 관측하면 회복 뒤에도 옛
허가를 되살리지 않는다. 실제 YOLO 관측·GREEN 값은 전혀 쓰지 않는다.

기존 Nav2 consumer 직전까지 내부 guard를 전달해 비동기 preflight 중 취소·만료·
source 변경을 다시 확인한다. 전송 전 거절과 제출 결과 불명을 구분하여 STOP이
소유권을 정상 정리할 수 있다. 의도적 신호 대기 중에는 진행 중인 Nav2 goal이
없으므로 progress recovery가 대기 해제를 대신하지 않는다.

## 경사로 한계

현재 정책은 ALL_DIRECTION_BASELINE이다. 같은 시각의 본체 중력 정렬 heading으로
전/후/좌/우 점 수와 pitch, 정합 metrics를 기록한다. `/scan` 장애물 입력은 기존
전체 센서 경로를 유지한다. 현재 sensor-frame 높이 절단이 실제 경사로에서 바닥을
장애물로 만드는지는 현장 확인이 필요하다. 이 현상을 정합 실패로 판정하지 않는다.
동일 경사로 기록의 baseline 비교 전에는 후방 가중치 성능 향상을 주장하지 않는다.

실행 순서와 복구는 [HANDOFF.md](HANDOFF.md)를 따른다.

## 초기 위치 UI 거절 및 운영자 자유공간 사본

20:32의 초기 위치 HTTP 200은 실제 ROS callback의
`RESEED_REQUIRES_OBSERVED_STOP` 거절을 전달하지 못했다. 3D seed와 새 클릭 사이의
5cm 제한도 일반 Nav2 초기 위치 수정과 충돌했다. 후속 코드는 실제 적용 영수증과
정지 preflight를 추가하고, 새 클릭의 평면 좌표를 보존한 3D seed로 변환한다.
정합 잔차·jump·시각·TF authority 검사는 유지한다.

사용자의 명시적 요청으로 `map_20261027_125427_operator_free_20261028` 사본을
저장했다. ID `9a382e3eb990fb02fe1a3569`, revision
`d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552`.
기존 장애물 3,625셀을 byte 단위로 보존하고 unknown 49,411셀만 free로 변경했다.
총 free 49,925셀. 이는 **운영자 지정 통행 정책**이며 센서로 확인된 빈 공간이 아니다.
255×210, 0.05m, origin/yaw와 PCD는 보존한다. raw scan·실시간 costmap과
차체 여유 검사를 해제하지 않는다. 이전 trial 지도·교정 파일도 백업해 보존했다.

Unitree 리모컨 시험 감시기는 실제 ly=0.159 입력을 감지했다. 감지 후 STOP 응답
0.256초, Nav2 종료 응답 0.798초, bridge stop 요청 응답 1.368초였다. 이는 정지
상태의 단발 시험이며 상시 기능/즉시 하드웨어 양도 보증이 아니다. 후속 START가
HTTP 423인 이유는 남은 SOFTWARE STOP 잠금이었다. 중립 1,500개/3초 관측 후
해제·Nav2 재시작을 확인했다. 이전 목표 주석은 사용자가 삭제해 현재 비어 있으며
임의로 복원하지 않는다. 이후 GOAL 활성화, 사용자 직접 목표 입력·실제 이동 확인까지
완료했다. 자동 현재 위치 정합은 5개 독립 초기값의 수렴 일치로 확인했고, 기존
initialpose 경로의 실제 적용 ACK 후 MAP_TRACKING/READY가 됐다. 출발 전 잔차는
약 0.045m, 도착 후 약 0.052m였다. 이것을 독립 위치 정확도로 해석하지 않는다.

단일 목표 이동과 도착 후 정지는 확인됐지만 정밀 위치·방향 일치는 OPEN이며,
현장 stop-and-go와 경사로는 NOT_RUN이다. 종료 상태와 다음 원인 분석의 정확한
goal·좌표·지도 pin·증거 경로는 [별도 기록](GOAL_FINAL_POSE_MISMATCH_20261028.md)을 따른다.
