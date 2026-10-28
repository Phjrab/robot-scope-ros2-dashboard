# 3D reference → 운영 Nav2 진행 기록

2026-10-28 KST. Jetson `3dd8e8119028`에서 사용자 코스 제외 PCD 13,546점으로
실제 정지 상태의 운영 source/consumer 연결을 확인했다. 원격 CI도 PASS다.
첫 미션의 사전 공간 검사 거절과 STOP 정리 오류를 수정하고 회귀 검사를 통과했다.
최종 source/배포 SHA/CI는 최종 인계 응답을 따른다.

사용자가 직접 검증한 기존 2D Nav2 주행과 계단·경사로 보행은 USER_VERIFIED로
인수했다. 검증 controller, 속도, Nav2 command topic과 signed bridge 경로를
유지했다. 사용자가 전원·같은 공간·현장 준비를 확인했다. 실제 주행 경로는
사용자가 Nav2 페이지에서 지정한 웨이포인트를 인수한 뒤 실행한다.

| 구간 | 현재 결과 | 증거/제약 |
| --- | --- | --- |
| 전체 PCD 편집·저장 | FIELD_PASS | 전체 원본 22,529점 보존. 첫 사본 22,517점, 사용자 코스 외부 제외 사본 13,546점 저장·재조회 |
| 3D/2D 지도 묶음 | FIELD_PASS (제한 시험) | 회전하지 않은 원본 2D와 동일 좌표. 실제 관측으로 확인한 514개 셀만 새 시험 사본에서 free로 변경. 기존 occupied 3,625셀 보존 |
| 지속 정합 → TF → Nav2 | FIELD_PASS (정지) | 실제 사본 기준 보정 500회 이상, 같은 stamp의 map→odom→base_link, controller/BT의 canonical body odom 구독, Nav2 READY 확인 |
| 시험용 녹색 stop/go | SOFTWARE_PASS | 실제 MissionCoordinator의 도착·대기·다음 goal 경로. OPERATOR_TEST와 NAV_STOP_POINT_TEST로 기록 |
| 현장 목표 도달·실제 정지·재출발 | PRE_DISPATCH_REJECTED | 첫 고고씽1이 차체 반경 검사에서 거절됨. Nav2 goal ID 없음, 브리지 이동 0회. 사용자가 수정한 두 점은 같은 검사 통과 |
| 경사로 전체 방향 baseline | NOT_RUN | 단계별 pitch/섹터/정합 지표 준비. 현재 경사로 기록 없음 |
| 후방·측면 가중치 채택 | NOT_RUN | 전체 방향 baseline 유지. 센서 X를 로봇 뒤로 해석하지 않음 |
| Jetson 배포·정지 검증 | FIELD_PASS | 별도 release 2,156파일 hash 검증. 사용자 checkout·CSS·기존 지도 81파일·튜닝 보존 |

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
자동 검증 완료로 간주해서는 안 된다. 현재 시험 지도는 회전하지 않은 원본에서
생성한 `97790325789687abea274ed6`, revision
`e852388ae426b0bcc8c3e69b1673926488fb0f5a37f014d4c05a3213d238e98c`다.

## 최종 로봇 없는 검사

- 최신 Python 전수: 3,089개 실행, 실패 0, 환경 skip 3. skip은 선택적 rosbags 1개와
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

초기 seed는 자동 실행하지 않는다. 기존 initialpose 경로로 선택한 본체 XY/yaw를
확인하고, 신선한 odometry에서 2초 정지가 관측돼야 3D 정합을 시작한다. 그때도
선택한 IMU 높이·roll/pitch와 실제 본체 lever arm은 유지한다. 지도·body 교정이
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
