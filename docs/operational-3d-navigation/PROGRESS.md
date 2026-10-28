# 3D reference → 운영 Nav2 진행 기록

2026-10-28 KST. 조사 기준 원격 main은 `7ed86cc96dbe500f17e63391cb5e515717a97b0a`.
이번 구현의 최종 source SHA/CI는 Git commit과 최종 인계 응답을 따른다.

사용자가 직접 검증한 기존 2D Nav2 주행과 계단·경사로 보행은 USER_VERIFIED로
인수했다. 검증 controller, 속도, Nav2 command topic과 signed bridge 경로를
유지했다. 장비는 충전 중이며 사용자 답변으로 Jetson 전원 또는 네트워크가
없는 상태가 확인됐다. 따라서 아래 소프트웨어 검사는 현재 장비 성공 증거가 아니다.

| 구간 | 현재 결과 | 증거/제약 |
| --- | --- | --- |
| 전체 PCD 편집·저장 | SOFTWARE_PASS | 기존 immutable full-source editor/store 재사용. 실제 codec/catalogue로 preview 밖 원본·속성·해시·계보를 검사 |
| 3D/2D 지도 묶음 | SOFTWARE_PASS | source ID/revision/hash, parent/edit history, 2D 원점·해상도, 명시적 SE(3) 정렬, 실제 Nav2 snapshot 파일 대조 |
| 지속 정합 → TF → Nav2 | SOFTWARE_PASS | 실제 저장 PCD reader/ICP 및 ROS-shaped production callbacks. 실제 Jetson source/consumer readback은 BLOCKED |
| 시험용 녹색 stop/go | SOFTWARE_PASS | 실제 MissionCoordinator의 도착·대기·다음 goal 경로. OPERATOR_TEST와 NAV_STOP_POINT_TEST로 기록 |
| 현장 목표 도달·실제 정지·재출발 | NOT_RUN | 충전 중. 임의 속도 publisher·ARM·실이동 없음 |
| 경사로 전체 방향 baseline | NOT_RUN | 단계별 pitch/섹터/정합 지표 준비. 현재 경사로 기록 없음 |
| 후방·측면 가중치 채택 | NOT_RUN | 전체 방향 baseline 유지. 센서 X를 로봇 뒤로 해석하지 않음 |
| Jetson 배포·정지 검증 | BLOCKED | 현재 접속 불가. 실제 PID/cwd/SHA/map catalogue는 아직 확인 못함 |

## 최종 로봇 없는 검사

- Python 전수: 3,081개 실행, 실패 0, 환경 skip 3. skip은 선택적 rosbags 1개와
  macOS에 없는 Linux `/proc`/fd 검사 2개다. 새 운영 관련 Python 83개는 모두 실행했다.
- JavaScript 단위: 689 PASS. 브라우저: 220 PASS. 별도 기존 미션 real-API
  fixture: 10 PASS. 이 fixture의 신호·로봇 입력은 소프트웨어 시험 데이터다.
- Ruff, 기존 mypy 4파일, frontend 112개 모듈 syntax, tracked-source credential
  scan, `git diff --check` PASS.
- production gateway의 final guard는 거절 전송 0회, 정상 허가 전송 1회를
  검사했다. 실제 DDS·Nav2 action server·bridge ACK·본체 이동은 검사하지 못했다.

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
